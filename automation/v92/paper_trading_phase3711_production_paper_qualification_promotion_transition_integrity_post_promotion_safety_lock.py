#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE3711_PRODUCTION_PAPER_QUALIFICATION_PROMOTION_TRANSITION_INTEGRITY_POST_PROMOTION_SAFETY_LOCK"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MAX_BLOCKED = 0
MIN_DISTINCT_DATES = 3

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
POST_PROMOTION_BROKER_UNLOCK_ALLOWED = False
POST_PROMOTION_REAL_MONEY_UNLOCK_ALLOWED = False
QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False

ART_DIR = Path("artifacts/phase3711")
RESULT_PATH = ART_DIR / "phase3711_result.json"
SUMMARY_PATH = ART_DIR / "phase3711_summary.md"

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

    dates = [str(row.get("cycle_date")) for row in rows if row.get("cycle_date")]
    observed = len(rows)
    valid = sum(1 for row in rows if truthy(row.get("valid_cycle")))
    blocked = sum(1 for row in rows if truthy(row.get("blocked_cycle")))
    distinct = len(set(dates))
    duplicate_rows = observed - distinct
    runtime_pass = observed > 0 and all(truthy(row.get("runtime_supervision_pass")) for row in rows)
    paper_only_pass = observed > 0 and all(truthy(row.get("paper_only_boundary_pass")) for row in rows)

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": distinct,
        "duplicate_rows": duplicate_rows,
        "runtime_supervision_pass": runtime_pass,
        "paper_only_boundary_pass": paper_only_pass,
        "cycle_dates": dates,
    }

def readiness_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": (
            "readiness_date,qualification_state,promotion_readiness_state,promotion_ready,"
            "observed_cycles,valid_cycles,blocked_cycles,runtime_supervision_pass,"
            "paper_only_boundary_pass,broker_order_submission_enabled,"
            "real_money_trading_enabled,historical_rewrite_allowed,raw_state"
        ),
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = request("GET", f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    qualification = qualification_snapshot()
    readiness = readiness_snapshot()

    observed = int(qualification["observed"])
    valid = int(qualification["valid"])
    blocked = int(qualification["blocked"])
    distinct = int(qualification["distinct_cycle_dates"])
    duplicate_rows = int(qualification["duplicate_rows"])
    runtime_pass = bool(qualification["runtime_supervision_pass"])
    paper_only_pass = bool(qualification["paper_only_boundary_pass"])

    threshold_met = (
        observed >= MIN_OBSERVED
        and valid >= MIN_VALID
        and blocked <= MAX_BLOCKED
        and distinct >= MIN_DISTINCT_DATES
        and duplicate_rows == 0
        and runtime_pass
        and paper_only_pass
    )

    readiness_present = bool(readiness)
    readiness_state = str(readiness.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()
    readiness_ready = truthy(readiness.get("promotion_ready", False))

    readiness_counts_consistent = True
    if readiness_present:
        readiness_counts_consistent = (
            int(readiness.get("observed_cycles", observed) or 0) == observed
            and int(readiness.get("valid_cycles", valid) or 0) == valid
            and int(readiness.get("blocked_cycles", blocked) or 0) == blocked
        )

    readiness_runtime_pass = truthy(readiness.get("runtime_supervision_pass", False)) if readiness_present else False
    readiness_paper_only_pass = truthy(readiness.get("paper_only_boundary_pass", False)) if readiness_present else False

    broker_enabled = truthy(readiness.get("broker_order_submission_enabled", False)) if readiness_present else False
    real_money_enabled = truthy(readiness.get("real_money_trading_enabled", False)) if readiness_present else False
    historical_rewrite = truthy(readiness.get("historical_rewrite_allowed", False)) if readiness_present else False

    post_promotion_safety_lock_pass = (
        not broker_enabled
        and not real_money_enabled
        and not historical_rewrite
    )

    transition_integrity_pass = True
    blockers = []

    if duplicate_rows > 0:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > MAX_BLOCKED:
        blockers.append(f"BLOCKED_CYCLES_PRESENT:{blocked}")
    if observed > 0 and not runtime_pass:
        blockers.append("CANONICAL_RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not paper_only_pass:
        blockers.append("CANONICAL_PAPER_ONLY_BOUNDARY_NOT_PASS")
    if readiness_present and not readiness_counts_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")

    # Transition integrity rules:
    # - Ready is forbidden before the canonical threshold is met.
    # - If Ready is declared, the readiness safety fields must still be locked.
    if readiness_ready and not threshold_met:
        transition_integrity_pass = False
        blockers.append("PROMOTION_READY_BEFORE_CANONICAL_THRESHOLD")

    if readiness_state == "PROMOTION_READINESS_READY" and not readiness_ready:
        transition_integrity_pass = False
        blockers.append("READINESS_STATE_FLAG_MISMATCH")

    if readiness_ready and not readiness_runtime_pass:
        transition_integrity_pass = False
        blockers.append("POST_PROMOTION_RUNTIME_SUPERVISION_NOT_PASS")

    if readiness_ready and not readiness_paper_only_pass:
        transition_integrity_pass = False
        blockers.append("POST_PROMOTION_PAPER_ONLY_BOUNDARY_NOT_PASS")

    if not post_promotion_safety_lock_pass:
        transition_integrity_pass = False
        blockers.append("POST_PROMOTION_SAFETY_LOCK_BREACH")

    if blockers:
        state = "PROMOTION_TRANSITION_INTEGRITY_BLOCKED"
        operational = False
    elif threshold_met and readiness_ready and readiness_state == "PROMOTION_READINESS_READY":
        state = "POST_PROMOTION_SAFETY_LOCK_VALIDATED"
        operational = True
    else:
        state = "PROMOTION_TRANSITION_INTEGRITY_ARMED_WAITING"
        operational = True

    result = {
        "contract": CONTRACT,
        "state": state,
        "operational": operational,
        "qualification": qualification,
        "readiness": readiness,
        "checks": {
            "canonical_threshold_met": threshold_met,
            "transition_integrity_pass": transition_integrity_pass,
            "readiness_counts_consistent": readiness_counts_consistent,
            "post_promotion_safety_lock_pass": post_promotion_safety_lock_pass,
            "promotion_ready": readiness_ready,
        },
        "blockers": blockers,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
            "post_promotion_broker_unlock_allowed": POST_PROMOTION_BROKER_UNLOCK_ALLOWED,
            "post_promotion_real_money_unlock_allowed": POST_PROMOTION_REAL_MONEY_UNLOCK_ALLOWED,
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
        },
    }

    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.11",
        "",
        "## Production Paper Qualification Promotion Transition Integrity + Post-Promotion Safety Lock",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        "",
        "## Canonical Qualification",
        "",
        f"- Observed Cycles: **{observed} / {MIN_OBSERVED}**",
        f"- Valid Cycles: **{valid} / {MIN_VALID}**",
        f"- Blocked Cycles: **{blocked} / {MAX_BLOCKED} max**",
        f"- Distinct Cycle Dates: **{distinct} / {MIN_DISTINCT_DATES}**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        f"- Runtime Supervision: **{'PASS' if runtime_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        f"- Paper-Only Boundary: **{'PASS' if paper_only_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        f"- Canonical Threshold Met: **{'YES' if threshold_met else 'NO'}**",
        "",
        "## Promotion Transition Integrity",
        "",
        f"- Readiness State: **{readiness_state}**",
        f"- Promotion Ready: **{'YES' if readiness_ready else 'NO'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_counts_consistent else 'FAIL'}**",
        f"- Transition Integrity: **{'PASS' if transition_integrity_pass else 'FAIL'}**",
        "",
        "## Post-Promotion Safety Lock",
        "",
        f"- Broker Order Submission Locked: **{'PASS' if not broker_enabled else 'FAIL'}**",
        f"- Real-Money Trading Locked: **{'PASS' if not real_money_enabled else 'FAIL'}**",
        f"- Historical Rewrite Locked: **{'PASS' if not historical_rewrite else 'FAIL'}**",
        f"- Post-Promotion Safety Lock: **{'PASS' if post_promotion_safety_lock_pass else 'FAIL'}**",
        "",
        "## Permanent Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "- Post-Promotion Broker Unlock Allowed: **NO**",
        "- Post-Promotion Real-Money Unlock Allowed: **NO**",
        "- Qualification Threshold Bypass: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {observed}/{MIN_OBSERVED}")
    print(f"Valid Cycles: {valid}/{MIN_VALID}")
    print(f"Blocked Cycles: {blocked}")
    print(f"Distinct Cycle Dates: {distinct}/{MIN_DISTINCT_DATES}")
    print(f"Promotion Ready: {'YES' if readiness_ready else 'NO'}")
    print(f"Transition Integrity: {'PASS' if transition_integrity_pass else 'FAIL'}")
    print(f"Post-Promotion Safety Lock: {'PASS' if post_promotion_safety_lock_pass else 'FAIL'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
