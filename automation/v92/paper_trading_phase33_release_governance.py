#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.3
Production Promotion + Release Governance

Purpose:
- Read the current Phase 3.2 qualification state from the existing daily snapshots.
- Evaluate promotion eligibility.
- Require explicit human approval before a release can be marked APPROVED.
- Produce release-governance artifacts and an audit-friendly summary.
- Never enable broker execution or real-money trading.

Safety:
- SHADOW_ONLY_NO_BROKER is mandatory.
- Broker execution remains disabled.
- Real-money execution remains disabled.
- Promotion is governance metadata only.
"""

from __future__ import annotations

import json
import os
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

ACTION = os.getenv("PHASE33_ACTION", "evaluate")
APPROVAL_TOKEN = os.getenv("PHASE33_APPROVAL_TOKEN", "").strip()

REQUIRED_PASS_DAYS = max(1, int(os.getenv("PHASE33_REQUIRED_PASS_DAYS", "5")))
MAX_STALE_DAYS = max(0, int(os.getenv("PHASE33_MAX_MARKET_STALE_DAYS", "3")))
MAX_DAILY_DRAWDOWN = float(os.getenv("PHASE33_MAX_DAILY_DRAWDOWN", "0.03"))
MAX_OPEN_POSITIONS = max(0, int(os.getenv("PHASE33_MAX_OPEN_POSITIONS", "10")))

SNAPSHOT_TABLE = os.getenv("PHASE33_SNAPSHOT_TABLE", "gptq_paper_daily_snapshots")

ALLOWED_ACTIONS = {"evaluate", "approve_release", "reject_release"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def request(method: str, table: str, query: str = ""):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url += "?" + query

    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {body}") from exc


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


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


def load_snapshots(limit=40):
    query = urllib.parse.urlencode(
        {
            "strategy_version": f"eq.{STRATEGY_VERSION}",
            "mode": f"eq.{MODE}",
            "order": "run_date.desc,completed_at.desc",
            "limit": str(limit),
        }
    )
    rows = request("GET", SNAPSHOT_TABLE, query)
    return rows if isinstance(rows, list) else []


def one_per_day(rows):
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        run_day = str(row.get("run_date") or "")[:10]
        if not run_day or run_day in seen:
            continue
        seen.add(run_day)
        result.append(row)
    return result


def status_pass(row):
    status = str(
        row.get("status")
        or row.get("pipeline_status")
        or row.get("pipeline")
        or ""
    ).upper()
    return status in {"COMPLETED", "PASS", "PASSED", "SUCCESS"}


def market_stale_days(row):
    run_day = parse_date(row.get("run_date"))
    market_day = parse_date(row.get("latest_market_date"))
    if not run_day or not market_day:
        return None
    return max(0, (run_day - market_day).days)


def row_checks(row):
    stale = market_stale_days(row)
    return {
        "snapshot_pass": status_pass(row),
        "market_date_present": parse_date(row.get("latest_market_date")) is not None,
        "market_data_fresh": stale is not None and stale <= MAX_STALE_DAYS,
        "equity_non_negative": as_float(row.get("equity")) >= 0,
        "positions_within_limit": 0 <= as_int(row.get("positions_open")) <= MAX_OPEN_POSITIONS,
    }


def consecutive_pass_days(rows):
    count = 0
    dates = []
    for row in one_per_day(rows):
        checks = row_checks(row)
        if all(checks.values()):
            count += 1
            dates.append(str(row.get("run_date"))[:10])
        else:
            break
    return count, dates


def daily_drawdown(rows):
    daily = one_per_day(rows)
    if len(daily) < 2:
        return 0.0
    current = as_float(daily[0].get("equity"))
    previous = as_float(daily[1].get("equity"))
    if previous <= 0:
        return 0.0
    return max(0.0, (previous - current) / previous)


def approval_present():
    # This is intentionally simple:
    # a human must explicitly provide a non-empty token/value through workflow input.
    return bool(APPROVAL_TOKEN)


def build_result(rows):
    daily = one_per_day(rows)
    if not daily:
        return {
            "version": "3.3",
            "checked_at": now_iso(),
            "status": "FAIL",
            "promotion_state": "BLOCKED",
            "release_state": "LOCKED",
            "reason": "NO_DAILY_SNAPSHOTS",
            "checks": {},
            "safety": {
                "broker_execution_enabled": False,
                "real_money_enabled": False,
            },
        }

    current = daily[0]
    streak, streak_dates = consecutive_pass_days(rows)
    drawdown = daily_drawdown(rows)
    stale = market_stale_days(current)

    checks = row_checks(current)
    checks.update(
        {
            "safety_mode_locked": MODE == "SHADOW_ONLY_NO_BROKER",
            "drawdown_within_limit": drawdown <= MAX_DAILY_DRAWDOWN,
            "consecutive_pass_requirement": streak >= REQUIRED_PASS_DAYS,
        }
    )

    qualified = all(checks.values())

    if not qualified:
        promotion_state = "OBSERVATION"
        release_state = "LOCKED"
        status = "PASS" if all(
            v for k, v in checks.items() if k != "consecutive_pass_requirement"
        ) else "FAIL"
        reason = "WAITING_FOR_PROMOTION_REQUIREMENTS"
    else:
        promotion_state = "QUALIFIED"
        release_state = "AWAITING_HUMAN_APPROVAL"
        status = "PASS"
        reason = "PROMOTION_REQUIREMENTS_SATISFIED"

    if ACTION == "approve_release":
        if not qualified:
            release_state = "LOCKED"
            status = "FAIL"
            reason = "APPROVAL_REJECTED_NOT_QUALIFIED"
        elif not approval_present():
            release_state = "AWAITING_HUMAN_APPROVAL"
            status = "FAIL"
            reason = "APPROVAL_TOKEN_MISSING"
        else:
            release_state = "APPROVED_FOR_PRODUCTION_PAPER"
            status = "PASS"
            reason = "HUMAN_APPROVAL_ACCEPTED"

    elif ACTION == "reject_release":
        release_state = "REJECTED"
        status = "PASS"
        reason = "HUMAN_REJECTION_RECORDED"

    return {
        "version": "3.3",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY_VERSION,
        "mode": MODE,
        "requested_action": ACTION,
        "status": status,
        "promotion_state": promotion_state,
        "release_state": release_state,
        "reason": reason,
        "required_consecutive_pass_days": REQUIRED_PASS_DAYS,
        "consecutive_pass_days": streak,
        "streak_dates": streak_dates,
        "latest_market_date": current.get("latest_market_date"),
        "market_stale_days": stale,
        "daily_drawdown": round(drawdown, 6),
        "checks": checks,
        "current_snapshot": {
            "run_key": current.get("run_key"),
            "run_date": current.get("run_date"),
            "equity": current.get("equity"),
            "cash": current.get("cash"),
            "market_value": current.get("market_value"),
            "positions_open": current.get("positions_open"),
            "signals_eligible": current.get("signals_eligible"),
            "orders_created": current.get("orders_created"),
        },
        "governance": {
            "human_approval_required": True,
            "approval_present": approval_present(),
            "automatic_release_enabled": False,
            "audit_artifact_required": True,
        },
        "safety": {
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "automatic_mode_switch_enabled": False,
            "kill_switch": "ARMED",
            "fail_closed": True,
        },
    }


def write_summary(result):
    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.3",
        "",
        "## Production Promotion + Release Governance",
        "",
        f"- Status: **{result.get('status')}**",
        f"- Promotion State: **{result.get('promotion_state')}**",
        f"- Release State: **{result.get('release_state')}**",
        f"- Requested Action: `{result.get('requested_action', ACTION)}`",
        f"- Strategy: `{result.get('strategy_version', STRATEGY_VERSION)}`",
        f"- Trading Mode: `{result.get('mode', MODE)}`",
        f"- Consecutive PASS days: **{result.get('consecutive_pass_days', 0)} / {result.get('required_consecutive_pass_days', REQUIRED_PASS_DAYS)}**",
        f"- Latest market date: `{result.get('latest_market_date')}`",
        f"- Market stale days: `{result.get('market_stale_days')}`",
        f"- Daily drawdown: `{result.get('daily_drawdown')}`",
        "",
        "### Promotion Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]

    for name, ok in (result.get("checks") or {}).items():
        lines.append(f"| `{name}` | {'✅ PASS' if ok else '🟡 WAIT / ❌ FAIL'} |")

    gov = result.get("governance") or {}
    lines += [
        "",
        "### Release Governance",
        "",
        f"- Human approval required: **{gov.get('human_approval_required', True)}**",
        f"- Approval present: **{gov.get('approval_present', False)}**",
        "- Automatic release: **DISABLED**",
        "- Broker Trading: **DISABLED**",
        "- Real Money: **DISABLED**",
        "- Kill Switch: **ARMED**",
        "",
        "> Phase 3.3 only governs promotion and Production PAPER release approval. "
        "It does not connect a broker and does not enable real-money execution.",
    ]

    (ROOT / "phase33_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def write_release_manifest(result):
    if result.get("release_state") != "APPROVED_FOR_PRODUCTION_PAPER":
        return

    manifest = {
        "release_id": f"phase33-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "approved_at": now_iso(),
        "release_state": result["release_state"],
        "promotion_state": result["promotion_state"],
        "strategy_version": result["strategy_version"],
        "mode": result["mode"],
        "consecutive_pass_days": result["consecutive_pass_days"],
        "latest_market_date": result["latest_market_date"],
        "broker_execution_enabled": False,
        "real_money_enabled": False,
        "automatic_mode_switch_enabled": False,
    }

    (ROOT / "phase33_release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    if ACTION not in ALLOWED_ACTIONS:
        raise RuntimeError(f"Unsupported PHASE33_ACTION: {ACTION}")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety lock: Phase 3.3 requires PAPER_TRADING_MODE=SHADOW_ONLY_NO_BROKER"
        )

    rows = load_snapshots()
    result = build_result(rows)

    (ROOT / "phase33_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_summary(result)
    write_release_manifest(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Observation/evaluation is a valid state.
    if result.get("status") == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
