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

CONTRACT = "PHASE37121_NATURAL_CROSS_DAY_QUALIFICATION_OBSERVATION_EVIDENCE_INTEGRITY_AUDIT"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

ART_DIR = Path("artifacts/phase37121")
BASELINE_PATH = ART_DIR / "baseline_snapshot.json"
RESULT_PATH = ART_DIR / "phase37121_result.json"
SUMMARY_PATH = ART_DIR / "phase37121_summary.md"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
EVIDENCE_SYNTHESIS_ALLOWED = False
CYCLE_DATE_BACKFILL_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
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
    runtime_pass = observed > 0 and all(truthy(row.get("runtime_supervision_pass")) for row in rows)
    paper_only_pass = observed > 0 and all(truthy(row.get("paper_only_boundary_pass")) for row in rows)

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": len(distinct_dates),
        "duplicate_rows": observed - len(distinct_dates),
        "distinct_dates": distinct_dates,
        "latest_cycle_date": distinct_dates[-1] if distinct_dates else None,
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

def save_baseline() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "qualification": qualification_snapshot(),
        "readiness": readiness_snapshot(),
    }
    BASELINE_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    q = snapshot["qualification"]
    print("Natural observation baseline saved.")
    print(f"Observed Cycles: {q['observed']}")
    print(f"Valid Cycles: {q['valid']}")
    print(f"Blocked Cycles: {q['blocked']}")
    print(f"Distinct Cycle Dates: {q['distinct_cycle_dates']}")
    print(f"Latest Cycle Date: {q['latest_cycle_date']}")
    return 0

def audit() -> int:
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

    no_change = (
        observed_delta == 0
        and valid_delta == 0
        and blocked_delta == 0
        and distinct_delta == 0
    )

    single_natural_rollover = (
        observed_delta == 1
        and distinct_delta == 1
        and len(added_dates) == 1
        and valid_delta in {0, 1}
        and blocked_delta in {0, 1}
        and int(current["duplicate_rows"]) == 0
    )

    no_counter_jump = (
        observed_delta <= 1
        and valid_delta <= 1
        and distinct_delta <= 1
    )

    no_duplicate_evidence = int(current["duplicate_rows"]) == 0

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

    blockers = []

    if not no_counter_jump:
        blockers.append("NON_NATURAL_MULTI_COUNTER_JUMP_DETECTED")
    if not no_duplicate_evidence:
        blockers.append("DUPLICATE_QUALIFICATION_EVIDENCE_DETECTED")
    if distinct_delta < 0 or observed_delta < 0 or valid_delta < 0:
        blockers.append("HISTORICAL_COUNTER_REGRESSION_DETECTED")
    if distinct_delta > 0 and not single_natural_rollover:
        blockers.append("CROSS_DAY_EVIDENCE_INTEGRITY_FAILED")
    if not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if not broker_locked:
        blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked:
        blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_rewrite_locked:
        blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "NATURAL_CROSS_DAY_EVIDENCE_AUDIT_BLOCKED"
        operational = False
    elif single_natural_rollover:
        state = "NATURAL_CROSS_DAY_QUALIFICATION_OBSERVED"
        operational = True
    else:
        state = "NATURAL_CROSS_DAY_OBSERVATION_WAITING"
        operational = True

    result = {
        "contract": CONTRACT,
        "state": state,
        "operational": operational,
        "baseline": baseline,
        "current": current,
        "readiness": readiness,
        "observation": {
            "observed_delta": observed_delta,
            "valid_delta": valid_delta,
            "blocked_delta": blocked_delta,
            "distinct_date_delta": distinct_delta,
            "added_distinct_dates": added_dates,
            "no_change": no_change,
            "single_natural_rollover": single_natural_rollover,
            "no_counter_jump": no_counter_jump,
            "no_duplicate_evidence": no_duplicate_evidence,
        },
        "checks": {
            "readiness_counter_consistent": readiness_consistent,
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
            "evidence_synthesis_allowed": EVIDENCE_SYNTHESIS_ALLOWED,
            "cycle_date_backfill_allowed": CYCLE_DATE_BACKFILL_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.12.1",
        "",
        "## Natural Cross-Day Qualification Observation + Evidence Integrity Audit",
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
        "## Evidence Integrity Audit",
        "",
        f"- Natural Single-Day Rollover: **{'PASS' if single_natural_rollover or no_change else 'FAIL'}**",
        f"- Counter Jump Guard: **{'PASS' if no_counter_jump else 'FAIL'}**",
        f"- Duplicate Evidence Guard: **{'PASS' if no_duplicate_evidence else 'FAIL'}**",
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
        "- Evidence Synthesis Allowed: **NO**",
        "- Cycle-Date Backfill Allowed: **NO**",
        "- Manual Counter Increment Allowed: **NO**",
        "- Qualification Threshold Bypass: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {baseline['observed']} -> {current['observed']}")
    print(f"Valid Cycles: {baseline['valid']} -> {current['valid']}")
    print(f"Blocked Cycles: {baseline['blocked']} -> {current['blocked']}")
    print(f"Distinct Cycle Dates: {baseline['distinct_cycle_dates']} -> {current['distinct_cycle_dates']}")
    print(f"Added Distinct Dates: {added_dates if added_dates else 'NONE'}")
    print(f"Natural Single-Day Rollover: {'PASS' if single_natural_rollover or no_change else 'FAIL'}")
    print(f"Counter Jump Guard: {'PASS' if no_counter_jump else 'FAIL'}")
    print(f"Duplicate Evidence Guard: {'PASS' if no_duplicate_evidence else 'FAIL'}")

    return 0 if operational else 1

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "audit"], required=True)
    args = parser.parse_args()

    if args.mode == "baseline":
        return save_baseline()
    return audit()

if __name__ == "__main__":
    raise SystemExit(main())
