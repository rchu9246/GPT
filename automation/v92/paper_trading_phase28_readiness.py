#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 2.8
Production Readiness + Controlled Go-Live

Safety design:
- Production PAPER only.
- Never connects to a broker.
- Never enables real-money execution.
- Requires consecutive PASS trading days before an ARM action can succeed.
- Fail-closed on missing/stale/inconsistent data.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = os.getenv("PAPER_TRADING_MODE", "SHADOW_ONLY_NO_BROKER")
ACTION = os.getenv("PHASE28_ACTION", "readiness_check")

REQUIRED_PASS_DAYS = max(1, int(os.getenv("PHASE28_REQUIRED_PASS_DAYS", "5")))
MAX_MARKET_STALE_DAYS = max(0, int(os.getenv("PHASE28_MAX_MARKET_STALE_DAYS", "3")))
MIN_EQUITY = float(os.getenv("PHASE28_MIN_EQUITY", "0"))
MAX_OPEN_POSITIONS = max(0, int(os.getenv("PHASE28_MAX_OPEN_POSITIONS", "10")))

ALLOWED_ACTIONS = {"readiness_check", "arm_production_paper"}


def request(table: str, query: str):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {body}") from exc


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def load_snapshots():
    query = urllib.parse.urlencode(
        {
            "select": (
                "run_key,run_date,strategy_version,mode,status,pipeline_status,"
                "latest_market_date,signals_eligible,orders_created,positions_open,"
                "cash,market_value,equity,realized_pnl,unrealized_pnl,raw_summary,completed_at"
            ),
            "strategy_version": f"eq.{STRATEGY_VERSION}",
            "mode": f"eq.{MODE}",
            "order": "run_date.desc,completed_at.desc",
            "limit": str(max(REQUIRED_PASS_DAYS * 5, 30)),
        }
    )
    rows = request("gptq_paper_daily_snapshots", query)
    return rows if isinstance(rows, list) else []


def one_per_day(rows):
    daily = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = str(row.get("run_date") or "")[:10]
        if not day or day in seen:
            continue
        seen.add(day)
        daily.append(row)
    return daily


def snapshot_pass(row, newest=False):
    run_day = parse_day(row.get("run_date"))
    market_day = parse_day(row.get("latest_market_date"))
    stale_days = (
        (run_day - market_day).days
        if run_day and market_day
        else 999999
    )

    checks = {
        "status_completed": row.get("status") == "COMPLETED",
        "pipeline_completed": row.get("pipeline_status") == "COMPLETED",
        "latest_market_date_present": market_day is not None,
        "market_data_fresh": market_day is not None and stale_days <= MAX_MARKET_STALE_DAYS,
        "equity_non_negative": as_float(row.get("equity")) >= MIN_EQUITY,
        "positions_within_limit": 0 <= as_int(row.get("positions_open")) <= MAX_OPEN_POSITIONS,
    }

    raw = row.get("raw_summary")
    if isinstance(raw, dict):
        integrity = raw.get("integrity_checks")
        if isinstance(integrity, dict) and integrity:
            checks["phase26_integrity_all_pass"] = all(bool(v) for v in integrity.values())

    return all(checks.values()), checks, (stale_days if market_day else None)


def main():
    if ACTION not in ALLOWED_ACTIONS:
        raise RuntimeError(f"Unsupported PHASE28_ACTION: {ACTION}")

    # Hard safety lock: Phase 2.8 cannot turn on broker execution.
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety lock: Phase 2.8 requires PAPER_TRADING_MODE=SHADOW_ONLY_NO_BROKER"
        )

    rows = load_snapshots()
    daily = one_per_day(rows)

    if not daily:
        result = {
            "version": "2.8",
            "status": "BLOCKED",
            "release_state": "BLOCKED",
            "reason": "NO_DAILY_SNAPSHOTS",
            "broker_execution_enabled": False,
            "real_money_enabled": False,
        }
        write_outputs(result, {}, [])
        return 1

    current = daily[0]
    current_pass, current_checks, stale_days = snapshot_pass(current, newest=True)

    streak = 0
    streak_days = []
    for row in daily:
        ok, _, _ = snapshot_pass(row)
        if not ok:
            break
        streak += 1
        streak_days.append(str(row.get("run_date"))[:10])

    readiness = current_pass and streak >= REQUIRED_PASS_DAYS

    if not current_pass:
        release_state = "BLOCKED"
        status = "FAIL"
        reason = "CURRENT_HEALTH_CHECK_FAILED"
    elif not readiness:
        release_state = "OBSERVATION"
        status = "PASS"
        reason = "WAITING_FOR_REQUIRED_PASS_DAYS"
    elif ACTION == "readiness_check":
        release_state = "READY_FOR_PRODUCTION_PAPER"
        status = "PASS"
        reason = "GO_LIVE_GATE_SATISFIED"
    else:
        release_state = "ARMED_FOR_PRODUCTION_PAPER"
        status = "PASS"
        reason = "MANUAL_ARM_ACCEPTED"

    result = {
        "version": "2.8",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "strategy_version": STRATEGY_VERSION,
        "mode": MODE,
        "requested_action": ACTION,
        "status": status,
        "release_state": release_state,
        "reason": reason,
        "required_consecutive_pass_days": REQUIRED_PASS_DAYS,
        "consecutive_pass_days": streak,
        "streak_dates": streak_days,
        "latest_market_date": current.get("latest_market_date"),
        "market_stale_days": stale_days,
        "current_run_key": current.get("run_key"),
        "current_checks": current_checks,
        "current_snapshot": {
            "equity": current.get("equity"),
            "cash": current.get("cash"),
            "market_value": current.get("market_value"),
            "positions_open": current.get("positions_open"),
            "signals_eligible": current.get("signals_eligible"),
            "orders_created": current.get("orders_created"),
        },
        "safety": {
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "auto_mode_switch_enabled": False,
            "manual_arm_required": True,
            "fail_closed": True,
        },
    }

    write_outputs(result, current_checks, streak_days)

    # Observation is healthy and should not fail the workflow.
    return 0 if status == "PASS" else 1


def write_outputs(result, checks, streak_days):
    (ROOT / "phase28_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    state = result.get("release_state", "BLOCKED")
    if state == "ARMED_FOR_PRODUCTION_PAPER":
        state_icon = "🟢"
    elif state in {"READY_FOR_PRODUCTION_PAPER", "OBSERVATION"}:
        state_icon = "🟡" if state == "OBSERVATION" else "🟢"
    else:
        state_icon = "🔴"

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 2.8",
        "",
        "## Production Readiness + Controlled Go-Live",
        "",
        f"- Status: **{result.get('status')}**",
        f"- Release state: **{state_icon} {state}**",
        f"- Requested action: `{result.get('requested_action', 'readiness_check')}`",
        f"- Strategy: `{result.get('strategy_version', STRATEGY_VERSION)}`",
        f"- Safety mode: `{result.get('mode', MODE)}`",
        f"- Consecutive PASS days: **{result.get('consecutive_pass_days', 0)} / {result.get('required_consecutive_pass_days', REQUIRED_PASS_DAYS)}**",
        f"- Latest market date: `{result.get('latest_market_date')}`",
        f"- Market stale days: `{result.get('market_stale_days')}`",
        "",
        "### Readiness Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]

    for name, ok in checks.items():
        lines.append(f"| `{name}` | {'✅ PASS' if ok else '❌ FAIL'} |")

    lines += [
        "",
        "### Safety Controls",
        "",
        "- Broker execution: **DISABLED**",
        "- Real-money execution: **DISABLED**",
        "- Automatic mode switch: **DISABLED**",
        "- Manual arm required: **YES**",
        "- Fail-closed: **YES**",
        "",
        "### Observation Streak",
        "",
    ]

    if streak_days:
        for day in streak_days:
            lines.append(f"- ✅ `{day}`")
    else:
        lines.append("- No valid PASS streak yet.")

    lines += [
        "",
        "> Phase 2.8 can authorize Production PAPER readiness only. "
        "It does not connect a broker and does not enable real-money trading.",
    ]

    (ROOT / "phase28_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    if result.get("release_state") == "ARMED_FOR_PRODUCTION_PAPER":
        manifest = {
            "release_id": f"phase28-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "release_state": "ARMED_FOR_PRODUCTION_PAPER",
            "strategy_version": STRATEGY_VERSION,
            "mode": MODE,
            "armed_at": datetime.now(timezone.utc).isoformat(),
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "required_pass_days": REQUIRED_PASS_DAYS,
            "observed_pass_days": result.get("consecutive_pass_days", 0),
        }
        (ROOT / "phase28_release_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
