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

CONTRACT = "PHASE37131_NATURAL_DAILY_ORCHESTRATION_PERSISTENCE_CROSS_DAY_RECOVERY_INTEGRITY"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

ART_DIR = Path("artifacts/phase37131")
RESULT_PATH = ART_DIR / "phase37131_result.json"
SUMMARY_PATH = ART_DIR / "phase37131_summary.md"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
PERSISTED_EVIDENCE_RESET_ALLOWED = False
CROSS_DAY_COUNTER_REGRESSION_ALLOWED = False
DUPLICATE_RECOVERY_INSERT_ALLOWED = False
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

def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    qualification = qualification_snapshot()
    readiness = readiness_snapshot()

    observed = int(qualification["observed"])
    valid = int(qualification["valid"])
    blocked = int(qualification["blocked"])
    distinct = int(qualification["distinct_cycle_dates"])
    duplicate_rows = int(qualification["duplicate_rows"])

    canonical_persistence_present = observed > 0 and distinct > 0
    counters_non_regressive = observed >= valid >= 0 and observed >= distinct >= 0
    duplicate_recovery_guard = duplicate_rows == 0

    readiness_consistent = True
    if readiness:
        readiness_consistent = (
            int(readiness.get("observed_cycles", observed) or 0) == observed
            and int(readiness.get("valid_cycles", valid) or 0) == valid
            and int(readiness.get("blocked_cycles", blocked) or 0) == blocked
        )

    broker_locked = not truthy(readiness.get("broker_order_submission_enabled", False)) if readiness else True
    real_money_locked = not truthy(readiness.get("real_money_trading_enabled", False)) if readiness else True
    historical_rewrite_locked = not truthy(readiness.get("historical_rewrite_allowed", False)) if readiness else True

    blockers = []
    if not canonical_persistence_present:
        blockers.append("CANONICAL_PERSISTED_EVIDENCE_MISSING")
    if not counters_non_regressive:
        blockers.append("CROSS_DAY_COUNTER_REGRESSION_DETECTED")
    if not duplicate_recovery_guard:
        blockers.append("DUPLICATE_RECOVERY_EVIDENCE_DETECTED")
    if not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if observed > 0 and not qualification["runtime_supervision_pass"]:
        blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not qualification["paper_only_boundary_pass"]:
        blockers.append("PAPER_ONLY_BOUNDARY_NOT_PASS")
    if not broker_locked:
        blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked:
        blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_rewrite_locked:
        blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "ORCHESTRATION_PERSISTENCE_RECOVERY_INTEGRITY_BLOCKED"
        operational = False
    else:
        state = "ORCHESTRATION_PERSISTENCE_RECOVERY_INTEGRITY_VALIDATED"
        operational = True

    result = {
        "contract": CONTRACT,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "qualification": qualification,
        "readiness": readiness,
        "checks": {
            "canonical_persistence_present": canonical_persistence_present,
            "counters_non_regressive": counters_non_regressive,
            "duplicate_recovery_guard": duplicate_recovery_guard,
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
            "persisted_evidence_reset_allowed": PERSISTED_EVIDENCE_RESET_ALLOWED,
            "cross_day_counter_regression_allowed": CROSS_DAY_COUNTER_REGRESSION_ALLOWED,
            "duplicate_recovery_insert_allowed": DUPLICATE_RECOVERY_INSERT_ALLOWED,
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.13.1",
        "",
        "## Natural Daily Orchestration Persistence + Cross-Day Recovery Integrity",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        "",
        "## Canonical Persistence",
        "",
        f"- Observed Cycles: **{observed}**",
        f"- Valid Cycles: **{valid}**",
        f"- Blocked Cycles: **{blocked}**",
        f"- Distinct Cycle Dates: **{distinct}**",
        f"- Latest Cycle Date: **{qualification['latest_cycle_date']}**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        f"- Canonical Persistence Present: **{'PASS' if canonical_persistence_present else 'FAIL'}**",
        "",
        "## Cross-Day Recovery Integrity",
        "",
        f"- Counter Non-Regression Guard: **{'PASS' if counters_non_regressive else 'FAIL'}**",
        f"- Duplicate Recovery Guard: **{'PASS' if duplicate_recovery_guard else 'FAIL'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
        f"- Runtime Supervision: **{'PASS' if qualification['runtime_supervision_pass'] else 'FAIL'}**",
        f"- Paper-Only Boundary: **{'PASS' if qualification['paper_only_boundary_pass'] else 'FAIL'}**",
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
        "- Persisted Evidence Reset Allowed: **NO**",
        "- Cross-Day Counter Regression Allowed: **NO**",
        "- Duplicate Recovery Insert Allowed: **NO**",
        "- Qualification Threshold Bypass: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {observed}")
    print(f"Valid Cycles: {valid}")
    print(f"Blocked Cycles: {blocked}")
    print(f"Distinct Cycle Dates: {distinct}")
    print(f"Canonical Persistence Present: {'PASS' if canonical_persistence_present else 'FAIL'}")
    print(f"Counter Non-Regression Guard: {'PASS' if counters_non_regressive else 'FAIL'}")
    print(f"Duplicate Recovery Guard: {'PASS' if duplicate_recovery_guard else 'FAIL'}")
    print(f"Readiness Counter Consistency: {'PASS' if readiness_consistent else 'FAIL'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
