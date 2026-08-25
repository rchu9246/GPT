#!/usr/bin/env python3
from __future__ import annotations

import json, os, urllib.parse, urllib.request, urllib.error
from pathlib import Path

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")
QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MIN_DISTINCT_DATES = 3
MAX_BLOCKED = 0

ART_DIR = Path("artifacts/phase37161")
SUMMARY_PATH = ART_DIR / "phase37161_summary.md"

QUALIFICATION_MUTATION_ALLOWED = False
SYNTHETIC_QUALIFICATION_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
ACTIVATION_HANDOFF_BEFORE_3OF3_ALLOWED = False
FIRST_SESSION_RELEASE_WITHOUT_PREFLIGHT_PASS_ALLOWED = False

REQUIRED_REPO_PATHS = [
    ".github/workflows/gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase3715-production-paper-runtime-activation-first-live-paper-session-safety-validation.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase37151-paper-runtime-pre-activation-configuration-first-session-dry-run-readiness-audit.yml",
    ".github/workflows/gpt-quant-v92-paper-trading-phase3716-first-live-paper-session-execution-order-lifecycle-safety-validation.yml",
]

def env_first(*names):
    for name in names:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

def truthy(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE","YES","Y","1","PASS","ENABLED"}

def get(path):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept":"application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e

def qualification():
    q = urllib.parse.urlencode({
        "select":"cycle_date,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id":f"eq.{PORTFOLIO_ID}",
        "strategy_version":f"eq.{STRATEGY_VERSION}",
        "order":"cycle_date.asc",
        "limit":"1000",
    })
    rows = get(f"{QUALIFICATION_TABLE}?{q}") or []
    dates = [str(x.get("cycle_date")) for x in rows if x.get("cycle_date")]
    distinct = sorted(set(dates))
    observed = len(rows)
    valid = sum(1 for x in rows if truthy(x.get("valid_cycle")))
    blocked = sum(1 for x in rows if truthy(x.get("blocked_cycle")))
    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct": len(distinct),
        "duplicate_rows": observed - len(distinct),
        "runtime_pass": observed > 0 and all(truthy(x.get("runtime_supervision_pass")) for x in rows),
        "paper_only_pass": observed > 0 and all(truthy(x.get("paper_only_boundary_pass")) for x in rows),
    }

def readiness():
    q = urllib.parse.urlencode({
        "select":"promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles,broker_order_submission_enabled,real_money_trading_enabled,historical_rewrite_allowed",
        "portfolio_id":f"eq.{PORTFOLIO_ID}",
        "strategy_version":f"eq.{STRATEGY_VERSION}",
        "order":"readiness_date.desc",
        "limit":"1",
    })
    rows = get(f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main():
    ART_DIR.mkdir(parents=True, exist_ok=True)
    q = qualification()
    r = readiness()
    missing = [p for p in REQUIRED_REPO_PATHS if not Path(p).is_file()]
    lineage_ok = not missing

    canonical_3of3 = (
        q["observed"] >= MIN_OBSERVED
        and q["valid"] >= MIN_VALID
        and q["distinct"] >= MIN_DISTINCT_DATES
        and q["blocked"] <= MAX_BLOCKED
        and q["duplicate_rows"] == 0
        and q["runtime_pass"]
        and q["paper_only_pass"]
    )

    readiness_consistent = True
    if r:
        readiness_consistent = (
            int(r.get("observed_cycles", q["observed"]) or 0) == q["observed"]
            and int(r.get("valid_cycles", q["valid"]) or 0) == q["valid"]
            and int(r.get("blocked_cycles", q["blocked"]) or 0) == q["blocked"]
        )

    promotion_ready = truthy(r.get("promotion_ready", False))
    broker_locked = not truthy(r.get("broker_order_submission_enabled", False))
    real_money_locked = not truthy(r.get("real_money_trading_enabled", False))
    historical_locked = not truthy(r.get("historical_rewrite_allowed", False))

    handoff_ready = canonical_3of3 and promotion_ready and readiness_consistent and lineage_ok

    blockers = []
    if not lineage_ok: blockers.append("ACTIVATION_LINEAGE_INCOMPLETE")
    if q["duplicate_rows"] > 0: blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if q["blocked"] > 0: blockers.append("BLOCKED_CYCLES_PRESENT")
    if not readiness_consistent: blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if promotion_ready and not canonical_3of3: blockers.append("PROMOTION_READY_BEFORE_CANONICAL_3OF3")
    if not broker_locked: blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked: blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_locked: blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "FIRST_LIVE_PAPER_SESSION_PREFLIGHT_HANDOFF_BLOCKED"
        operational = False
        release_ready = False
    elif handoff_ready:
        state = "FIRST_LIVE_PAPER_SESSION_PREFLIGHT_HANDOFF_VALIDATED_READY"
        operational = True
        release_ready = True
    else:
        state = "FIRST_LIVE_PAPER_SESSION_PREFLIGHT_HANDOFF_ARMED_WAITING_FOR_3OF3"
        operational = True
        release_ready = False

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.16.1",
        "",
        "## First Live Paper Session Preflight + Canonical 3/3 Activation Handoff Integrity",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- First Live Paper Session Release Ready: **{'YES' if release_ready else 'NO'}**",
        "",
        "## Activation Handoff Lineage",
        "",
        f"- Required 3.7.14 → 3.7.15 → 3.7.15.1 → 3.7.16 Lineage: **{'PASS' if lineage_ok else 'FAIL'}**",
        f"- Missing Required Paths: **{', '.join(missing) if missing else 'NONE'}**",
        "",
        "## Canonical Qualification",
        "",
        f"- Observed Cycles: **{q['observed']} / 3**",
        f"- Valid Cycles: **{q['valid']} / 3**",
        f"- Blocked Cycles: **{q['blocked']} / 0 max**",
        f"- Distinct Cycle Dates: **{q['distinct']} / 3**",
        f"- Duplicate Rows: **{q['duplicate_rows']}**",
        f"- Canonical 3/3: **{'PASS' if canonical_3of3 else 'WAITING'}**",
        f"- Promotion Ready: **{'YES' if promotion_ready else 'NO'}**",
        f"- Activation Handoff Ready: **{'YES' if handoff_ready else 'NO'}**",
        "",
        "## Safety",
        "",
        f"- Broker Order Submission Locked: **{'PASS' if broker_locked else 'FAIL'}**",
        f"- Real-Money Trading Locked: **{'PASS' if real_money_locked else 'FAIL'}**",
        f"- Historical Rewrite Locked: **{'PASS' if historical_locked else 'FAIL'}**",
        "",
        "- Qualification Mutation Allowed: **NO**",
        "- Synthetic Qualification Allowed: **NO**",
        "- Manual Counter Increment Allowed: **NO**",
        "- Activation Handoff Before 3/3 Allowed: **NO**",
        "- First Session Release Without Preflight PASS Allowed: **NO**",
    ]
    if blockers:
        lines += ["", "## Blockers", ""] + [f"- **{b}**" for b in blockers]

    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"State: {state}")
    print(f"Lineage Audit: {'PASS' if lineage_ok else 'FAIL'}")
    print(f"Canonical 3/3: {'PASS' if canonical_3of3 else 'WAITING'}")
    print(f"First Live Paper Session Release Ready: {'YES' if release_ready else 'NO'}")
    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
