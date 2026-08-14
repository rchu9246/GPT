#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 2.9
Production Paper Trading Operations

Safety:
- SHADOW_ONLY_NO_BROKER is mandatory.
- Broker execution is disabled.
- Real-money trading is disabled.
- Fail-closed on unhealthy upstream state.
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

VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = os.getenv("PAPER_TRADING_MODE", "SHADOW_ONLY_NO_BROKER")

REQUIRED_PASS_DAYS = max(1, int(os.getenv("PHASE29_REQUIRED_PASS_DAYS", "5")))
MAX_STALE_DAYS = max(0, int(os.getenv("PHASE29_MAX_MARKET_STALE_DAYS", "3")))
MAX_OPEN_POSITIONS = max(0, int(os.getenv("PHASE29_MAX_OPEN_POSITIONS", "10")))
MIN_EQUITY = float(os.getenv("PHASE29_MIN_EQUITY", "0"))
MAX_DAILY_DRAWDOWN = float(os.getenv("PHASE29_MAX_DAILY_DRAWDOWN", "0.08"))


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
            "strategy_version": f"eq.{VERSION}",
            "mode": f"eq.{MODE}",
            "order": "run_date.desc,completed_at.desc",
            "limit": str(max(REQUIRED_PASS_DAYS * 6, 40)),
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
        d = str(row.get("run_date") or "")[:10]
        if not d or d in seen:
            continue
        seen.add(d)
        daily.append(row)
    return daily


def health_for(row):
    run_day = parse_day(row.get("run_date"))
    market_day = parse_day(row.get("latest_market_date"))
    stale_days = (run_day - market_day).days if run_day and market_day else None

    checks = {
        "status_completed": row.get("status") == "COMPLETED",
        "pipeline_completed": row.get("pipeline_status") == "COMPLETED",
        "latest_market_date_present": market_day is not None,
        "market_data_fresh": market_day is not None and stale_days is not None and stale_days <= MAX_STALE_DAYS,
        "equity_non_negative": as_float(row.get("equity")) >= MIN_EQUITY,
        "positions_within_limit": 0 <= as_int(row.get("positions_open")) <= MAX_OPEN_POSITIONS,
    }

    raw = row.get("raw_summary")
    if isinstance(raw, dict):
        integrity = raw.get("integrity_checks")
        if isinstance(integrity, dict) and integrity:
            checks["phase26_integrity_all_pass"] = all(bool(v) for v in integrity.values())

    return checks, stale_days


def compute_streak(daily):
    streak = 0
    dates = []
    for row in daily:
        checks, _ = health_for(row)
        if all(checks.values()):
            streak += 1
            dates.append(str(row.get("run_date"))[:10])
        else:
            break
    return streak, dates


def calc_daily_drawdown(daily):
    if len(daily) < 2:
        return 0.0
    today_eq = as_float(daily[0].get("equity"))
    prev_eq = as_float(daily[1].get("equity"))
    if prev_eq <= 0:
        return 0.0
    return max(0.0, (prev_eq - today_eq) / prev_eq)


def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety lock: Phase 2.9 requires PAPER_TRADING_MODE=SHADOW_ONLY_NO_BROKER"
        )

    rows = load_snapshots()
    daily = one_per_day(rows)

    if not daily:
        result = {
            "version": "2.9",
            "status": "BLOCKED",
            "system_health": "FAIL",
            "operations_state": "LOCKED",
            "reason": "NO_DAILY_SNAPSHOTS",
            "broker_execution_enabled": False,
            "real_money_enabled": False,
        }
        write_outputs(result, {}, [])
        return 1

    current = daily[0]
    checks, stale_days = health_for(current)
    streak, streak_dates = compute_streak(daily)
    drawdown = calc_daily_drawdown(daily)

    risk_checks = {
        "daily_drawdown_within_limit": drawdown <= MAX_DAILY_DRAWDOWN,
        "gross_safety_mode_locked": MODE == "SHADOW_ONLY_NO_BROKER",
    }

    all_checks = {**checks, **risk_checks}
    healthy = all(all_checks.values())

    if not healthy:
        phase28_gate = "BLOCKED"
        operations_state = "LOCKED"
        status = "FAIL"
        reason = "HEALTH_OR_RISK_CHECK_FAILED"
    elif streak < REQUIRED_PASS_DAYS:
        phase28_gate = "OBSERVATION"
        operations_state = "LOCKED"
        status = "PASS"
        reason = "OBSERVATION_PERIOD_ACTIVE"
    else:
        phase28_gate = "READY_FOR_PRODUCTION_PAPER"
        operations_state = "READY"
        status = "PASS"
        reason = "PRODUCTION_PAPER_OPERATIONS_READY"

    result = {
        "version": "2.9",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "strategy_version": VERSION,
        "mode": MODE,
        "status": status,
        "system_health": "PASS" if healthy else "FAIL",
        "phase28_gate": phase28_gate,
        "operations_state": operations_state,
        "reason": reason,
        "required_consecutive_pass_days": REQUIRED_PASS_DAYS,
        "consecutive_pass_days": streak,
        "streak_dates": streak_dates,
        "latest_market_date": current.get("latest_market_date"),
        "market_stale_days": stale_days,
        "daily_drawdown": round(drawdown, 6),
        "checks": all_checks,
        "ledger": {
            "run_key": current.get("run_key"),
            "cash": current.get("cash"),
            "market_value": current.get("market_value"),
            "equity": current.get("equity"),
            "realized_pnl": current.get("realized_pnl"),
            "unrealized_pnl": current.get("unrealized_pnl"),
            "positions_open": current.get("positions_open"),
            "signals_eligible": current.get("signals_eligible"),
            "orders_created": current.get("orders_created"),
        },
        "safety": {
            "production_paper_locked": operations_state != "READY",
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "kill_switch": "ARMED",
            "fail_closed": True,
        },
    }

    write_outputs(result, all_checks, streak_dates)
    return 0 if status == "PASS" else 1


def write_outputs(result, checks, streak_dates):
    (ROOT / "phase29_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    state = result.get("operations_state", "LOCKED")
    state_icon = "🟢" if state == "READY" else "🟡" if result.get("status") == "PASS" else "🔴"

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 2.9",
        "",
        "## Production Paper Trading Operations",
        "",
        f"- System Health: **{result.get('system_health')}**",
        f"- Phase 2.8 Gate: **{result.get('phase28_gate')}**",
        f"- Operations State: **{state_icon} {state}**",
        f"- Strategy: `{result.get('strategy_version', VERSION)}`",
        f"- Trading Mode: `{result.get('mode', MODE)}`",
        f"- Consecutive PASS days: **{result.get('consecutive_pass_days', 0)} / {result.get('required_consecutive_pass_days', REQUIRED_PASS_DAYS)}**",
        f"- Latest market date: `{result.get('latest_market_date')}`",
        f"- Market stale days: `{result.get('market_stale_days')}`",
        f"- Daily drawdown: `{result.get('daily_drawdown')}`",
        "",
        "### Operations Health",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| `{name}` | {'✅ PASS' if ok else '❌ FAIL'} |")

    ledger = result.get("ledger", {})
    lines += [
        "",
        "### Production Paper Ledger",
        "",
        f"- Run key: `{ledger.get('run_key')}`",
        f"- Cash: `{ledger.get('cash')}`",
        f"- Market value: `{ledger.get('market_value')}`",
        f"- Equity: `{ledger.get('equity')}`",
        f"- Realized P&L: `{ledger.get('realized_pnl')}`",
        f"- Unrealized P&L: `{ledger.get('unrealized_pnl')}`",
        f"- Positions open: `{ledger.get('positions_open')}`",
        f"- Signals eligible: `{ledger.get('signals_eligible')}`",
        f"- Orders created: `{ledger.get('orders_created')}`",
        "",
        "### Safety Controls",
        "",
        f"- Production Paper: **{'UNLOCKED' if state == 'READY' else 'LOCKED'}**",
        "- Broker Trading: **DISABLED**",
        "- Real Money: **DISABLED**",
        "- Kill Switch: **ARMED**",
        "- Fail Closed: **YES**",
        "",
        "### Observation Streak",
        "",
    ]

    if streak_dates:
        for d in streak_dates:
            lines.append(f"- ✅ `{d}`")
    else:
        lines.append("- No valid PASS streak yet.")

    lines += [
        "",
        "> Phase 2.9 operates only on Production PAPER readiness. "
        "It does not connect a broker and does not enable real-money trading.",
    ]

    (ROOT / "phase29_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
