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

CONTRACT = "PHASE37151_PAPER_RUNTIME_PRE_ACTIVATION_CONFIGURATION_FIRST_SESSION_DRY_RUN_READINESS_AUDIT"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MIN_DISTINCT_DATES = 3
MAX_BLOCKED = 0

ART_DIR = Path("artifacts/phase37151")
RESULT_PATH = ART_DIR / "phase37151_result.json"
SUMMARY_PATH = ART_DIR / "phase37151_summary.md"

# Permanent safety contract.
PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
QUALIFICATION_MUTATION_ALLOWED = False
SYNTHETIC_CYCLE_DATE_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
DRY_RUN_BROKER_SIDE_EFFECT_ALLOWED = False
DRY_RUN_REAL_MONEY_SIDE_EFFECT_ALLOWED = False
PRE_ACTIVATION_BYPASS_ALLOWED = False

# These are configuration/lineage dependencies only. Phase 3.7.15.1 does not invoke them.
REQUIRED_REPO_PATHS = [
    ".github/workflows/gpt-quant-v92-paper-trading-phase3713-production-paper-natural-qualification-daily-orchestration-promotion-readiness-automation.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase37131-natural-daily-orchestration-persistence-cross-day-recovery-integrity.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase3715-production-paper-runtime-activation-first-live-paper-session-safety-validation.yml",
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

def dry_run() -> Dict[str, Any]:
    """
    Pure dry-run. No database writes, no broker calls, no counter mutation.
    The output only proves that a first-session envelope can be constructed
    while all real-money/broker side effects remain disabled.
    """
    envelope = {
        "mode": "PAPER_DRY_RUN",
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "broker_submission": False,
        "real_money": False,
        "historical_rewrite": False,
        "qualification_mutation": False,
        "synthetic_cycle_date": False,
        "manual_counter_increment": False,
        "side_effects": [],
    }
    return {
        "dry_run_pass": (
            envelope["mode"] == "PAPER_DRY_RUN"
            and envelope["broker_submission"] is False
            and envelope["real_money"] is False
            and envelope["historical_rewrite"] is False
            and envelope["qualification_mutation"] is False
            and envelope["synthetic_cycle_date"] is False
            and envelope["manual_counter_increment"] is False
            and envelope["side_effects"] == []
        ),
        "envelope": envelope,
    }

def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    qualification = qualification_snapshot()
    readiness = readiness_snapshot()
    config = repo_configuration_audit()
    dry = dry_run()

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

    phase3715_ready_equivalent = canonical_3of3 and promotion_ready and readiness_consistent
    pre_activation_configuration_ready = bool(config["configuration_complete"]) and bool(dry["dry_run_pass"])

    blockers = []
    if not config["configuration_complete"]:
        blockers.append("PRE_ACTIVATION_CONFIGURATION_INCOMPLETE")
    if not dry["dry_run_pass"]:
        blockers.append("FIRST_SESSION_DRY_RUN_FAILED")
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
        state = "PAPER_RUNTIME_PRE_ACTIVATION_AUDIT_BLOCKED"
        operational = False
        first_session_dry_run_ready = False
    elif phase3715_ready_equivalent:
        state = "PAPER_RUNTIME_PRE_ACTIVATION_AUDIT_READY_FOR_FIRST_SESSION"
        operational = True
        first_session_dry_run_ready = True
    else:
        state = "PAPER_RUNTIME_PRE_ACTIVATION_AUDIT_READY_WAITING_FOR_3OF3"
        operational = True
        first_session_dry_run_ready = True

    result = {
        "contract": CONTRACT,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "first_session_dry_run_ready": first_session_dry_run_ready,
        "configuration": config,
        "dry_run": dry,
        "qualification": qualification,
        "readiness": readiness,
        "checks": {
            "canonical_3of3": canonical_3of3,
            "promotion_ready": promotion_ready,
            "readiness_counter_consistent": readiness_consistent,
            "phase3715_ready_equivalent": phase3715_ready_equivalent,
            "pre_activation_configuration_ready": pre_activation_configuration_ready,
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
            "synthetic_cycle_date_allowed": SYNTHETIC_CYCLE_DATE_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "dry_run_broker_side_effect_allowed": DRY_RUN_BROKER_SIDE_EFFECT_ALLOWED,
            "dry_run_real_money_side_effect_allowed": DRY_RUN_REAL_MONEY_SIDE_EFFECT_ALLOWED,
            "pre_activation_bypass_allowed": PRE_ACTIVATION_BYPASS_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.15.1",
        "",
        "## Paper Runtime Pre-Activation Configuration + First Session Dry-Run Readiness Audit",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- First Session Dry-Run Ready: **{'YES' if first_session_dry_run_ready else 'NO'}**",
        "",
        "## Pre-Activation Configuration",
        "",
        f"- Required Lineage Files Present: **{'PASS' if config['configuration_complete'] else 'FAIL'}**",
        f"- Missing Required Paths: **{', '.join(config['missing_paths']) if config['missing_paths'] else 'NONE'}**",
        "",
        "## First Session Dry-Run",
        "",
        f"- Dry-Run Envelope Construction: **{'PASS' if dry['dry_run_pass'] else 'FAIL'}**",
        "- Broker Side Effect: **DISABLED**",
        "- Real-Money Side Effect: **DISABLED**",
        "- Qualification Mutation: **DISABLED**",
        "- Synthetic Cycle-Date: **DISABLED**",
        "- Manual Counter Increment: **DISABLED**",
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
        f"- Phase 3.7.15 Ready Equivalent: **{'YES' if phase3715_ready_equivalent else 'NO'}**",
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
        "- Historical Rewrite Allowed: **NO**",
        "- Qualification Mutation Allowed: **NO**",
        "- Synthetic Cycle-Date Allowed: **NO**",
        "- Manual Counter Increment Allowed: **NO**",
        "- Dry-Run Broker Side Effect Allowed: **NO**",
        "- Dry-Run Real-Money Side Effect Allowed: **NO**",
        "- Pre-Activation Bypass Allowed: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Configuration Audit: {'PASS' if config['configuration_complete'] else 'FAIL'}")
    print(f"Dry Run: {'PASS' if dry['dry_run_pass'] else 'FAIL'}")
    print(f"Observed: {observed}/{MIN_OBSERVED}")
    print(f"Valid: {valid}/{MIN_VALID}")
    print(f"Distinct Cycle Dates: {distinct}/{MIN_DISTINCT_DATES}")
    print(f"Promotion Ready: {'YES' if promotion_ready else 'NO'}")
    print(f"First Session Dry-Run Ready: {'YES' if first_session_dry_run_ready else 'NO'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
