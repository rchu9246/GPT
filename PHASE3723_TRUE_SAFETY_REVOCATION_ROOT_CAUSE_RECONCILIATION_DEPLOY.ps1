#requires -Version 5.1
<#
PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.3 — True Safety Revocation Root Cause Reconciliation

Purpose
-------
Diagnose the actual canonical condition that caused the Phase 3.6.7 runtime
supervision state to become REVOKED, and reconcile whether the revocation is:

  TRUE_SAFETY_VIOLATION
    - real current canonical safety condition;
    - keep REVOKED / FAIL_CLOSED;
    - recovery remains blocked.

  STALE_OR_FALSE_REVOCATION
    - downstream revocation exists, but current canonical upstream evidence
      proves the revocation was caused by stale/misaligned propagation;
    - historical evidence is NOT rewritten;
    - canonical recovery may be attempted only by re-running the normal chain.

  NEEDS_REVIEW
    - root cause cannot be proven safe either way;
    - keep fail-closed.

This phase NEVER:
  - edits historical lifecycle evidence;
  - flips REVOKED to ACTIVE directly;
  - enables broker order submission;
  - enables real-money trading.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py
  supabase/PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase3723-true-safety-revocation-root-cause-reconciliation.yml
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

Section "GPT Quant V9.2 — Phase 3.7.2.3 True Safety Revocation Root Cause Reconciliation"

$repo = $null
try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = $null
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this deployment package from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py",
    "automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py",
    "automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py",
    "automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase3723-true-safety-revocation-root-cause-reconciliation.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase3723-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.7.2.3 reconciliation engine"

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
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

TRUE_SAFETY_VIOLATION = "TRUE_SAFETY_VIOLATION"
STALE_OR_FALSE_REVOCATION = "STALE_OR_FALSE_REVOCATION"
NEEDS_REVIEW = "NEEDS_REVIEW"
NO_REVOCATION = "NO_ACTIVE_REVOCATION"

SAFE_SUPERVISION_STATES = {
    "CONTINUE_ACTIVE",
    "CONTINUE_WITH_OBSERVATION",
    "ACTIVE",
    "HEALTHY",
}
REVOKED_SUPERVISION_STATES = {
    "REVOKED",
    "FAIL_CLOSED",
    "STOP",
    "BLOCKED",
}
SAFE_CONTROLLER_STATES = {
    "COMPLETED",
    "COMPLETED_WITH_OBSERVATION",
}
PASS_LIFECYCLE_STATES = {
    "PASS",
    "PASS_WITH_OBSERVATION",
}

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

def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

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

    def request(
        self,
        method: str,
        table: str,
        query: str = "",
        payload: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> Any:
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
        self.request(
            "POST",
            table,
            query=query,
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )

def latest(sb: Supabase, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def latest_compatible(
    sb: Supabase,
    candidates: List[Tuple[str, str]],
    portfolio_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], List[str]]:
    notes: List[str] = []

    for table, order_column in candidates:
        try:
            row = latest(sb, table, portfolio_id, order_column)
            notes.append(f"TABLE_SELECTED:{table}")
            return row, table, notes
        except RuntimeError as exc:
            message = str(exc)
            if (
                "HTTP 404" in message
                or "PGRST205" in message
                or "Could not find the table" in message
            ):
                notes.append(f"TABLE_MISSING:{table}")
                continue
            raise

    notes.append("NO_COMPATIBLE_TABLE_FOUND")
    return None, None, notes

def row_date(row: Optional[Dict[str, Any]], *names: str) -> Optional[str]:
    if not row:
        return None
    for name in names:
        value = row.get(name)
        if value:
            return str(value)[:10]
    return None

def state(row: Optional[Dict[str, Any]], *names: str, default: str = "MISSING") -> str:
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

def first_present(row: Optional[Dict[str, Any]], names: List[str]) -> Any:
    if not row:
        return None
    for name in names:
        if name in row:
            return row.get(name)
    return None

def extract_safety_reasons(row: Optional[Dict[str, Any]]) -> List[str]:
    if not row:
        return []

    reasons: List[str] = []
    candidate_fields = [
        "reason_codes",
        "reasons",
        "revocation_reasons",
        "safety_reasons",
        "failure_reasons",
        "hard_failures",
    ]

    for field in candidate_fields:
        value = row.get(field)
        if value is None:
            continue

        if isinstance(value, list):
            reasons.extend(str(x) for x in value)
        elif isinstance(value, dict):
            reasons.extend(f"{k}:{v}" for k, v in value.items())
        else:
            reasons.append(str(value))

    return reasons

def reconcile(
    supervision: Optional[Dict[str, Any]],
    controller: Optional[Dict[str, Any]],
    lifecycle: Optional[Dict[str, Any]],
    diagnostic: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    reasons: List[str] = []
    true_violations: List[str] = []
    stale_indicators: List[str] = []

    supervision_state = state(
        supervision,
        "supervision_state",
        "runtime_supervision_state",
        "state",
    )
    controller_state = state(controller, "controller_state")
    lifecycle_state = state(lifecycle, "lifecycle_state")

    supervision_revoked = (
        truth(supervision, "safety_revocation_triggered", default=False)
        or supervision_state in REVOKED_SUPERVISION_STATES
    )
    controller_revoked = truth(controller, "safety_revocation_triggered", default=False)
    lifecycle_revoked = truth(lifecycle, "safety_revocation_triggered", default=False)

    paper_only = truth(supervision, "paper_only", default=True)
    broker_api_used = truth(supervision, "broker_api_used", default=False)
    broker_credentials_used = truth(supervision, "broker_credentials_used", default=False)
    broker_submission_enabled = truth(
        supervision,
        "broker_order_submission_enabled",
        "broker_order_submission",
        default=False,
    )
    real_money_enabled = truth(
        supervision,
        "real_money_trading_enabled",
        "real_money_trading",
        default=False,
    )
    live_release_authorized = truth(
        supervision,
        "live_money_release_authorized",
        default=False,
    )
    fail_closed_policy = truth(supervision, "fail_closed_policy", default=True)

    if not paper_only:
        true_violations.append("PAPER_ONLY_DISABLED")
    if broker_api_used:
        true_violations.append("BROKER_API_USED")
    if broker_credentials_used:
        true_violations.append("BROKER_CREDENTIALS_USED")
    if broker_submission_enabled:
        true_violations.append("BROKER_ORDER_SUBMISSION_ENABLED")
    if real_money_enabled:
        true_violations.append("REAL_MONEY_TRADING_ENABLED")
    if live_release_authorized:
        true_violations.append("LIVE_MONEY_RELEASE_AUTHORIZED")
    if not fail_closed_policy:
        true_violations.append("FAIL_CLOSED_POLICY_DISABLED")

    if controller_revoked:
        true_violations.append("CONTROLLER_SAFETY_REVOCATION_TRIGGERED")
    if lifecycle_revoked:
        true_violations.append("LIFECYCLE_SAFETY_REVOCATION_TRIGGERED")

    supervision_reasons = extract_safety_reasons(supervision)
    controller_reasons = extract_safety_reasons(controller)
    lifecycle_reasons = extract_safety_reasons(lifecycle)

    all_reason_text = " | ".join(supervision_reasons + controller_reasons + lifecycle_reasons).upper()

    explicit_unsafe_tokens = [
        "BROKER",
        "REAL_MONEY",
        "LIVE_MONEY",
        "UNAUTHORIZED",
        "CHAIN_BREAK",
        "DRAWNDOWN_LIMIT",
        "DRAWDOWN_LIMIT",
        "CREDENTIAL",
        "ORDER_SUBMISSION",
        "SAFETY_VIOLATION",
    ]
    for token in explicit_unsafe_tokens:
        if token in all_reason_text:
            true_violations.append(f"EXPLICIT_UNSAFE_REASON:{token}")

    dates = {
        "supervision": row_date(supervision, "supervision_date", "run_date", "created_at"),
        "controller": row_date(controller, "controller_date", "run_date", "created_at"),
        "lifecycle": row_date(lifecycle, "evidence_date", "run_date", "created_at"),
        "diagnostic": row_date(diagnostic, "diagnostic_date", "created_at"),
    }

    source_dates = [d for k, d in dates.items() if k != "diagnostic" and d]
    newest_source_date = max(source_dates) if source_dates else None

    if newest_source_date:
        for name in ("supervision", "controller", "lifecycle"):
            d = dates[name]
            if d and d != newest_source_date:
                stale_indicators.append(f"{name.upper()}_DATE_MISMATCH:{d}!={newest_source_date}")

    if (
        supervision_revoked
        and not true_violations
        and controller_state in SAFE_CONTROLLER_STATES
        and lifecycle_state in PASS_LIFECYCLE_STATES
    ):
        stale_indicators.append("SUPERVISION_REVOKED_WITH_HEALTHY_DOWNSTREAM_CANONICAL_STATE")

    if (
        supervision_revoked
        and not true_violations
        and not supervision_reasons
        and not controller_revoked
        and not lifecycle_revoked
    ):
        stale_indicators.append("REVOCATION_WITHOUT_EXPLICIT_CURRENT_SAFETY_REASON")

    if true_violations:
        classification = TRUE_SAFETY_VIOLATION
        recovery_authorized = False
        reasons.extend(true_violations)
    elif supervision_revoked and stale_indicators:
        classification = STALE_OR_FALSE_REVOCATION
        recovery_authorized = True
        reasons.extend(stale_indicators)
    elif not supervision_revoked:
        classification = NO_REVOCATION
        recovery_authorized = False
        reasons.append("LATEST_SUPERVISION_NOT_REVOKED")
    else:
        classification = NEEDS_REVIEW
        recovery_authorized = False
        reasons.append("REVOCATION_PRESENT_BUT_ROOT_CAUSE_NOT_PROVEN")

    if supervision_reasons:
        reasons.extend(f"SUPERVISION_REASON:{x}" for x in supervision_reasons)
    if controller_reasons:
        reasons.extend(f"CONTROLLER_REASON:{x}" for x in controller_reasons)
    if lifecycle_reasons:
        reasons.extend(f"LIFECYCLE_REASON:{x}" for x in lifecycle_reasons)

    return {
        "classification": classification,
        "canonical_recovery_authorized": recovery_authorized,
        "historical_rewrite_allowed": False,

        "supervision_state": supervision_state,
        "controller_state": controller_state,
        "lifecycle_state": lifecycle_state,

        "supervision_revoked": supervision_revoked,
        "controller_revoked": controller_revoked,
        "lifecycle_revoked": lifecycle_revoked,

        "paper_only": paper_only,
        "broker_api_used": broker_api_used,
        "broker_credentials_used": broker_credentials_used,
        "broker_order_submission_enabled": broker_submission_enabled,
        "real_money_trading_enabled": real_money_enabled,
        "live_money_release_authorized": live_release_authorized,
        "fail_closed_policy": fail_closed_policy,

        "dates": dates,
        "true_violations": sorted(set(true_violations)),
        "stale_indicators": sorted(set(stale_indicators)),
        "reason_codes": reasons,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--reconciliation-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.reconciliation_date)

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = Supabase(url, key)

    supervision, supervision_table, supervision_notes = latest_compatible(
        sb,
        [
            ("paper_runtime_supervision_state_v92", "supervision_date"),
            ("paper_runtime_supervision_v92", "supervision_date"),
        ],
        args.portfolio_id,
    )

    controller = latest(
        sb,
        "paper_daily_autonomous_controller_v92",
        args.portfolio_id,
        "controller_date",
    )

    lifecycle = latest(
        sb,
        "paper_daily_lifecycle_evidence_v92",
        args.portfolio_id,
        "evidence_date",
    )

    diagnostic = latest(
        sb,
        "paper_observation_fail_closed_diagnostic_v92",
        args.portfolio_id,
        "diagnostic_date",
    )

    result = reconcile(supervision, controller, lifecycle, diagnostic)
    result["supervision_table"] = supervision_table
    result["supervision_compatibility_notes"] = supervision_notes
    result["reason_codes"].extend(supervision_notes)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "reconciliation_date": args.reconciliation_date,
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
        "reconciliation_date": args.reconciliation_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "classification": result["classification"],
        "canonical_recovery_authorized": result["canonical_recovery_authorized"],
        "historical_rewrite_allowed": False,

        "supervision_table": result["supervision_table"],
        "supervision_state": result["supervision_state"],
        "controller_state": result["controller_state"],
        "lifecycle_state": result["lifecycle_state"],

        "supervision_date": result["dates"]["supervision"],
        "controller_date": result["dates"]["controller"],
        "lifecycle_date": result["dates"]["lifecycle"],

        "supervision_revoked": result["supervision_revoked"],
        "controller_revoked": result["controller_revoked"],
        "lifecycle_revoked": result["lifecycle_revoked"],

        "true_violations": result["true_violations"],
        "stale_indicators": result["stale_indicators"],
        "reason_codes": result["reason_codes"],

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

    sb.upsert(
        "paper_true_safety_revocation_reconciliation_v92",
        payload,
        "portfolio_id,reconciliation_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_true_safety_revocation_reconciliation_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.3")
    print()
    print("## True Safety Revocation Root Cause Reconciliation")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Reconciliation Date: `{args.reconciliation_date}`")
    print(f"- Classification: **{result['classification']}**")
    print(f"- Canonical Recovery Authorized: **{'YES' if result['canonical_recovery_authorized'] else 'NO'}**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical State Snapshot")
    print()
    print(f"- Runtime Supervision Table: **{result['supervision_table'] or 'NOT_FOUND'}**")
    print(f"- Supervision: **{result['supervision_state']}** (date `{result['dates']['supervision'] or 'MISSING'}`)")
    print(f"- Controller: **{result['controller_state']}** (date `{result['dates']['controller'] or 'MISSING'}`)")
    print(f"- Lifecycle: **{result['lifecycle_state']}** (date `{result['dates']['lifecycle'] or 'MISSING'}`)")
    print()
    print("## Current Safety Facts")
    print()
    print(f"- Supervision Revoked: **{'YES' if result['supervision_revoked'] else 'NO'}**")
    print(f"- Controller Revoked: **{'YES' if result['controller_revoked'] else 'NO'}**")
    print(f"- Lifecycle Revoked: **{'YES' if result['lifecycle_revoked'] else 'NO'}**")
    print(f"- Paper Only: **{'YES' if result['paper_only'] else 'NO'}**")
    print(f"- Broker API Used: **{'YES' if result['broker_api_used'] else 'NO'}**")
    print(f"- Broker Credentials Used: **{'YES' if result['broker_credentials_used'] else 'NO'}**")
    print(f"- Broker Order Submission Enabled: **{'YES' if result['broker_order_submission_enabled'] else 'NO'}**")
    print(f"- Real-Money Trading Enabled: **{'YES' if result['real_money_trading_enabled'] else 'NO'}**")
    print(f"- Live-Money Release Authorized: **{'YES' if result['live_money_release_authorized'] else 'NO'}**")
    print(f"- Fail-Closed Policy: **{'ENABLED' if result['fail_closed_policy'] else 'DISABLED'}**")
    print()
    print("## True Violations")
    print()
    if result["true_violations"]:
        for item in result["true_violations"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Stale / False-Revocation Indicators")
    print()
    if result["stale_indicators"]:
        for item in result["stale_indicators"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Reconciliation Reasons")
    print()
    for item in result["reason_codes"]:
        print(f"- `{item}`")
    print()
    print("## Recovery Instruction")
    print()
    if result["classification"] == TRUE_SAFETY_VIOLATION:
        print("- **KEEP REVOKED / FAIL_CLOSED.**")
        print("- Resolve the underlying safety condition before any canonical recovery.")
    elif result["classification"] == STALE_OR_FALSE_REVOCATION:
        print("- **SAFE CANONICAL RECOVERY MAY BE ATTEMPTED.**")
        print("- Do not edit historical rows.")
        print("- Re-run the normal chain in order:")
        print("  `Phase 3.6.7 -> 3.6.8 -> 3.6.9 -> 3.7.0 -> 3.7.1 -> 3.7.2`")
    elif result["classification"] == NO_REVOCATION:
        print("- Latest supervision is not revoked. No special recovery required.")
    else:
        print("- Root cause is not proven safe. Keep fail-closed and review source evidence.")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Historical evidence rewrite: **DISABLED**")
    print("- Fail-closed policy: **ENABLED**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3723")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "true_safety_revocation_reconciliation.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "payload": payload,
                "evidence_document": evidence_doc,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3723_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.3 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_true_safety_revocation_reconciliation_v92 (
    id bigint generated by default as identity primary key,
    reconciliation_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION',

    classification text not null,
    canonical_recovery_authorized boolean not null default false,
    historical_rewrite_allowed boolean not null default false,

    supervision_table text,
    supervision_state text not null default 'MISSING',
    controller_state text not null default 'MISSING',
    lifecycle_state text not null default 'MISSING',

    supervision_date date,
    controller_date date,
    lifecycle_date date,

    supervision_revoked boolean not null default false,
    controller_revoked boolean not null default false,
    lifecycle_revoked boolean not null default false,

    true_violations jsonb not null default '[]'::jsonb,
    stale_indicators jsonb not null default '[]'::jsonb,
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

    constraint ck_phase3723_classification check (
        classification in (
            'TRUE_SAFETY_VIOLATION',
            'STALE_OR_FALSE_REVOCATION',
            'NEEDS_REVIEW',
            'NO_ACTIVE_REVOCATION'
        )
    ),
    constraint ck_phase3723_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3723_paper_only check (paper_only = true),
    constraint ck_phase3723_no_broker_api check (broker_api_used = false),
    constraint ck_phase3723_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3723_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3723_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3723_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3723_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_true_safety_revocation_reconciliation_v92_portfolio_date
    on public.paper_true_safety_revocation_reconciliation_v92 (portfolio_id, reconciliation_date);

create table if not exists public.paper_true_safety_revocation_reconciliation_audit_v92 (
    id bigint generated by default as identity primary key,
    reconciliation_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION',

    classification text not null,
    canonical_recovery_authorized boolean not null default false,
    historical_rewrite_allowed boolean not null default false,

    supervision_table text,
    supervision_state text not null default 'MISSING',
    controller_state text not null default 'MISSING',
    lifecycle_state text not null default 'MISSING',

    supervision_date date,
    controller_date date,
    lifecycle_date date,

    supervision_revoked boolean not null default false,
    controller_revoked boolean not null default false,
    lifecycle_revoked boolean not null default false,

    true_violations jsonb not null default '[]'::jsonb,
    stale_indicators jsonb not null default '[]'::jsonb,
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

    constraint ck_phase3723_audit_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3723_audit_paper_only check (paper_only = true),
    constraint ck_phase3723_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase3723_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3723_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3723_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3723_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3723_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_true_safety_revocation_reconciliation_audit_v92_portfolio_created
    on public.paper_true_safety_revocation_reconciliation_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_true_safety_revocation_reconciliation_v92 enable row level security;
alter table public.paper_true_safety_revocation_reconciliation_audit_v92 enable row level security;

comment on table public.paper_true_safety_revocation_reconciliation_v92 is
'GPT Quant V9.2 Phase 3.7.2.3 true safety revocation root-cause reconciliation state.';

comment on table public.paper_true_safety_revocation_reconciliation_audit_v92 is
'GPT Quant V9.2 Phase 3.7.2.3 immutable-style true safety revocation reconciliation audit evidence.';

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.3 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.2.3 - True Safety Revocation Root Cause Reconciliation

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
  group: phase3723-true-safety-revocation-reconciliation
  cancel-in-progress: false

jobs:
  true-safety-revocation-root-cause-reconciliation:
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

      - name: Compile Phase 3.7.2.3
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py

      - name: Validate reconciliation safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION' \
            automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py

          grep -q '"historical_rewrite_allowed": False' \
            automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py

          echo "Phase 3.7.2.3 reconciliation safety contract: PASS"

      - name: Execute Phase 3.7.2.3
        shell: bash
        run: |
          mkdir -p artifacts/phase3723

          python automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase3723/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3723/summary.md ]; then
            cat artifacts/phase3723/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload reconciliation evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3723-true-safety-revocation-reconciliation
          path: artifacts/phase3723/
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
    Fail "Phase 3.7.2.3 Python compile failed."
}

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION",
    "TRUE_SAFETY_VIOLATION",
    "STALE_OR_FALSE_REVOCATION",
    "NEEDS_REVIEW",
    "paper_true_safety_revocation_reconciliation_v92",
    "paper_runtime_supervision_state_v92"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Required Phase 3.7.2.3 token missing: $token"
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
    Fail "Phase 3.7.2.3 SQL unexpectedly small or empty."
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "True-safety reconciliation contract scan: PASS" -ForegroundColor Green
Write-Host "Canonical supervision compatibility scan: PASS" -ForegroundColor Green
Write-Host "No historical rewrite scan: PASS" -ForegroundColor Green
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
        Write-Host "No staged Phase 3.7.2.3 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.7.2.3 true safety revocation root cause reconciliation"
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
Write-Host "  automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py"
Write-Host "  supabase/PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3723-true-safety-revocation-root-cause-reconciliation.yml"
Write-Host ""
Write-Host "Possible results:" -ForegroundColor Cyan
Write-Host "  TRUE_SAFETY_VIOLATION"
Write-Host "  STALE_OR_FALSE_REVOCATION"
Write-Host "  NEEDS_REVIEW"
Write-Host "  NO_ACTIVE_REVOCATION"
Write-Host ""
Write-Host "Recovery policy:" -ForegroundColor Yellow
Write-Host "  TRUE_SAFETY_VIOLATION => keep REVOKED / FAIL_CLOSED."
Write-Host "  STALE_OR_FALSE_REVOCATION => re-run normal canonical chain only."
Write-Host "  NEEDS_REVIEW => keep fail-closed."
Write-Host "  Historical evidence rewrite remains DISABLED."
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run supabase/PHASE3723_TRUE_SAFETY_REVOCATION_ROOT_CAUSE_RECONCILIATION.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.2.3 - True Safety Revocation Root Cause Reconciliation."
Write-Host "  4) Use the Summary classification to choose the next recovery step."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
