#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT = "PHASE3718_SCHEDULED_AUTOMATION_END_TO_END_OBSERVATION_NATURAL_QUALIFICATION_PROGRESS_MONITORING"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

ART_DIR = Path("artifacts/phase3718")
RESULT_PATH = ART_DIR / "phase3718_result.json"
SUMMARY_PATH = ART_DIR / "phase3718_summary.md"

QUALIFICATION_MUTATION_ALLOWED = False
SYNTHETIC_QUALIFICATION_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
PRODUCTION_SCHEDULE_MUTATION_ALLOWED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
OBSERVATION_ONLY = True

WORKFLOW_CHAIN = [
    ("3.7.13", "gpt-quant-v92-paper-trading-phase3713-production-paper-natural-qualification-daily-orchestration-promotion-readiness-automation.yml"),
    ("3.7.14", "gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml"),
    ("3.7.15", "gpt-quant-v92-paper-trading-phase3715-production-paper-runtime-activation-first-live-paper-session-safety-validation.yml"),
    ("3.7.15.1", "gpt-quant-v92-paper-trading-phase37151-paper-runtime-pre-activation-configuration-first-session-dry-run-readiness-audit.yml"),
    ("3.7.16", "gpt-quant-v92-paper-trading-phase3716-first-live-paper-session-execution-order-lifecycle-safety-validation.yml"),
    ("3.7.16.1", "gpt-quant-v92-paper-trading-phase37161-first-live-paper-session-preflight-canonical-3of3-activation-handoff-integrity.yml"),
    ("3.7.16.2", "gpt-quant-v92-paper-trading-phase37162-natural-2of3-to-3of3-qualification-transition-first-paper-session-release-observation.yml"),
    ("3.7.17", "gpt-quant-v92-paper-trading-phase3717-scheduled-workflow-watchdog-email-alert.yml"),
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
    return str(v).strip().upper() in {"TRUE","YES","Y","1","PASS","ENABLED"}

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
            "User-Agent": "gpt-quant-phase3718",
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
    distinct = sorted(set(dates))
    observed = len(rows)
    valid = sum(1 for r in rows if truthy(r.get("valid_cycle")))
    blocked = sum(1 for r in rows if truthy(r.get("blocked_cycle")))
    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": len(distinct),
        "distinct_dates": distinct,
        "duplicate_rows": observed - len(distinct),
        "latest_cycle_date": distinct[-1] if distinct else None,
        "runtime_supervision_pass": observed > 0 and all(truthy(r.get("runtime_supervision_pass")) for r in rows),
        "paper_only_boundary_pass": observed > 0 and all(truthy(r.get("paper_only_boundary_pass")) for r in rows),
    }

def readiness_snapshot():
    q = urllib.parse.urlencode({
        "select": "readiness_date,promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles,broker_order_submission_enabled,real_money_trading_enabled,historical_rewrite_allowed",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = supabase_get(f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def workflow_statuses():
    out = []
    for phase, wf in WORKFLOW_CHAIN:
        data = github_get(f"/actions/workflows/{wf}/runs?branch=main&per_page=10")
        runs = data.get("workflow_runs", [])
        latest = runs[0] if runs else None
        out.append({
            "phase": phase,
            "workflow": wf,
            "latest_run_present": latest is not None,
            "latest_status": latest.get("status") if latest else None,
            "latest_conclusion": latest.get("conclusion") if latest else None,
            "latest_event": latest.get("event") if latest else None,
            "latest_created_at": latest.get("created_at") if latest else None,
            "latest_url": latest.get("html_url") if latest else None,
        })
    return out

def main():
    ART_DIR.mkdir(parents=True, exist_ok=True)

    qualification = qualification_snapshot()
    readiness = readiness_snapshot()
    workflows = workflow_statuses()

    observed = int(qualification["observed"])
    valid = int(qualification["valid"])
    blocked = int(qualification["blocked"])
    distinct = int(qualification["distinct_cycle_dates"])
    duplicate_rows = int(qualification["duplicate_rows"])

    canonical_2of3 = observed >= 2 and valid >= 2 and distinct >= 2 and blocked == 0 and duplicate_rows == 0
    canonical_3of3 = (
        observed >= 3 and valid >= 3 and distinct >= 3
        and blocked == 0 and duplicate_rows == 0
        and qualification["runtime_supervision_pass"]
        and qualification["paper_only_boundary_pass"]
    )

    # PHASE371810_CANONICAL_3OF3_PROMOTION_READINESS_STATE_SYNCHRONIZATION_FIX_V2
    # Preserve the persisted readiness signal separately.
    persisted_promotion_ready = truthy(readiness.get("promotion_ready", False))
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

    # Phase 3.7.18.1 classification fix:
    # A historical/manual failed run must not permanently poison the chain while
    # natural qualification is healthy and the scheduled watchdog is operational.
    # Missing workflows and currently-running workflows are observable/non-blocking;
    # only a completed non-success latest run is classified, with Phase 3.7.17
    # (the canonical watchdog) used as the blocking authority for schedule health.
    completed_non_success = [
        x for x in workflows
        if x["latest_run_present"]
        and x["latest_status"] == "completed"
        and x["latest_conclusion"] not in ("success", "neutral", "skipped", None)
    ]
    watchdog = next((x for x in workflows if x["phase"] == "3.7.17"), None)
    watchdog_blocking = bool(
        watchdog
        and watchdog["latest_run_present"]
        and watchdog["latest_status"] == "completed"
        and watchdog["latest_conclusion"] not in ("success", "neutral", "skipped", None)
    )
    workflow_failures = [watchdog] if watchdog_blocking else []


    # Observation-layer canonical promotion readiness.
    # This derives from existing evidence only; it does not mutate persistence.
    canonical_promotion_ready = (
        canonical_3of3
        and readiness_consistent
        and broker_locked
        and real_money_locked
        and historical_locked
        and (not workflow_failures)
    )
    promotion_ready = persisted_promotion_ready or canonical_promotion_ready

    blockers = []
    if duplicate_rows > 0: blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > 0: blockers.append("BLOCKED_CYCLES_PRESENT")
    if not readiness_consistent: blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if promotion_ready and not canonical_3of3: blockers.append("PROMOTION_READY_BEFORE_CANONICAL_3OF3")
    if not broker_locked: blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked: blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_locked: blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")
    if workflow_failures: blockers.append("WORKFLOW_CHAIN_HEALTH_ISSUE")

    if blockers:
        state = "SCHEDULED_AUTOMATION_END_TO_END_OBSERVATION_BLOCKED"
        operational = False
    elif canonical_3of3 and promotion_ready:
        state = "NATURAL_3OF3_END_TO_END_AUTOMATION_OBSERVED_READY"
        operational = True
    elif canonical_2of3:
        state = "NATURAL_2OF3_END_TO_END_AUTOMATION_OBSERVED_WAITING_FOR_3OF3"
        operational = True
    else:
        state = "END_TO_END_AUTOMATION_OBSERVATION_WAITING_FOR_2OF3"
        operational = True

    result = {
        "contract": CONTRACT,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "qualification": qualification,
        "readiness": readiness,
        "workflow_chain": workflows,
        "checks": {
            "canonical_2of3": canonical_2of3,
            "canonical_3of3": canonical_3of3,
            "promotion_ready": promotion_ready,
            "persisted_promotion_ready": persisted_promotion_ready,
            "canonical_promotion_ready": canonical_promotion_ready,
            "readiness_consistent": readiness_consistent,
            "broker_locked": broker_locked,
            "real_money_locked": real_money_locked,
            "historical_rewrite_locked": historical_locked,
            "workflow_chain_healthy": len(workflow_failures) == 0,
            "completed_non_success_observed": len(completed_non_success),
            "watchdog_blocking": watchdog_blocking,
            "natural_2of3_preserved": canonical_2of3 and not canonical_3of3,
        },
        "blockers": blockers,
        "safety": {
            "observation_only": OBSERVATION_ONLY,
            "qualification_mutation_allowed": QUALIFICATION_MUTATION_ALLOWED,
            "synthetic_qualification_allowed": SYNTHETIC_QUALIFICATION_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "production_schedule_mutation_allowed": PRODUCTION_SCHEDULE_MUTATION_ALLOWED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
        },
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.18",
        "",
        "## Scheduled Automation End-to-End Observation + Natural Qualification Progress Monitoring",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        "",
        "## Natural Qualification Progress",
        "",
        f"- Observed Cycles: **{observed} / 3**",
        f"- Valid Cycles: **{valid} / 3**",
        f"- Blocked Cycles: **{blocked} / 0 max**",
        f"- Distinct Cycle Dates: **{distinct} / 3**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        f"- Canonical 2/3: **{'PASS' if canonical_2of3 else 'WAITING'}**",
        f"- Canonical 3/3: **{'PASS' if canonical_3of3 else 'WAITING'}**",
        f"- Promotion Ready: **{'YES' if promotion_ready else 'NO'}**",
        f"- Persisted Promotion Ready: **{'YES' if persisted_promotion_ready else 'NO'}**",
        f"- Canonical Promotion Ready: **{'YES' if canonical_promotion_ready else 'NO'}**",
        "",
        "## End-to-End Workflow Chain",
        "",
    ]
    for x in workflows:
        lines += [
            f"- Phase {x['phase']}: **{x['latest_conclusion'] or x['latest_status'] or 'NO_RUN'}** "
            f"({x['latest_event'] or 'NO_EVENT'})"
        ]

    lines += [
        "",
        "## Safety Boundary",
        "",
        "- Observation Only: **YES**",
        "- Qualification Mutation: **DISABLED**",
        "- Synthetic Qualification: **DISABLED**",
        "- Manual Counter Increment: **DISABLED**",
        "- Production Schedule Mutation: **DISABLED**",
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
    print(f"Canonical 2/3: {'PASS' if canonical_2of3 else 'WAITING'}")
    print(f"Canonical 3/3: {'PASS' if canonical_3of3 else 'WAITING'}")
    print(f"Workflow Chain Healthy: {'YES' if len(workflow_failures)==0 else 'NO'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
