#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE37111_QUALIFICATION_WAITING_STATE_INTEGRITY_CROSS_DAY_ROLLOVER_GUARD"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MAX_BLOCKED = 0
MIN_DISTINCT_DATES = 3

ART_DIR = Path("artifacts/phase37111")
BASELINE_PATH = ART_DIR / "baseline_snapshot.json"
RESULT_PATH = ART_DIR / "phase37111_result.json"
SUMMARY_PATH = ART_DIR / "phase37111_summary.md"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
SAME_DAY_COUNTER_ADVANCE_ALLOWED = False
CROSS_DAY_ADVANCE_WITHOUT_NEW_DATE_ALLOWED = False
QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False

def env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip().rstrip("/")
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
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"TRUE", "YES", "Y", "1", "PASS", "ENABLED"}

def qualification_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "cycle_date,cycle_state,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request("GET", f"{QUALIFICATION_TABLE}?{q}") or []

    cycle_dates = [str(row.get("cycle_date")) for row in rows if row.get("cycle_date")]
    distinct_dates = sorted(set(cycle_dates))
    observed = len(rows)
    valid = sum(1 for row in rows if truthy(row.get("valid_cycle")))
    blocked = sum(1 for row in rows if truthy(row.get("blocked_cycle")))
    duplicate_rows = observed - len(distinct_dates)
    runtime_pass = observed > 0 and all(truthy(row.get("runtime_supervision_pass")) for row in rows)
    paper_only_pass = observed > 0 and all(truthy(row.get("paper_only_boundary_pass")) for row in rows)

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": len(distinct_dates),
        "cycle_dates": cycle_dates,
        "distinct_dates": distinct_dates,
        "latest_cycle_date": distinct_dates[-1] if distinct_dates else None,
        "duplicate_rows": duplicate_rows,
        "runtime_supervision_pass": runtime_pass,
        "paper_only_boundary_pass": paper_only_pass,
    }

def readiness_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": (
            "readiness_date,qualification_state,promotion_readiness_state,promotion_ready,"
            "observed_cycles,valid_cycles,blocked_cycles,runtime_supervision_pass,"
            "paper_only_boundary_pass,broker_order_submission_enabled,"
            "real_money_trading_enabled,historical_rewrite_allowed"
        ),
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = request("GET", f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def capture_baseline() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "qualification": qualification_snapshot(),
        "readiness": readiness_snapshot(),
    }
    BASELINE_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    q = snapshot["qualification"]
    print("Baseline captured.")
    print(f"Observed: {q['observed']}")
    print(f"Valid: {q['valid']}")
    print(f"Blocked: {q['blocked']}")
    print(f"Distinct Cycle Dates: {q['distinct_cycle_dates']}")
    print(f"Latest Cycle Date: {q['latest_cycle_date']}")
    return 0

def validate_waiting_state() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise RuntimeError("BASELINE_SNAPSHOT_MISSING")

    baseline_doc = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline = baseline_doc["qualification"]
    current = qualification_snapshot()
    readiness = readiness_snapshot()

    baseline_dates = set(baseline.get("distinct_dates", []))
    current_dates = set(current.get("distinct_dates", []))
    added_dates = sorted(current_dates - baseline_dates)

    observed_delta = int(current["observed"]) - int(baseline["observed"])
    valid_delta = int(current["valid"]) - int(baseline["valid"])
    blocked_delta = int(current["blocked"]) - int(baseline["blocked"])
    distinct_delta = int(current["distinct_cycle_dates"]) - int(baseline["distinct_cycle_dates"])

    new_distinct_date_present = distinct_delta > 0 and len(added_dates) == distinct_delta

    same_day_no_inflation = (
        distinct_delta == 0
        and observed_delta == 0
        and valid_delta == 0
        and blocked_delta == 0
    )

    cross_day_rollover_valid = (
        distinct_delta == 1
        and observed_delta == 1
        and valid_delta in {0, 1}
        and blocked_delta in {0, 1}
        and new_distinct_date_present
        and int(current["duplicate_rows"]) == 0
    )

    no_multi_cycle_jump = (
        observed_delta <= 1
        and valid_delta <= 1
        and distinct_delta <= 1
    )

    readiness_consistent = True
    if readiness:
        readiness_consistent = (
            int(readiness.get("observed_cycles", current["observed"]) or 0) == int(current["observed"])
            and int(readiness.get("valid_cycles", current["valid"]) or 0) == int(current["valid"])
            and int(readiness.get("blocked_cycles", current["blocked"]) or 0) == int(current["blocked"])
        )

    broker_locked = not truthy(readiness.get("broker_order_submission_enabled", False)) if readiness else True
    real_money_locked = not truthy(readiness.get("real_money_trading_enabled", False)) if readiness else True
    historical_rewrite_locked = not truthy(readiness.get("historical_rewrite_allowed", False)) if readiness else True

    threshold_met = (
        int(current["observed"]) >= MIN_OBSERVED
        and int(current["valid"]) >= MIN_VALID
        and int(current["blocked"]) <= MAX_BLOCKED
        and int(current["distinct_cycle_dates"]) >= MIN_DISTINCT_DATES
        and int(current["duplicate_rows"]) == 0
        and bool(current["runtime_supervision_pass"])
        and bool(current["paper_only_boundary_pass"])
    )

    readiness_state = str(readiness.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()
    readiness_ready = truthy(readiness.get("promotion_ready", False))

    waiting_state_integrity = (
        (not threshold_met and not readiness_ready)
        or threshold_met
    )

    blockers = []

    if int(current["duplicate_rows"]) > 0:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if not no_multi_cycle_jump:
        blockers.append("MULTI_CYCLE_COUNTER_JUMP_DETECTED")
    if distinct_delta == 0 and not same_day_no_inflation:
        blockers.append("SAME_DAY_COUNTER_ADVANCE_DETECTED")
    if distinct_delta > 0 and not cross_day_rollover_valid:
        blockers.append("CROSS_DAY_ROLLOVER_INTEGRITY_FAILED")
    if not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if not waiting_state_integrity:
        blockers.append("PROMOTION_READY_BEFORE_CANONICAL_THRESHOLD")
    if not broker_locked:
        blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked:
        blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_rewrite_locked:
        blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "QUALIFICATION_WAITING_STATE_INTEGRITY_BLOCKED"
        operational = False
    elif threshold_met and readiness_ready:
        state = "QUALIFICATION_ROLLOVER_THRESHOLD_REACHED"
        operational = True
    elif cross_day_rollover_valid:
        state = "QUALIFICATION_CROSS_DAY_ROLLOVER_VALIDATED"
        operational = True
    else:
        state = "QUALIFICATION_WAITING_STATE_INTEGRITY_VALIDATED"
        operational = True

    result = {
        "contract": CONTRACT,
        "state": state,
        "operational": operational,
        "baseline": baseline,
        "current": current,
        "readiness": readiness,
        "rollover": {
            "observed_delta": observed_delta,
            "valid_delta": valid_delta,
            "blocked_delta": blocked_delta,
            "distinct_date_delta": distinct_delta,
            "added_dates": added_dates,
            "same_day_no_inflation": same_day_no_inflation,
            "cross_day_rollover_valid": cross_day_rollover_valid,
            "no_multi_cycle_jump": no_multi_cycle_jump,
        },
        "checks": {
            "readiness_counter_consistent": readiness_consistent,
            "waiting_state_integrity": waiting_state_integrity,
            "canonical_threshold_met": threshold_met,
            "broker_locked": broker_locked,
            "real_money_locked": real_money_locked,
            "historical_rewrite_locked": historical_rewrite_locked,
        },
        "blockers": blockers,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
            "same_day_counter_advance_allowed": SAME_DAY_COUNTER_ADVANCE_ALLOWED,
            "cross_day_advance_without_new_date_allowed": CROSS_DAY_ADVANCE_WITHOUT_NEW_DATE_ALLOWED,
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.11.1",
        "",
        "## Qualification Waiting-State Integrity + Cross-Day Rollover Guard",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        "",
        "## Baseline → Current",
        "",
        f"- Observed Cycles: **{baseline['observed']} → {current['observed']}**",
        f"- Valid Cycles: **{baseline['valid']} → {current['valid']}**",
        f"- Blocked Cycles: **{baseline['blocked']} → {current['blocked']}**",
        f"- Distinct Cycle Dates: **{baseline['distinct_cycle_dates']} → {current['distinct_cycle_dates']}**",
        f"- Added Distinct Dates: **{', '.join(added_dates) if added_dates else 'NONE'}**",
        "",
        "## Rollover Guard",
        "",
        f"- Same-Day Counter Non-Inflation: **{'PASS' if same_day_no_inflation or distinct_delta > 0 else 'FAIL'}**",
        f"- Cross-Day Rollover Integrity: **{'PASS' if cross_day_rollover_valid or distinct_delta == 0 else 'FAIL'}**",
        f"- Multi-Cycle Jump Guard: **{'PASS' if no_multi_cycle_jump else 'FAIL'}**",
        f"- Duplicate Rows: **{current['duplicate_rows']}**",
        "",
        "## Qualification / Readiness",
        "",
        f"- Canonical Threshold Met: **{'YES' if threshold_met else 'NO'}**",
        f"- Readiness State: **{readiness_state}**",
        f"- Promotion Ready: **{'YES' if readiness_ready else 'NO'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
        "",
        "## Safety Lock",
        "",
        f"- Broker Order Submission Locked: **{'PASS' if broker_locked else 'FAIL'}**",
        f"- Real-Money Trading Locked: **{'PASS' if real_money_locked else 'FAIL'}**",
        f"- Historical Rewrite Locked: **{'PASS' if historical_rewrite_locked else 'FAIL'}**",
        "",
        "## Permanent Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "- Same-Day Counter Advance Allowed: **NO**",
        "- Cross-Day Advance Without New Date Allowed: **NO**",
        "- Qualification Threshold Bypass: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed: {baseline['observed']} -> {current['observed']}")
    print(f"Valid: {baseline['valid']} -> {current['valid']}")
    print(f"Blocked: {baseline['blocked']} -> {current['blocked']}")
    print(f"Distinct Dates: {baseline['distinct_cycle_dates']} -> {current['distinct_cycle_dates']}")
    print(f"Added Dates: {added_dates if added_dates else 'NONE'}")
    print(f"Same-Day Non-Inflation: {'PASS' if same_day_no_inflation or distinct_delta > 0 else 'FAIL'}")
    print(f"Cross-Day Rollover Integrity: {'PASS' if cross_day_rollover_valid or distinct_delta == 0 else 'FAIL'}")
    print(f"Multi-Cycle Jump Guard: {'PASS' if no_multi_cycle_jump else 'FAIL'}")

    return 0 if operational else 1

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "validate"], required=True)
    args = parser.parse_args()

    if args.mode == "baseline":
        return capture_baseline()
    return validate_waiting_state()

if __name__ == "__main__":
    raise SystemExit(main())
