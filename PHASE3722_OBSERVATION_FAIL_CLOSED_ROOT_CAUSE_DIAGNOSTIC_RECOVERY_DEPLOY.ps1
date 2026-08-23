#requires -Version 5.1
<#
PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.2 — Observation FAIL_CLOSED Root Cause Diagnostic + Safe Recovery

Purpose
-------
Diagnose why the unattended observation chain entered FAIL_CLOSED and determine
whether the cause is:
  - a real safety revocation,
  - an upstream lifecycle failure,
  - stale / date-misaligned canonical evidence,
  - an observation aggregation issue,
  - or a downstream readiness/promotion propagation issue.

This package NEVER fabricates PASS history and NEVER rewrites historical
Phase 3.6.9 lifecycle evidence.

Recovery policy
---------------
SAFE_CANONICAL_RERUN is allowed only when the latest upstream safety sources
are healthy and the FAIL_CLOSED state can be explained by stale/misaligned
downstream evidence. Otherwise recovery remains blocked or requires review.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py
  supabase/PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase3722-observation-fail-closed-root-cause-diagnostic-recovery.yml
#>

param(
    [switch]$AutoGit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Text" -ForegroundColor Red
    exit 1
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

Section "GPT Quant V9.2 — Phase 3.7.2.2 FAIL_CLOSED Diagnostic + Safe Recovery"

$repo = $null
try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = $null
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this package from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py",
    "automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py",
    "automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py",
    "automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py",
    "automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py",
    "automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase3722-observation-fail-closed-root-cause-diagnostic-recovery.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase3722-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.7.2.2 diagnostic engine"

$py = @'
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

RECOVERY_NOT_NEEDED = "NOT_NEEDED"
RECOVERY_SAFE_RERUN = "SAFE_CANONICAL_RERUN"
RECOVERY_BLOCKED = "BLOCKED_BY_TRUE_SAFETY_FAILURE"
RECOVERY_NEEDS_REVIEW = "NEEDS_REVIEW"

def env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""

def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

class Supabase:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def request(self, method: str, table: str, query: str = "", payload: Optional[Any] = None, prefer: Optional[str] = None) -> Any:
        endpoint = f"{self.url}/rest/v1/{table}"
        if query:
            endpoint += "?" + query
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, headers=headers, data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc

    def get(self, table: str, query: str) -> List[Dict[str, Any]]:
        value = self.request("GET", table, query=query)
        return value if isinstance(value, list) else []

    def upsert(self, table: str, payload: Dict[str, Any], on_conflict: str) -> None:
        query = "on_conflict=" + urllib.parse.quote(on_conflict, safe=",")
        self.request("POST", table, query=query, payload=payload, prefer="resolution=merge-duplicates,return=minimal")

def latest(sb: Supabase, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def row_date(row: Optional[Dict[str, Any]], *names: str) -> Optional[str]:
    if not row:
        return None
    for name in names:
        value = row.get(name)
        if value:
            return str(value)[:10]
    return None

def text(row: Optional[Dict[str, Any]], *names: str, default: str = "MISSING") -> str:
    if not row:
        return default
    for name in names:
        value = row.get(name)
        if value is not None:
            return str(value).upper()
    return default

def truth(row: Optional[Dict[str, Any]], *names: str, default: bool = False) -> bool:
    if not row:
        return default
    for name in names:
        if name in row:
            return as_bool(row.get(name), default)
    return default

def diagnose(supervision, controller, lifecycle, observation, readiness, promotion):
    reasons: List[str] = []
    true_safety_failures: List[str] = []
    stale_or_propagation_issues: List[str] = []

    supervision_state = text(supervision, "supervision_state", "runtime_supervision_state", "state")
    controller_state = text(controller, "controller_state")
    lifecycle_state = text(lifecycle, "lifecycle_state")
    observation_state = text(observation, "observation_state")
    readiness_state = text(readiness, "readiness_state")
    promotion_state = text(promotion, "promotion_state")

    supervision_revoked = (
        truth(supervision, "safety_revocation_triggered", default=False)
        or supervision_state in {"REVOKED", "FAIL_CLOSED", "STOP", "BLOCKED"}
    )
    controller_revoked = truth(controller, "safety_revocation_triggered", default=False)
    lifecycle_revoked = truth(lifecycle, "safety_revocation_triggered", default=False)

    observation_revocation_days = as_int((observation or {}).get("safety_revocation_days"), 0)
    readiness_revocation_days = as_int((readiness or {}).get("safety_revocation_days"), 0)

    if supervision_revoked:
        true_safety_failures.append("RUNTIME_SUPERVISION_REVOKED")
    if controller_revoked:
        true_safety_failures.append("DAILY_CONTROLLER_REVOKED")
    if lifecycle_revoked:
        true_safety_failures.append("LATEST_LIFECYCLE_REVOKED")

    dates = {
        "supervision": row_date(supervision, "supervision_date", "run_date", "created_at"),
        "controller": row_date(controller, "controller_date", "run_date", "created_at"),
        "lifecycle": row_date(lifecycle, "evidence_date", "run_date", "created_at"),
        "observation": row_date(observation, "observation_date", "created_at"),
        "readiness": row_date(readiness, "monitor_date", "created_at"),
        "promotion": row_date(promotion, "promotion_date", "created_at"),
    }

    known_dates = [d for d in dates.values() if d]
    newest_date = max(known_dates) if known_dates else None
    if newest_date:
        for name, d in dates.items():
            if d and d != newest_date:
                stale_or_propagation_issues.append(f"{name.upper()}_DATE_MISMATCH:{d}!={newest_date}")

    if (
        lifecycle_state == "FAIL_CLOSED"
        and not lifecycle_revoked
        and controller_state in {"COMPLETED", "COMPLETED_WITH_OBSERVATION"}
        and not controller_revoked
        and supervision_state in {"CONTINUE_ACTIVE", "CONTINUE_WITH_OBSERVATION", "ACTIVE", "HEALTHY"}
        and not supervision_revoked
    ):
        stale_or_propagation_issues.append("LIFECYCLE_FAIL_CLOSED_WITH_HEALTHY_UPSTREAM")

    if observation_state == "FAIL_CLOSED" and lifecycle_state in {"PASS", "PASS_WITH_OBSERVATION"} and not lifecycle_revoked:
        stale_or_propagation_issues.append("OBSERVATION_FAIL_CLOSED_WITH_PASSING_LIFECYCLE")

    if readiness_state == "FAIL_CLOSED" and observation_state not in {"FAIL_CLOSED", "MISSING"} and observation_revocation_days == 0:
        stale_or_propagation_issues.append("READINESS_FAIL_CLOSED_WITH_HEALTHY_OBSERVATION")

    if promotion_state == "FAIL_CLOSED" and readiness_state not in {"FAIL_CLOSED", "MISSING"}:
        stale_or_propagation_issues.append("PROMOTION_FAIL_CLOSED_WITH_HEALTHY_READINESS")

    if observation_revocation_days > 0:
        reasons.append(f"OBSERVATION_REPORTED_REVOCATION_DAYS:{observation_revocation_days}")
    if readiness_revocation_days > 0:
        reasons.append(f"READINESS_REPORTED_REVOCATION_DAYS:{readiness_revocation_days}")

    if true_safety_failures:
        recovery_state = RECOVERY_BLOCKED
        safe_to_rerun = False
        reasons.extend(true_safety_failures)
    elif stale_or_propagation_issues:
        recovery_state = RECOVERY_SAFE_RERUN
        safe_to_rerun = True
        reasons.extend(stale_or_propagation_issues)
    elif all(state not in {"FAIL_CLOSED", "MISSING"} for state in (lifecycle_state, observation_state, readiness_state, promotion_state)):
        recovery_state = RECOVERY_NOT_NEEDED
        safe_to_rerun = False
        reasons.append("CURRENT_CHAIN_NOT_FAIL_CLOSED")
    else:
        recovery_state = RECOVERY_NEEDS_REVIEW
        safe_to_rerun = False
        reasons.append("FAIL_CLOSED_ROOT_CAUSE_NOT_PROVEN_SAFE")

    if (observation_revocation_days > 0 or readiness_revocation_days > 0) and not true_safety_failures:
        reasons.append("HISTORICAL_REVOCATION_COUNT_REQUIRES_SOURCE_AUDIT")

    return {
        "recovery_state": recovery_state,
        "safe_to_rerun_canonical_chain": safe_to_rerun,
        "historical_rewrite_allowed": False,
        "true_safety_failures": true_safety_failures,
        "stale_or_propagation_issues": stale_or_propagation_issues,
        "reasons": reasons,
        "states": {
            "supervision": supervision_state,
            "controller": controller_state,
            "lifecycle": lifecycle_state,
            "observation": observation_state,
            "readiness": readiness_state,
            "promotion": promotion_state,
        },
        "dates": dates,
        "observation_revocation_days": observation_revocation_days,
        "readiness_revocation_days": readiness_revocation_days,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--diagnostic-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.diagnostic_date)

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "VITE_SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = Supabase(url, key)

    supervision = latest(sb, "paper_runtime_supervision_v92", args.portfolio_id, "supervision_date")
    controller = latest(sb, "paper_daily_autonomous_controller_v92", args.portfolio_id, "controller_date")
    lifecycle = latest(sb, "paper_daily_lifecycle_evidence_v92", args.portfolio_id, "evidence_date")
    observation = latest(sb, "paper_operations_observation_validation_v92", args.portfolio_id, "observation_date")
    readiness = latest(sb, "paper_observation_acceptance_readiness_v92", args.portfolio_id, "monitor_date")
    promotion = latest(sb, "paper_acceptance_promotion_control_v92", args.portfolio_id, "promotion_date")

    result = diagnose(supervision, controller, lifecycle, observation, readiness, promotion)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "diagnostic_date": args.diagnostic_date,
        "result": result,
        "safety": {
            "paper_only": True,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "historical_rewrite_allowed": False,
        },
    }
    evidence_sha = stable_hash(evidence_doc)

    payload = {
        "diagnostic_date": args.diagnostic_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "recovery_state": result["recovery_state"],
        "safe_to_rerun_canonical_chain": result["safe_to_rerun_canonical_chain"],
        "historical_rewrite_allowed": False,

        "runtime_supervision_state": result["states"]["supervision"],
        "controller_state": result["states"]["controller"],
        "lifecycle_state": result["states"]["lifecycle"],
        "observation_state": result["states"]["observation"],
        "readiness_state": result["states"]["readiness"],
        "promotion_state": result["states"]["promotion"],

        "runtime_supervision_date": result["dates"]["supervision"],
        "controller_date": result["dates"]["controller"],
        "lifecycle_date": result["dates"]["lifecycle"],
        "observation_date": result["dates"]["observation"],
        "readiness_date": result["dates"]["readiness"],
        "promotion_date": result["dates"]["promotion"],

        "observation_revocation_days": result["observation_revocation_days"],
        "readiness_revocation_days": result["readiness_revocation_days"],

        "true_safety_failures": result["true_safety_failures"],
        "stale_or_propagation_issues": result["stale_or_propagation_issues"],
        "reason_codes": result["reasons"],

        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,

        "evidence_sha256": evidence_sha,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    sb.upsert("paper_observation_fail_closed_diagnostic_v92", payload, "portfolio_id,diagnostic_date")

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request("POST", "paper_observation_fail_closed_diagnostic_audit_v92", payload=audit, prefer="return=minimal")

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.2")
    print()
    print("## Observation FAIL_CLOSED Root Cause Diagnostic + Safe Recovery")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Diagnostic Date: `{args.diagnostic_date}`")
    print(f"- Recovery State: **{result['recovery_state']}**")
    print(f"- Safe To Re-run Canonical Chain: **{'YES' if result['safe_to_rerun_canonical_chain'] else 'NO'}**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical State Snapshot")
    print()
    for name in ("supervision", "controller", "lifecycle", "observation", "readiness", "promotion"):
        print(f"- {name.title()}: **{result['states'][name]}** (date `{result['dates'][name] or 'MISSING'}`)")
    print()
    print("## Revocation Diagnostics")
    print()
    print(f"- Observation Revocation Days: **{result['observation_revocation_days']}**")
    print(f"- Readiness Revocation Days: **{result['readiness_revocation_days']}**")
    print(f"- True Safety Failures: **{len(result['true_safety_failures'])}**")
    print(f"- Stale/Propagation Issues: **{len(result['stale_or_propagation_issues'])}**")
    print()
    print("## Diagnostic Reasons")
    print()
    for item in result["reasons"]:
        print(f"- `{item}`")
    print()
    print("## Recovery Instruction")
    print()
    if result["recovery_state"] == RECOVERY_SAFE_RERUN:
        print("- **SAFE RECOVERY PATH:** re-run canonical chain in order:")
        print("  `Phase 3.6.9 -> Phase 3.7.0 -> Phase 3.7.1 -> Phase 3.7.2`")
        print("- Do **not** delete or rewrite prior lifecycle evidence.")
    elif result["recovery_state"] == RECOVERY_BLOCKED:
        print("- **RECOVERY BLOCKED:** a real safety failure/revocation is present.")
        print("- Inspect Phase 3.6.7 / 3.6.8 before any downstream re-run.")
    elif result["recovery_state"] == RECOVERY_NOT_NEEDED:
        print("- Current canonical chain is not FAIL_CLOSED; no recovery required.")
    else:
        print("- Root cause is not proven safe. Keep FAIL_CLOSED and review source evidence.")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")
    print("- Historical evidence rewrite: **DISABLED**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3722")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "fail_closed_diagnostic.json"), "w", encoding="utf-8") as handle:
        json.dump({"payload": payload, "evidence_document": evidence_doc}, handle, ensure_ascii=False, indent=2)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3722_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.2 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_observation_fail_closed_diagnostic_v92 (
    id bigint generated by default as identity primary key,
    diagnostic_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY',

    recovery_state text not null,
    safe_to_rerun_canonical_chain boolean not null default false,
    historical_rewrite_allowed boolean not null default false,

    runtime_supervision_state text not null default 'MISSING',
    controller_state text not null default 'MISSING',
    lifecycle_state text not null default 'MISSING',
    observation_state text not null default 'MISSING',
    readiness_state text not null default 'MISSING',
    promotion_state text not null default 'MISSING',

    runtime_supervision_date date,
    controller_date date,
    lifecycle_date date,
    observation_date date,
    readiness_date date,
    promotion_date date,

    observation_revocation_days integer not null default 0,
    readiness_revocation_days integer not null default 0,

    true_safety_failures jsonb not null default '[]'::jsonb,
    stale_or_propagation_issues jsonb not null default '[]'::jsonb,
    reason_codes jsonb not null default '[]'::jsonb,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint ck_phase3722_recovery_state check (
        recovery_state in (
            'NOT_NEEDED',
            'SAFE_CANONICAL_RERUN',
            'BLOCKED_BY_TRUE_SAFETY_FAILURE',
            'NEEDS_REVIEW'
        )
    ),
    constraint ck_phase3722_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3722_paper_only check (paper_only = true),
    constraint ck_phase3722_no_broker_api check (broker_api_used = false),
    constraint ck_phase3722_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3722_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3722_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3722_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3722_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_observation_fail_closed_diagnostic_v92_portfolio_date
    on public.paper_observation_fail_closed_diagnostic_v92 (portfolio_id, diagnostic_date);

create table if not exists public.paper_observation_fail_closed_diagnostic_audit_v92 (
    id bigint generated by default as identity primary key,
    diagnostic_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY',

    recovery_state text not null,
    safe_to_rerun_canonical_chain boolean not null default false,
    historical_rewrite_allowed boolean not null default false,

    runtime_supervision_state text not null default 'MISSING',
    controller_state text not null default 'MISSING',
    lifecycle_state text not null default 'MISSING',
    observation_state text not null default 'MISSING',
    readiness_state text not null default 'MISSING',
    promotion_state text not null default 'MISSING',

    runtime_supervision_date date,
    controller_date date,
    lifecycle_date date,
    observation_date date,
    readiness_date date,
    promotion_date date,

    observation_revocation_days integer not null default 0,
    readiness_revocation_days integer not null default 0,

    true_safety_failures jsonb not null default '[]'::jsonb,
    stale_or_propagation_issues jsonb not null default '[]'::jsonb,
    reason_codes jsonb not null default '[]'::jsonb,
    evidence_document jsonb not null default '{}'::jsonb,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),

    constraint ck_phase3722_audit_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3722_audit_paper_only check (paper_only = true),
    constraint ck_phase3722_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase3722_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3722_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3722_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3722_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3722_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_observation_fail_closed_diagnostic_audit_v92_portfolio_created
    on public.paper_observation_fail_closed_diagnostic_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_observation_fail_closed_diagnostic_v92 enable row level security;
alter table public.paper_observation_fail_closed_diagnostic_audit_v92 enable row level security;

comment on table public.paper_observation_fail_closed_diagnostic_v92 is
'GPT Quant V9.2 Phase 3.7.2.2 FAIL_CLOSED root-cause diagnostic and safe recovery-control state.';

comment on table public.paper_observation_fail_closed_diagnostic_audit_v92 is
'GPT Quant V9.2 Phase 3.7.2.2 immutable-style FAIL_CLOSED diagnostic audit evidence.';

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.2 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.2.2 - Observation FAIL_CLOSED Root Cause Diagnostic Recovery

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

permissions:
  contents: read

concurrency:
  group: phase3722-observation-fail-closed-diagnostic
  cancel-in-progress: false

jobs:
  fail-closed-root-cause-diagnostic:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Compile Phase 3.7.2.2
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py

      - name: Validate diagnostic safety contract
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY' \
            automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py

          grep -q '"historical_rewrite_allowed": False' \
            automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py

          echo "Phase 3.7.2.2 diagnostic safety contract: PASS"

      - name: Execute Phase 3.7.2.2
        shell: bash
        run: |
          mkdir -p artifacts/phase3722

          python automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase3722/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3722/summary.md ]; then
            cat artifacts/phase3722/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload diagnostic evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3722-fail-closed-diagnostic
          path: artifacts/phase3722/
          if-no-files-found: warn
          retention-days: 120
'@

Write-Utf8NoBom $ymlTarget $yml
Write-Host "Wrote: $ymlTarget" -ForegroundColor Green

Section "Static validation"

$pythonExe = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} else {
    Fail "Python not found in PATH."
}

if ($pythonExe -eq "py") {
    & py -3 -m py_compile $pyTarget
} else {
    & python -m py_compile $pyTarget
}

if ($LASTEXITCODE -ne 0) {
    Fail "Phase 3.7.2.2 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY",
    "SAFE_CANONICAL_RERUN",
    "BLOCKED_BY_TRUE_SAFETY_FAILURE",
    "NEEDS_REVIEW",
    "historical_rewrite_allowed",
    "paper_observation_fail_closed_diagnostic_v92"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.7.2.2 required token missing: $token"
    }
}

foreach ($forbidden in @(
    '"broker_api_used": True',
    '"broker_credentials_used": True',
    '"broker_order_submission_enabled": True',
    '"real_money_trading_enabled": True',
    '"live_money_release_authorized": True',
    '"historical_rewrite_allowed": True'
)) {
    if ($combined.Contains($forbidden)) {
        Fail "Forbidden capability detected: $forbidden"
    }
}

if ((Get-Item $sqlTarget).Length -lt 3000) {
    Fail "Phase 3.7.2.2 SQL unexpectedly small or empty."
}

Write-Host "FAIL_CLOSED diagnostic contract scan: PASS" -ForegroundColor Green
Write-Host "No historical rewrite scan: PASS" -ForegroundColor Green
Write-Host "Safe recovery gate scan: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary scan: PASS" -ForegroundColor Green

Section "Git status"
& git status --short

if ($AutoGit) {
    Section "Optional AutoGit"

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    & git add -- $sqlTarget $pyTarget $ymlTarget
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed"
    }

    $pending = (& git diff --cached --name-only)
    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged Phase 3.7.2.2 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.7.2.2 FAIL_CLOSED root cause diagnostic recovery"
        if ($LASTEXITCODE -ne 0) {
            Fail "git commit failed"
        }

        & git push origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git push origin main failed"
        }

        Write-Host "AutoGit commit + push: PASS" -ForegroundColor Green
    }
}

Section "DEPLOY COMPLETE"

Write-Host "Generated:" -ForegroundColor Green
Write-Host "  automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py"
Write-Host "  supabase/PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3722-observation-fail-closed-root-cause-diagnostic-recovery.yml"
Write-Host ""
Write-Host "Possible outcomes:" -ForegroundColor Cyan
Write-Host "  SAFE_CANONICAL_RERUN"
Write-Host "  BLOCKED_BY_TRUE_SAFETY_FAILURE"
Write-Host "  NEEDS_REVIEW"
Write-Host "  NOT_NEEDED"
Write-Host ""
Write-Host "Important:" -ForegroundColor Yellow
Write-Host "  This phase does NOT force PASS."
Write-Host "  This phase does NOT delete/rewrite prior lifecycle evidence."
Write-Host "  SAFE_CANONICAL_RERUN => re-run 3.6.9 -> 3.7.0 -> 3.7.1 -> 3.7.2."
Write-Host "  BLOCKED_BY_TRUE_SAFETY_FAILURE => inspect 3.6.7 / 3.6.8 first."
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run supabase/PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.2.2 - Observation FAIL_CLOSED Root Cause Diagnostic Recovery."
Write-Host "  4) Use the Summary to choose the recovery path."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
