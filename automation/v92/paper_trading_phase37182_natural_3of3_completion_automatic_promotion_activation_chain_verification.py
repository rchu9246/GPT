#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

CONTRACT = "PHASE37182_NATURAL_3OF3_COMPLETION_AUTOMATIC_PROMOTION_ACTIVATION_CHAIN_VERIFICATION"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

ART_DIR = Path("artifacts/phase37182")
RESULT_PATH = ART_DIR / "phase37182_result.json"
SUMMARY_PATH = ART_DIR / "phase37182_summary.md"

OBSERVATION_ONLY = True
QUALIFICATION_MUTATION_ALLOWED = False
SYNTHETIC_QUALIFICATION_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
PROMOTION_FORCE_ALLOWED = False
ACTIVATION_FORCE_ALLOWED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False

REQUIRED_WORKFLOWS = [
    ("3.7.14", "gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml"),
    ("3.7.15", "gpt-quant-v92-paper-trading-phase3715-production-paper-runtime-activation-first-live-paper-session-safety-validation.yml"),
    ("3.7.15.1", "gpt-quant-v92-paper-trading-phase37151-paper-runtime-pre-activation-configuration-first-session-dry-run-readiness-audit.yml"),
    ("3.7.16", "gpt-quant-v92-paper-trading-phase3716-first-live-paper-session-execution-order-lifecycle-safety-validation.yml"),
    ("3.7.16.1", "gpt-quant-v92-paper-trading-phase37161-first-live-paper-session-preflight-canonical-3of3-activation-handoff-integrity.yml"),
    ("3.7.16.2", "gpt-quant-v92-paper-trading-phase37162-natural-2of3-to-3of3-qualification-transition-first-paper-session-release-observation.yml"),
    ("3.7.18", "gpt-quant-v92-paper-trading-phase3718-scheduled-automation-end-to-end-observation-natural-qualification-progress-monitoring.yml"),
]

def env_first(*names):
    for name in names:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

def truthy(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE", "YES", "Y", "1", "PASS", "ENABLED", "READY"}

def supabase_get(path):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SUPABASE_HTTP_{e.code}: {detail}") from e

def github_get(path):
    if not GITHUB_REPOSITORY or not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_CONFIGURATION_MISSING")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "gpt-quant-phase37182",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GITHUB_HTTP_{e.code}: {detail}") from e

def qualification_snapshot():
    q = urllib.parse.urlencode({
        "select": "cycle_date,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = supabase_get(f"{QUALIFICATION_TABLE}?{q}") or []
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
        "distinct_dates": distinct_dates,
        "duplicate_rows": observed - len(distinct_dates),
        "runtime_supervision_pass": observed > 0 and all(truthy(r.get("runtime_supervision_pass")) for r in rows),
        "paper_only_boundary_pass": observed > 0 and all(truthy(r.get("paper_only_boundary_pass")) for r in rows),
    }

def readiness_snapshot():
    q = urllib.parse.urlencode({
        "select": "readiness_date,qualification_state,promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles,runtime_supervision_pass,paper_only_boundary_pass,broker_order_submission_enabled,real_money_trading_enabled,historical_rewrite_allowed",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = supabase_get(f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def latest_workflow_runs():
    rows = []
    for phase, wf in REQUIRED_WORKFLOWS:
        data = github_get(f"/actions/workflows/{wf}/runs?branch=main&per_page=10")
        runs = data.get("workflow_runs", [])
        latest = runs[0] if runs else None
        rows.append({
            "phase": phase,
            "workflow": wf,
            "present": latest is not None,
            "status": latest.get("status") if latest else None,
            "conclusion": latest.get("conclusion") if latest else None,
            "event": latest.get("event") if latest else None,
            "created_at": latest.get("created_at") if latest else None,
            "url": latest.get("html_url") if latest else None,
        })
    return rows

def main():
    ART_DIR.mkdir(parents=True, exist_ok=True)

    qualification = qualification_snapshot()
    readiness = readiness_snapshot()
    workflow_runs = latest_workflow_runs()

    observed = int(qualification["observed"])
    valid = int(qualification["valid"])
    blocked = int(qualification["blocked"])
    distinct = int(qualification["distinct_cycle_dates"])
    duplicates = int(qualification["duplicate_rows"])

    canonical_3of3 = (
        observed >= 3
        and valid >= 3
        and distinct >= 3
        and blocked == 0
        and duplicates == 0
        and qualification["runtime_supervision_pass"]
        and qualification["paper_only_boundary_pass"]
    )

    promotion_ready = truthy(readiness.get("promotion_ready", False))
    readiness_state = str(readiness.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()

    readiness_consistent = True
    if readiness:
        readiness_consistent = (
            int(readiness.get("observed_cycles", observed) or 0) == observed
            and int(readiness.get("valid_cycles", valid) or 0) == valid
            and int(readiness.get("blocked_cycles", blocked) or 0) == blocked
        )

    broker_locked = not truthy(readiness.get("broker_order_submission_enabled", False))
    real_money_locked = not truthy(readiness.get("real_money_trading_enabled", False))
    historical_locked = not truthy(readiness.get("historical_rewrite_allowed", False))

    latest_completed_bad = [
        x for x in workflow_runs
        if x["present"] and x["status"] == "completed" and x["conclusion"] not in ("success", "neutral", "skipped", None)
    ]

    chain_presence = all(x["present"] for x in workflow_runs)

    blockers = []
    if duplicates > 0:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > 0:
        blockers.append("BLOCKED_CYCLES_PRESENT")
    if not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if promotion_ready and not canonical_3of3:
        blockers.append("PROMOTION_READY_BEFORE_CANONICAL_3OF3")
    if not broker_locked:
        blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked:
        blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_locked:
        blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    # Historical/manual failed runs are recorded, but do not force a failure while
    # the system is still naturally waiting for 3/3. At actual 3/3, the chain must
    # have present runs and no current completed failure.
    chain_verified_for_activation = (
        canonical_3of3
        and promotion_ready
        and chain_presence
        and len(latest_completed_bad) == 0
        and readiness_consistent
        and broker_locked
        and real_money_locked
        and historical_locked
    )

    if blockers:
        state = "NATURAL_3OF3_PROMOTION_ACTIVATION_CHAIN_VERIFICATION_BLOCKED"
        operational = False
        chain_verified = False
    elif not canonical_3of3:
        state = "NATURAL_3OF3_COMPLETION_WAITING"
        operational = True
        chain_verified = False
    elif canonical_3of3 and not promotion_ready:
        state = "NATURAL_3OF3_COMPLETED_WAITING_FOR_PROMOTION"
        operational = True
        chain_verified = False
    elif chain_verified_for_activation:
        state = "NATURAL_3OF3_PROMOTION_ACTIVATION_CHAIN_VERIFIED_READY"
        operational = True
        chain_verified = True
    else:
        state = "NATURAL_3OF3_COMPLETED_PROMOTION_READY_CHAIN_PENDING"
        operational = True
        chain_verified = False

    result = {
        "contract": CONTRACT,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "chain_verified": chain_verified,
        "qualification": qualification,
        "readiness": readiness,
        "workflow_runs": workflow_runs,
        "checks": {
            "canonical_3of3": canonical_3of3,
            "promotion_ready": promotion_ready,
            "readiness_state": readiness_state,
            "readiness_consistent": readiness_consistent,
            "chain_presence": chain_presence,
            "latest_completed_bad_count": len(latest_completed_bad),
            "chain_verified_for_activation": chain_verified_for_activation,
            "broker_locked": broker_locked,
            "real_money_locked": real_money_locked,
            "historical_locked": historical_locked,
        },
        "blockers": blockers,
        "safety": {
            "observation_only": OBSERVATION_ONLY,
            "qualification_mutation_allowed": QUALIFICATION_MUTATION_ALLOWED,
            "synthetic_qualification_allowed": SYNTHETIC_QUALIFICATION_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "promotion_force_allowed": PROMOTION_FORCE_ALLOWED,
            "activation_force_allowed": ACTIVATION_FORCE_ALLOWED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.18.2",
        "",
        "## Natural 3/3 Completion + Automatic Promotion/Activation Chain Verification",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Promotion/Activation Chain Verified: **{'YES' if chain_verified else 'NO'}**",
        "",
        "## Natural Qualification",
        "",
        f"- Observed Cycles: **{observed} / 3**",
        f"- Valid Cycles: **{valid} / 3**",
        f"- Blocked Cycles: **{blocked} / 0 max**",
        f"- Distinct Cycle Dates: **{distinct} / 3**",
        f"- Duplicate Rows: **{duplicates}**",
        f"- Canonical 3/3: **{'PASS' if canonical_3of3 else 'WAITING'}**",
        f"- Promotion Ready: **{'YES' if promotion_ready else 'NO'}**",
        f"- Promotion Readiness State: **{readiness_state}**",
        "",
        "## Automatic Promotion / Activation Chain",
        "",
        f"- Required Workflow Presence: **{'PASS' if chain_presence else 'FAIL'}**",
        f"- Current Completed Non-Success Runs: **{len(latest_completed_bad)}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
        f"- Activation Chain Verified: **{'YES' if chain_verified_for_activation else 'NO'}**",
        "",
    ]

    for x in workflow_runs:
        lines.append(
            f"- Phase {x['phase']}: **{x['conclusion'] or x['status'] or 'NO_RUN'}** ({x['event'] or 'NO_EVENT'})"
        )

    lines += [
        "",
        "## Safety Boundary",
        "",
        "- Observation Only: **YES**",
        "- Qualification Mutation: **DISABLED**",
        "- Synthetic Qualification: **DISABLED**",
        "- Manual Counter Increment: **DISABLED**",
        "- Promotion Force: **DISABLED**",
        "- Activation Force: **DISABLED**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
    ]

    if blockers:
        lines += ["", "## Blockers", ""] + [f"- **{b}**" for b in blockers]

    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed: {observed}/3")
    print(f"Valid: {valid}/3")
    print(f"Distinct Cycle Dates: {distinct}/3")
    print(f"Canonical 3/3: {'PASS' if canonical_3of3 else 'WAITING'}")
    print(f"Promotion Ready: {'YES' if promotion_ready else 'NO'}")
    print(f"Promotion/Activation Chain Verified: {'YES' if chain_verified else 'NO'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
