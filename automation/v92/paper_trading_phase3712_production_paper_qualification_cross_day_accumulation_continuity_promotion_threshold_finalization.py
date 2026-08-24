#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE3712_PRODUCTION_PAPER_QUALIFICATION_CROSS_DAY_ACCUMULATION_CONTINUITY_PROMOTION_THRESHOLD_FINALIZATION"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MIN_DISTINCT_DATES = 3
MAX_BLOCKED = 0

ART_DIR = Path("artifacts/phase3712")
RESULT_PATH = ART_DIR / "phase3712_result.json"
SUMMARY_PATH = ART_DIR / "phase3712_summary.md"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False
SAME_DAY_COUNTER_ADVANCE_ALLOWED = False
FINALIZATION_WITHOUT_CANONICAL_THRESHOLD_ALLOWED = False

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
    distinct_dates = sorted(set(dates))

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

def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    q = qualification_snapshot()
    r = readiness_snapshot()

    observed = int(q["observed"])
    valid = int(q["valid"])
    blocked = int(q["blocked"])
    distinct = int(q["distinct_cycle_dates"])
    duplicate_rows = int(q["duplicate_rows"])
    runtime_pass = bool(q["runtime_supervision_pass"])
    paper_only_pass = bool(q["paper_only_boundary_pass"])

    canonical_threshold_met = (
        observed >= MIN_OBSERVED
        and valid >= MIN_VALID
        and blocked <= MAX_BLOCKED
        and distinct >= MIN_DISTINCT_DATES
        and duplicate_rows == 0
        and runtime_pass
        and paper_only_pass
    )

    readiness_present = bool(r)
    readiness_state = str(r.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()
    readiness_ready = truthy(r.get("promotion_ready", False))

    readiness_counts_consistent = True
    if readiness_present:
        readiness_counts_consistent = (
            int(r.get("observed_cycles", observed) or 0) == observed
            and int(r.get("valid_cycles", valid) or 0) == valid
            and int(r.get("blocked_cycles", blocked) or 0) == blocked
        )

    broker_locked = not truthy(r.get("broker_order_submission_enabled", False)) if readiness_present else True
    real_money_locked = not truthy(r.get("real_money_trading_enabled", False)) if readiness_present else True
    historical_rewrite_locked = not truthy(r.get("historical_rewrite_allowed", False)) if readiness_present else True

    blockers = []

    if duplicate_rows > 0:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > MAX_BLOCKED:
        blockers.append(f"BLOCKED_CYCLES_PRESENT:{blocked}")
    if observed > 0 and not runtime_pass:
        blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not paper_only_pass:
        blockers.append("PAPER_ONLY_BOUNDARY_NOT_PASS")
    if readiness_present and not readiness_counts_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if readiness_ready and not canonical_threshold_met:
        blockers.append("PROMOTION_READY_BEFORE_THRESHOLD_FINALIZATION")
    if not broker_locked:
        blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked:
        blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_rewrite_locked:
        blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "CROSS_DAY_ACCUMULATION_CONTINUITY_BLOCKED"
        qualification_finalized = False
        promotion_threshold_met = canonical_threshold_met
        operational = False
    elif canonical_threshold_met:
        state = "QUALIFICATION_THRESHOLD_FINALIZED"
        qualification_finalized = True
        promotion_threshold_met = True
        operational = True
    else:
        state = "CROSS_DAY_ACCUMULATION_CONTINUITY_WAITING"
        qualification_finalized = False
        promotion_threshold_met = False
        operational = True

    result = {
        "contract": CONTRACT,
        "state": state,
        "operational": operational,
        "qualification_finalized": qualification_finalized,
        "promotion_threshold_met": promotion_threshold_met,
        "qualification": q,
        "readiness": r,
        "checks": {
            "canonical_threshold_met": canonical_threshold_met,
            "readiness_counter_consistent": readiness_counts_consistent,
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
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
            "same_day_counter_advance_allowed": SAME_DAY_COUNTER_ADVANCE_ALLOWED,
            "finalization_without_canonical_threshold_allowed": FINALIZATION_WITHOUT_CANONICAL_THRESHOLD_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.12",
        "",
        "## Production Paper Qualification Cross-Day Accumulation Continuity + Promotion Threshold Finalization",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Qualification Finalized: **{'YES' if qualification_finalized else 'NO'}**",
        f"- Promotion Threshold Met: **{'YES' if promotion_threshold_met else 'NO'}**",
        "",
        "## Canonical Qualification Progress",
        "",
        f"- Observed Cycles: **{observed} / {MIN_OBSERVED}**",
        f"- Valid Cycles: **{valid} / {MIN_VALID}**",
        f"- Blocked Cycles: **{blocked} / {MAX_BLOCKED} max**",
        f"- Distinct Cycle Dates: **{distinct} / {MIN_DISTINCT_DATES}**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        f"- Runtime Supervision: **{'PASS' if runtime_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        f"- Paper-Only Boundary: **{'PASS' if paper_only_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        "",
        "## Promotion Readiness Link",
        "",
        f"- Readiness State: **{readiness_state}**",
        f"- Promotion Ready: **{'YES' if readiness_ready else 'NO'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_counts_consistent else 'FAIL'}**",
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
        "- Qualification Threshold Bypass: **NO**",
        "- Same-Day Counter Advance Allowed: **NO**",
        "- Finalization Without Canonical Threshold Allowed: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed: {observed}/{MIN_OBSERVED}")
    print(f"Valid: {valid}/{MIN_VALID}")
    print(f"Blocked: {blocked}")
    print(f"Distinct Cycle Dates: {distinct}/{MIN_DISTINCT_DATES}")
    print(f"Qualification Finalized: {'YES' if qualification_finalized else 'NO'}")
    print(f"Promotion Threshold Met: {'YES' if promotion_threshold_met else 'NO'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
