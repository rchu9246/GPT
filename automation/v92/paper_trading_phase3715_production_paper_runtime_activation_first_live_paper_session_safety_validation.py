#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MIN_DISTINCT_DATES = 3
MAX_BLOCKED = 0

ART_DIR = Path("artifacts/phase3715")
RESULT_PATH = ART_DIR / "phase3715_result.json"
SUMMARY_PATH = ART_DIR / "phase3715_summary.md"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
SYNTHETIC_QUALIFICATION_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
RUNTIME_ACTIVATION_WITHOUT_GATE_READY_ALLOWED = False
FIRST_LIVE_PAPER_SESSION_WITHOUT_SAFETY_PASS_ALLOWED = False

def env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

def request(path: str) -> Any:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
        method="GET",
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
        "select": "cycle_date,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request(f"{QUALIFICATION_TABLE}?{q}") or []
    dates = [str(r.get("cycle_date")) for r in rows if r.get("cycle_date")]
    distinct_dates = sorted(set(dates))
    observed = len(rows)
    valid = sum(1 for r in rows if truthy(r.get("valid_cycle")))
    blocked = sum(1 for r in rows if truthy(r.get("blocked_cycle")))
    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": len(distinct_dates),
        "duplicate_rows": observed - len(distinct_dates),
        "latest_cycle_date": distinct_dates[-1] if distinct_dates else None,
        "runtime_supervision_pass": observed > 0 and all(truthy(r.get("runtime_supervision_pass")) for r in rows),
        "paper_only_boundary_pass": observed > 0 and all(truthy(r.get("paper_only_boundary_pass")) for r in rows),
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
    rows = request(f"{READINESS_TABLE}?{q}") or []
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

    canonical_3of3 = (
        observed >= MIN_OBSERVED
        and valid >= MIN_VALID
        and distinct >= MIN_DISTINCT_DATES
        and blocked <= MAX_BLOCKED
        and duplicate_rows == 0
        and bool(q["runtime_supervision_pass"])
        and bool(q["paper_only_boundary_pass"])
    )

    readiness_present = bool(r)
    promotion_ready = truthy(r.get("promotion_ready", False))
    readiness_state = str(r.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()

    readiness_consistent = True
    if readiness_present:
        readiness_consistent = (
            int(r.get("observed_cycles", observed) or 0) == observed
            and int(r.get("valid_cycles", valid) or 0) == valid
            and int(r.get("blocked_cycles", blocked) or 0) == blocked
        )

    broker_locked = not truthy(r.get("broker_order_submission_enabled", False)) if readiness_present else True
    real_money_locked = not truthy(r.get("real_money_trading_enabled", False)) if readiness_present else True
    historical_rewrite_locked = not truthy(r.get("historical_rewrite_allowed", False)) if readiness_present else True

    gate_ready = canonical_3of3 and promotion_ready and readiness_consistent

    blockers = []
    if duplicate_rows > 0:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > 0:
        blockers.append("BLOCKED_CYCLES_PRESENT")
    if observed > 0 and not q["runtime_supervision_pass"]:
        blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not q["paper_only_boundary_pass"]:
        blockers.append("PAPER_ONLY_BOUNDARY_NOT_PASS")
    if not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if promotion_ready and not canonical_3of3:
        blockers.append("PROMOTION_READY_BEFORE_CANONICAL_3OF3")
    if not broker_locked:
        blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked:
        blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_rewrite_locked:
        blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "FIRST_LIVE_PAPER_SESSION_SAFETY_BLOCKED"
        runtime_active = False
        first_live_paper_session_ready = False
        operational = False
    elif gate_ready:
        state = "PAPER_RUNTIME_ACTIVATION_VALIDATED"
        runtime_active = True
        first_live_paper_session_ready = True
        operational = True
    else:
        state = "PAPER_RUNTIME_ACTIVATION_ARMED_WAITING"
        runtime_active = False
        first_live_paper_session_ready = False
        operational = True

    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "runtime_active": runtime_active,
        "first_live_paper_session_ready": first_live_paper_session_ready,
        "qualification": q,
        "readiness": r,
        "checks": {
            "canonical_3of3": canonical_3of3,
            "promotion_ready": promotion_ready,
            "readiness_counter_consistent": readiness_consistent,
            "phase3714_gate_ready_equivalent": gate_ready,
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
            "synthetic_qualification_allowed": SYNTHETIC_QUALIFICATION_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "runtime_activation_without_gate_ready_allowed": RUNTIME_ACTIVATION_WITHOUT_GATE_READY_ALLOWED,
            "first_live_paper_session_without_safety_pass_allowed": FIRST_LIVE_PAPER_SESSION_WITHOUT_SAFETY_PASS_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.15",
        "",
        "## Production Paper Runtime Activation + First Live Paper Session Safety Validation",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Runtime Active: **{'YES' if runtime_active else 'NO'}**",
        f"- First Live Paper Session Ready: **{'YES' if first_live_paper_session_ready else 'NO'}**",
        "",
        "## Qualification / Activation Gate",
        "",
        f"- Observed Cycles: **{observed} / {MIN_OBSERVED}**",
        f"- Valid Cycles: **{valid} / {MIN_VALID}**",
        f"- Blocked Cycles: **{blocked} / {MAX_BLOCKED} max**",
        f"- Distinct Cycle Dates: **{distinct} / {MIN_DISTINCT_DATES}**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        f"- Canonical 3/3: **{'PASS' if canonical_3of3 else 'WAITING'}**",
        f"- Promotion Ready: **{'YES' if promotion_ready else 'NO'}**",
        f"- Readiness State: **{readiness_state}**",
        f"- Phase 3.7.14 Gate Ready Equivalent: **{'YES' if gate_ready else 'NO'}**",
        "",
        "## Safety Validation",
        "",
        f"- Runtime Supervision: **{'PASS' if q['runtime_supervision_pass'] else 'FAIL'}**",
        f"- Paper-Only Boundary: **{'PASS' if q['paper_only_boundary_pass'] else 'FAIL'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
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
        "- Synthetic Qualification Allowed: **NO**",
        "- Manual Counter Increment Allowed: **NO**",
        "- Runtime Activation Without Gate Ready Allowed: **NO**",
        "- First Live Paper Session Without Safety PASS Allowed: **NO**",
    ]
    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{b}**" for b in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed: {observed}/{MIN_OBSERVED}")
    print(f"Valid: {valid}/{MIN_VALID}")
    print(f"Distinct Cycle Dates: {distinct}/{MIN_DISTINCT_DATES}")
    print(f"Promotion Ready: {'YES' if promotion_ready else 'NO'}")
    print(f"Runtime Active: {'YES' if runtime_active else 'NO'}")
    print(f"First Live Paper Session Ready: {'YES' if first_live_paper_session_ready else 'NO'}")
    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
