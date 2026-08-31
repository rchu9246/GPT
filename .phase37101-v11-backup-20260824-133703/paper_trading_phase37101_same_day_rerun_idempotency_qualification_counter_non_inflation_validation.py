#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE37101_SAME_DAY_RERUN_IDEMPOTENCY_QUALIFICATION_COUNTER_NON_INFLATION_VALIDATION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False
QUALIFICATION_COUNTER_INFLATION_ALLOWED = False

def env_first(*names: str) -> Optional[str]:
    for name in names:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

def request(method: str, path: str) -> Any:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e

def b(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE", "YES", "Y", "1", "PASS", "ENABLED"}

def qualification_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "cycle_date,cycle_state,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request("GET", f"{QUALIFICATION_TABLE}?{q}") or []
    dates = [str(r.get("cycle_date")) for r in rows if r.get("cycle_date")]
    observed = len(rows)
    valid = sum(1 for r in rows if b(r.get("valid_cycle")))
    blocked = sum(1 for r in rows if b(r.get("blocked_cycle")))
    distinct = len(set(dates))
    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": distinct,
        "cycle_dates": dates,
        "duplicate_rows": observed - distinct,
    }

def readiness_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "readiness_date,promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = request("GET", f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main() -> int:
    art = Path("artifacts/phase37101")
    art.mkdir(parents=True, exist_ok=True)

    current = qualification_snapshot()
    readiness = readiness_snapshot()

    observed = int(current["observed"])
    valid = int(current["valid"])
    blocked = int(current["blocked"])
    distinct = int(current["distinct_cycle_dates"])
    duplicate_rows = int(current["duplicate_rows"])

    same_day_idempotent = observed == distinct
    counter_non_inflated = duplicate_rows == 0

    readiness_observed = int(readiness.get("observed_cycles", observed) or 0)
    readiness_valid = int(readiness.get("valid_cycles", valid) or 0)
    readiness_blocked = int(readiness.get("blocked_cycles", blocked) or 0)

    readiness_consistent = (
        readiness_observed == observed
        and readiness_valid == valid
        and readiness_blocked == blocked
    )

    blockers = []
    if not same_day_idempotent:
        blockers.append("SAME_DAY_DUPLICATE_EVIDENCE_DETECTED")
    if not counter_non_inflated:
        blockers.append(f"QUALIFICATION_COUNTER_INFLATION:{duplicate_rows}")
    if readiness and not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")

    if blockers:
        state = "SAME_DAY_IDEMPOTENCY_VALIDATION_BLOCKED"
        operational = False
    else:
        state = "SAME_DAY_IDEMPOTENCY_VALIDATED"
        operational = True

    result = {
        "contract": CONTRACT,
        "state": state,
        "operational": operational,
        "qualification": current,
        "readiness": readiness,
        "checks": {
            "same_day_idempotent": same_day_idempotent,
            "qualification_counter_non_inflated": counter_non_inflated,
            "readiness_counter_consistent": readiness_consistent,
        },
        "blockers": blockers,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
            "same_day_duplicate_bypass_allowed": SAME_DAY_DUPLICATE_BYPASS_ALLOWED,
            "qualification_counter_inflation_allowed": QUALIFICATION_COUNTER_INFLATION_ALLOWED,
        },
    }

    (art / "phase37101_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.10.1",
        "",
        "## Same-Day Re-Run Idempotency + Qualification Counter Non-Inflation Validation",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        "",
        "## Canonical Qualification Counters",
        "",
        f"- Observed Cycles: **{observed}**",
        f"- Valid Cycles: **{valid}**",
        f"- Blocked Cycles: **{blocked}**",
        f"- Distinct Cycle Dates: **{distinct}**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        "",
        "## Validation Checks",
        "",
        f"- Same-Day Re-Run Idempotent: **{'PASS' if same_day_idempotent else 'FAIL'}**",
        f"- Qualification Counter Non-Inflation: **{'PASS' if counter_non_inflated else 'FAIL'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "- Same-Day Duplicate Bypass: **NO**",
        "- Qualification Counter Inflation Allowed: **NO**",
    ]
    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{x}**" for x in blockers]

    (art / "phase37101_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {observed}")
    print(f"Valid Cycles: {valid}")
    print(f"Blocked Cycles: {blocked}")
    print(f"Distinct Cycle Dates: {distinct}")
    print(f"Duplicate Rows: {duplicate_rows}")
    print(f"Same-Day Re-Run Idempotent: {'PASS' if same_day_idempotent else 'FAIL'}")
    print(f"Qualification Counter Non-Inflation: {'PASS' if counter_non_inflated else 'FAIL'}")
    print(f"Readiness Counter Consistency: {'PASS' if readiness_consistent else 'FAIL'}")

    return 1 if blockers else 0

if __name__ == "__main__":
    raise SystemExit(main())
