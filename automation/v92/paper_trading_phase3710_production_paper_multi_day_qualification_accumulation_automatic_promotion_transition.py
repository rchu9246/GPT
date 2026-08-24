#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE3710_PRODUCTION_PAPER_MULTI_DAY_QUALIFICATION_ACCUMULATION_AUTOMATIC_PROMOTION_TRANSITION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MAX_BLOCKED = 0

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False
QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False

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

    observed = len(rows)
    valid = sum(1 for r in rows if b(r.get("valid_cycle")))
    blocked = sum(1 for r in rows if b(r.get("blocked_cycle")))
    runtime_pass = observed > 0 and all(b(r.get("runtime_supervision_pass")) for r in rows)
    paper_only_pass = observed > 0 and all(b(r.get("paper_only_boundary_pass")) for r in rows)
    dates = [str(r.get("cycle_date")) for r in rows if r.get("cycle_date")]

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "runtime_supervision_pass": runtime_pass,
        "paper_only_boundary_pass": paper_only_pass,
        "cycle_dates": dates,
        "distinct_cycle_dates": len(set(dates)),
    }

def readiness_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "readiness_date,qualification_state,promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = request("GET", f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main() -> int:
    art = Path("artifacts/phase3710")
    art.mkdir(parents=True, exist_ok=True)

    q = qualification_snapshot()
    r = readiness_snapshot()

    observed = int(q["observed"])
    valid = int(q["valid"])
    blocked = int(q["blocked"])
    distinct_dates = int(q["distinct_cycle_dates"])
    runtime_pass = bool(q["runtime_supervision_pass"])
    paper_only_pass = bool(q["paper_only_boundary_pass"])

    threshold_met = (
        observed >= MIN_OBSERVED
        and valid >= MIN_VALID
        and blocked <= MAX_BLOCKED
        and distinct_dates >= MIN_OBSERVED
        and runtime_pass
        and paper_only_pass
    )

    readiness_state = str(r.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()
    readiness_ready = b(r.get("promotion_ready", False))

    blockers = []
    if blocked > MAX_BLOCKED:
        blockers.append(f"BLOCKED_CYCLES_PRESENT:{blocked}")
    if observed > 0 and not runtime_pass:
        blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not paper_only_pass:
        blockers.append("PAPER_ONLY_BOUNDARY_NOT_PASS")
    if observed != distinct_dates:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")

    if blockers:
        state = "MULTI_DAY_QUALIFICATION_BLOCKED"
        transition_required = False
        operational = False
    elif threshold_met and readiness_ready and readiness_state == "PROMOTION_READINESS_READY":
        state = "AUTOMATIC_PROMOTION_TRANSITION_READY"
        transition_required = False
        operational = True
    elif threshold_met:
        state = "QUALIFICATION_THRESHOLD_MET_PROMOTION_TRANSITION_REQUIRED"
        transition_required = True
        operational = True
    else:
        state = "MULTI_DAY_QUALIFICATION_ACCUMULATING"
        transition_required = False
        operational = True

    result = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "state": state,
        "operational": operational,
        "transition_required": transition_required,
        "thresholds": {
            "minimum_observed_cycles": MIN_OBSERVED,
            "minimum_valid_cycles": MIN_VALID,
            "maximum_blocked_cycles": MAX_BLOCKED,
            "minimum_distinct_cycle_dates": MIN_OBSERVED,
        },
        "qualification": q,
        "readiness": r,
        "checks": {
            "threshold_met": threshold_met,
            "readiness_ready": readiness_ready,
            "same_day_deduplication_preserved": observed == distinct_dates,
            "qualification_threshold_bypass": False,
        },
        "blockers": blockers,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
            "same_day_duplicate_bypass_allowed": SAME_DAY_DUPLICATE_BYPASS_ALLOWED,
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
        },
    }

    (art / "phase3710_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.10",
        "",
        "## Production Paper Multi-Day Qualification Accumulation + Automatic Promotion Transition",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Automatic Promotion Transition Required: **{'YES' if transition_required else 'NO'}**",
        "",
        "## Multi-Day Qualification Evidence",
        "",
        f"- Observed Cycles: **{observed} / {MIN_OBSERVED}**",
        f"- Valid Cycles: **{valid} / {MIN_VALID}**",
        f"- Blocked Cycles: **{blocked} / {MAX_BLOCKED} max**",
        f"- Distinct Cycle Dates: **{distinct_dates} / {MIN_OBSERVED}**",
        f"- Runtime Supervision: **{'PASS' if runtime_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        f"- Paper-Only Boundary: **{'PASS' if paper_only_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        "",
        "## Promotion Readiness",
        "",
        f"- Phase 3.7.9 Readiness State: **{readiness_state}**",
        f"- Promotion Ready: **{'YES' if readiness_ready else 'NO'}**",
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "- Same-Day Duplicate Bypass: **NO**",
        "- Qualification Threshold Bypass: **NO**",
    ]
    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{x}**" for x in blockers]

    (art / "phase3710_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {observed}")
    print(f"Valid Cycles: {valid}")
    print(f"Blocked Cycles: {blocked}")
    print(f"Distinct Cycle Dates: {distinct_dates}")
    print(f"Transition Required: {'YES' if transition_required else 'NO'}")

    return 1 if blockers else 0

if __name__ == "__main__":
    raise SystemExit(main())
