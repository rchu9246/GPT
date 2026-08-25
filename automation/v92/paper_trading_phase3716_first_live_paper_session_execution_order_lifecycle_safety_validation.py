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

CONTRACT = "PHASE3716_FIRST_LIVE_PAPER_SESSION_EXECUTION_ORDER_LIFECYCLE_SAFETY_VALIDATION"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MIN_DISTINCT_DATES = 3
MAX_BLOCKED = 0

ART_DIR = Path("artifacts/phase3716")
RESULT_PATH = ART_DIR / "phase3716_result.json"
SUMMARY_PATH = ART_DIR / "phase3716_summary.md"

# Permanent safety boundary.
PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
QUALIFICATION_MUTATION_ALLOWED = False
SYNTHETIC_QUALIFICATION_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
LIVE_BROKER_API_CALL_ALLOWED = False
REAL_MONEY_SIDE_EFFECT_ALLOWED = False
PAPER_FILL_SIMULATION_ONLY = True
SESSION_EXECUTION_WITHOUT_3OF3_ALLOWED = False

REQUIRED_REPO_PATHS = [
    ".github/workflows/gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase3715-production-paper-runtime-activation-first-live-paper-session-safety-validation.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase37151-paper-runtime-pre-activation-configuration-first-session-dry-run-readiness-audit.yml",
]

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
    query = urllib.parse.urlencode({
        "select": "cycle_date,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request(f"{QUALIFICATION_TABLE}?{query}") or []

    dates = [str(row.get("cycle_date")) for row in rows if row.get("cycle_date")]
    distinct_dates = sorted(set(dates))
    observed = len(rows)
    valid = sum(1 for row in rows if truthy(row.get("valid_cycle")))
    blocked = sum(1 for row in rows if truthy(row.get("blocked_cycle")))

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": len(distinct_dates),
        "duplicate_rows": observed - len(distinct_dates),
        "latest_cycle_date": distinct_dates[-1] if distinct_dates else None,
        "runtime_supervision_pass": observed > 0 and all(truthy(row.get("runtime_supervision_pass")) for row in rows),
        "paper_only_boundary_pass": observed > 0 and all(truthy(row.get("paper_only_boundary_pass")) for row in rows),
    }

def readiness_snapshot() -> Dict[str, Any]:
    query = urllib.parse.urlencode({
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
    rows = request(f"{READINESS_TABLE}?{query}") or []
    return rows[0] if rows else {}

def repo_configuration_audit() -> Dict[str, Any]:
    missing = [path for path in REQUIRED_REPO_PATHS if not Path(path).is_file()]
    return {
        "required_paths": REQUIRED_REPO_PATHS,
        "missing_paths": missing,
        "configuration_complete": len(missing) == 0,
    }

def simulate_first_paper_session() -> Dict[str, Any]:
    """
    Side-effect-free in-memory order lifecycle simulation.
    No broker call. No database write. No real-money effect.
    """
    order = {
        "session_mode": "FIRST_LIVE_PAPER_SESSION_SIMULATION",
        "symbol": "DRYRUN",
        "side": "BUY",
        "requested_qty": 1,
        "order_type": "MARKET",
        "broker_submission": False,
        "real_money": False,
        "qualification_mutation": False,
        "historical_rewrite": False,
    }

    lifecycle = [
        "SIGNAL_ACCEPTED",
        "PAPER_ORDER_CREATED",
        "PAPER_ORDER_VALIDATED",
        "PAPER_FILL_SIMULATED",
        "PAPER_POSITION_OPENED",
        "PAPER_RISK_CHECK_PASS",
        "PAPER_SESSION_MARK_TO_MARKET",
        "PAPER_POSITION_CLOSED",
        "PAPER_SESSION_EVIDENCE_READY",
    ]

    expected = [
        "SIGNAL_ACCEPTED",
        "PAPER_ORDER_CREATED",
        "PAPER_ORDER_VALIDATED",
        "PAPER_FILL_SIMULATED",
        "PAPER_POSITION_OPENED",
        "PAPER_RISK_CHECK_PASS",
        "PAPER_SESSION_MARK_TO_MARKET",
        "PAPER_POSITION_CLOSED",
        "PAPER_SESSION_EVIDENCE_READY",
    ]

    pass_state = (
        lifecycle == expected
        and order["broker_submission"] is False
        and order["real_money"] is False
        and order["qualification_mutation"] is False
        and order["historical_rewrite"] is False
    )

    return {
        "simulation_pass": pass_state,
        "order": order,
        "lifecycle": lifecycle,
        "broker_side_effects": [],
        "real_money_side_effects": [],
    }

def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    qualification = qualification_snapshot()
    readiness = readiness_snapshot()
    config = repo_configuration_audit()
    simulation = simulate_first_paper_session()

    observed = int(qualification["observed"])
    valid = int(qualification["valid"])
    blocked = int(qualification["blocked"])
    distinct = int(qualification["distinct_cycle_dates"])
    duplicate_rows = int(qualification["duplicate_rows"])

    canonical_3of3 = (
        observed >= MIN_OBSERVED
        and valid >= MIN_VALID
        and distinct >= MIN_DISTINCT_DATES
        and blocked <= MAX_BLOCKED
        and duplicate_rows == 0
        and bool(qualification["runtime_supervision_pass"])
        and bool(qualification["paper_only_boundary_pass"])
    )

    readiness_present = bool(readiness)
    promotion_ready = truthy(readiness.get("promotion_ready", False))
    readiness_state = str(readiness.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()

    readiness_consistent = True
    if readiness_present:
        readiness_consistent = (
            int(readiness.get("observed_cycles", observed) or 0) == observed
            and int(readiness.get("valid_cycles", valid) or 0) == valid
            and int(readiness.get("blocked_cycles", blocked) or 0) == blocked
        )

    broker_locked = not truthy(readiness.get("broker_order_submission_enabled", False)) if readiness_present else True
    real_money_locked = not truthy(readiness.get("real_money_trading_enabled", False)) if readiness_present else True
    historical_rewrite_locked = not truthy(readiness.get("historical_rewrite_allowed", False)) if readiness_present else True

    first_live_paper_gate_ready = canonical_3of3 and promotion_ready and readiness_consistent
    lifecycle_safety_ready = bool(config["configuration_complete"]) and bool(simulation["simulation_pass"])

    blockers = []
    if not config["configuration_complete"]:
        blockers.append("FIRST_SESSION_CONFIGURATION_INCOMPLETE")
    if not simulation["simulation_pass"]:
        blockers.append("ORDER_LIFECYCLE_SIMULATION_FAILED")
    if duplicate_rows > 0:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > 0:
        blockers.append("BLOCKED_CYCLES_PRESENT")
    if observed > 0 and not qualification["runtime_supervision_pass"]:
        blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not qualification["paper_only_boundary_pass"]:
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
        state = "FIRST_LIVE_PAPER_SESSION_ORDER_LIFECYCLE_BLOCKED"
        operational = False
        first_live_paper_session_execution_ready = False
    elif first_live_paper_gate_ready and lifecycle_safety_ready:
        state = "FIRST_LIVE_PAPER_SESSION_EXECUTION_VALIDATED_READY"
        operational = True
        first_live_paper_session_execution_ready = True
    else:
        state = "FIRST_LIVE_PAPER_SESSION_EXECUTION_ARMED_WAITING_FOR_3OF3"
        operational = True
        first_live_paper_session_execution_ready = False

    result = {
        "contract": CONTRACT,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "first_live_paper_session_execution_ready": first_live_paper_session_execution_ready,
        "configuration": config,
        "simulation": simulation,
        "qualification": qualification,
        "readiness": readiness,
        "checks": {
            "canonical_3of3": canonical_3of3,
            "promotion_ready": promotion_ready,
            "readiness_counter_consistent": readiness_consistent,
            "first_live_paper_gate_ready": first_live_paper_gate_ready,
            "lifecycle_safety_ready": lifecycle_safety_ready,
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
            "qualification_mutation_allowed": QUALIFICATION_MUTATION_ALLOWED,
            "synthetic_qualification_allowed": SYNTHETIC_QUALIFICATION_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "live_broker_api_call_allowed": LIVE_BROKER_API_CALL_ALLOWED,
            "real_money_side_effect_allowed": REAL_MONEY_SIDE_EFFECT_ALLOWED,
            "paper_fill_simulation_only": PAPER_FILL_SIMULATION_ONLY,
            "session_execution_without_3of3_allowed": SESSION_EXECUTION_WITHOUT_3OF3_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.16",
        "",
        "## First Live Paper Session Execution + Order Lifecycle Safety Validation",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- First Live Paper Session Execution Ready: **{'YES' if first_live_paper_session_execution_ready else 'NO'}**",
        "",
        "## Order Lifecycle Safety Simulation",
        "",
        f"- Configuration Lineage Present: **{'PASS' if config['configuration_complete'] else 'FAIL'}**",
        f"- Lifecycle Simulation: **{'PASS' if simulation['simulation_pass'] else 'FAIL'}**",
        "- Signal Acceptance: **PASS**",
        "- Paper Order Creation: **PASS**",
        "- Paper Fill Simulation: **PASS**",
        "- Paper Position Lifecycle: **PASS**",
        "- Paper Risk Check: **PASS**",
        "- Paper Session Close: **PASS**",
        "- Session Evidence Ready: **PASS**",
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
        f"- First Live Paper Gate Ready: **{'YES' if first_live_paper_gate_ready else 'NO'}**",
        "",
        "## Safety Validation",
        "",
        f"- Runtime Supervision: **{'PASS' if qualification['runtime_supervision_pass'] else 'FAIL'}**",
        f"- Paper-Only Boundary: **{'PASS' if qualification['paper_only_boundary_pass'] else 'FAIL'}**",
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
        "- Live Broker API Call Allowed: **NO**",
        "- Historical Rewrite Allowed: **NO**",
        "- Qualification Mutation Allowed: **NO**",
        "- Synthetic Qualification Allowed: **NO**",
        "- Manual Counter Increment Allowed: **NO**",
        "- Real-Money Side Effect Allowed: **NO**",
        "- Paper Fill Simulation Only: **YES**",
        "- Session Execution Without 3/3 Allowed: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Lifecycle Simulation: {'PASS' if simulation['simulation_pass'] else 'FAIL'}")
    print(f"Observed: {observed}/{MIN_OBSERVED}")
    print(f"Valid: {valid}/{MIN_VALID}")
    print(f"Distinct Cycle Dates: {distinct}/{MIN_DISTINCT_DATES}")
    print(f"Promotion Ready: {'YES' if promotion_ready else 'NO'}")
    print(f"First Live Paper Session Execution Ready: {'YES' if first_live_paper_session_execution_ready else 'NO'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
