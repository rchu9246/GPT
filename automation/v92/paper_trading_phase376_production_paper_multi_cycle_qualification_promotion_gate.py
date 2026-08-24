#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

CONTRACT = "PHASE376_PRODUCTION_PAPER_MULTI_CYCLE_QUALIFICATION_PROMOTION_GATE"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

PHASE375_RESULT_PATH = Path(
    os.getenv(
        "PHASE375_RESULT_PATH",
        "artifacts/phase376/input/phase375_result.json",
    )
)

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False

WAITING = "PROMOTION_WAITING_FOR_QUALIFICATION"
AUTHORIZED = "PRODUCTION_PAPER_PROMOTION_AUTHORIZED"
BLOCKED = "PRODUCTION_PAPER_PROMOTION_BLOCKED"

def bool_value(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE", "T", "1", "YES", "Y"}

def load_phase375() -> Dict[str, Any]:
    if not PHASE375_RESULT_PATH.exists():
        return {}
    try:
        obj = json.loads(PHASE375_RESULT_PATH.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def main() -> int:
    art = Path("artifacts/phase376")
    art.mkdir(parents=True, exist_ok=True)

    upstream = load_phase375()
    blockers: List[str] = []

    upstream_present = bool(upstream)
    upstream_state = str(upstream.get("state", "")).strip().upper()
    upstream_qualified = bool_value(upstream.get("qualified", False))
    upstream_operational = bool_value(upstream.get("operational", False))

    safety = upstream.get("safety", {}) if isinstance(upstream.get("safety"), dict) else {}
    counts = upstream.get("evidence_counts", {}) if isinstance(upstream.get("evidence_counts"), dict) else {}
    checks = upstream.get("checks", {}) if isinstance(upstream.get("checks"), dict) else {}

    paper_only_ok = safety.get("paper_only") is True if upstream_present else True
    broker_submission_disabled = safety.get("broker_order_submission_enabled") is False if upstream_present else True
    real_money_disabled = safety.get("real_money_trading_enabled") is False if upstream_present else True
    historical_rewrite_disabled = safety.get("historical_rewrite_allowed") is False if upstream_present else True

    runtime_pass = str(checks.get("runtime_supervision", "")).upper() == "PASS" if upstream_present else False
    blocked_cycles = int(counts.get("blocked", 0) or 0) if upstream_present else 0
    observed_cycles = int(counts.get("observed", 0) or 0) if upstream_present else 0
    valid_cycles = int(counts.get("valid", 0) or 0) if upstream_present else 0

    if upstream_present:
        if upstream_state == "MULTI_CYCLE_STABILITY_BLOCKED":
            blockers.append("UPSTREAM_PHASE375_BLOCKED")
        if not paper_only_ok:
            blockers.append("PAPER_ONLY_BOUNDARY_VIOLATION")
        if not broker_submission_disabled:
            blockers.append("BROKER_ORDER_SUBMISSION_ENABLED")
        if not real_money_disabled:
            blockers.append("REAL_MONEY_TRADING_ENABLED")
        if not historical_rewrite_disabled:
            blockers.append("HISTORICAL_REWRITE_ALLOWED")
        if blocked_cycles > 0:
            blockers.append(f"BLOCKED_CYCLES_PRESENT:{blocked_cycles}")

    qualified_contract = (
        upstream_present
        and upstream_state == "MULTI_CYCLE_STABILITY_QUALIFIED"
        and upstream_qualified
        and upstream_operational
        and runtime_pass
        and blocked_cycles == 0
        and paper_only_ok
        and broker_submission_disabled
        and real_money_disabled
        and historical_rewrite_disabled
    )

    if blockers:
        state = BLOCKED
        promotion_authorized = False
        operational = False
    elif qualified_contract:
        state = AUTHORIZED
        promotion_authorized = True
        operational = True
    else:
        state = WAITING
        promotion_authorized = False
        operational = True

    result = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "promotion_authorized": promotion_authorized,
        "operational": operational,
        "blockers": blockers,
        "upstream": {
            "phase375_result_present": upstream_present,
            "phase375_state": upstream_state or "NOT_AVAILABLE",
            "phase375_qualified": upstream_qualified,
            "phase375_operational": upstream_operational,
            "runtime_supervision": "PASS" if runtime_pass else "NOT_QUALIFIED",
            "observed_cycles": observed_cycles,
            "valid_cycles": valid_cycles,
            "blocked_cycles": blocked_cycles,
        },
        "checks": {
            "upstream_phase375_qualified": "PASS" if qualified_contract else "WAITING",
            "runtime_supervision": "PASS" if runtime_pass else "WAITING",
            "blocked_cycle_gate": "PASS" if blocked_cycles == 0 else "FAIL",
            "paper_only_boundary": "PASS" if paper_only_ok else "FAIL",
            "broker_order_submission": "DISABLED" if broker_submission_disabled else "ENABLED",
            "real_money_trading": "DISABLED" if real_money_disabled else "ENABLED",
            "historical_rewrite_prohibition": "PASS" if historical_rewrite_disabled else "FAIL",
        },
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_api_used": BROKER_API_USED,
            "broker_credentials_used": BROKER_CREDENTIALS_USED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        },
    }

    (art / "phase376_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.6",
        "",
        "## Production Paper Multi-Cycle Qualification Promotion Gate",
        "",
        f"- Contract: `{CONTRACT}`",
        f"- Portfolio ID: `{PORTFOLIO_ID}`",
        f"- Strategy Version: `{STRATEGY_VERSION}`",
        f"- Promotion Gate State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Promotion Authorized: **{'YES' if promotion_authorized else 'NO'}**",
        "",
        "## Upstream Phase 3.7.5",
        "",
        f"- Result Present: **{'YES' if upstream_present else 'NO'}**",
        f"- State: **{upstream_state or 'NOT_AVAILABLE'}**",
        f"- Qualified: **{'YES' if upstream_qualified else 'NO'}**",
        f"- Observed Cycles: **{observed_cycles}**",
        f"- Valid Cycles: **{valid_cycles}**",
        f"- Blocked Cycles: **{blocked_cycles}**",
        "",
        "## Gate Checks",
        "",
    ]
    for k, v in result["checks"].items():
        lines.append(f"- {k}: **{v}**")

    lines += [
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
    ]

    if blockers:
        lines += ["", "## Blockers", ""]
        for b in blockers:
            lines.append(f"- **{b}**")

    (art / "phase376_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Promotion Authorized: {'YES' if promotion_authorized else 'NO'}")
    print(f"Phase375 State: {upstream_state or 'NOT_AVAILABLE'}")
    print(f"Phase375 Qualified: {'YES' if upstream_qualified else 'NO'}")
    print(f"Observed Cycles: {observed_cycles}")
    print(f"Valid Cycles: {valid_cycles}")
    print(f"Blocked Cycles: {blocked_cycles}")
    if blockers:
        print("Blockers: " + ", ".join(blockers))

    # WAITING is healthy and must not fail CI. Only genuine safety/upstream failure blocks.
    return 1 if state == BLOCKED else 0

if __name__ == "__main__":
    raise SystemExit(main())
