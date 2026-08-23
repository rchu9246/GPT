#requires -Version 5.1
<#
PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.4 — True Safety Violation Evidence Forensics + Recovery Eligibility

Purpose
-------
Investigate the canonical evidence behind the current TRUE_SAFETY_VIOLATION
classification and determine whether recovery is eligible without mutating
historical evidence or bypassing fail-closed controls.

This phase:
  - traces the latest supervision/controller/lifecycle evidence;
  - extracts safety/revocation reason codes;
  - compares canonical dates and evidence hashes;
  - checks paper-only / broker / real-money safety facts;
  - classifies the revocation as:
      RECOVERY_ELIGIBLE_STALE_OR_LEGACY
      RECOVERY_BLOCKED_TRUE_CURRENT_VIOLATION
      RECOVERY_BLOCKED_INSUFFICIENT_EVIDENCE
      NO_ACTIVE_VIOLATION
  - persists forensic evidence and an audit trail.

This phase NEVER:
  - rewrites historical rows;
  - flips REVOKED to ACTIVE;
  - changes observation-day history;
  - enables broker/live-money trading.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py
  supabase/PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase3724-true-safety-violation-evidence-forensics-and-recovery-eligibility.yml
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

Section "GPT Quant V9.2 — Phase 3.7.2.4 Safety Violation Evidence Forensics"

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
    "automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py",
    "automation/v92/paper_trading_phase3723_true_safety_revocation_root_cause_reconciliation.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase3724-true-safety-violation-evidence-forensics-and-recovery-eligibility.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase3724-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.7.2.4 forensic engine"

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

CONTRACT = "PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

RECOVERY_ELIGIBLE = "RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
RECOVERY_BLOCKED_TRUE = "RECOVERY_BLOCKED_TRUE_CURRENT_VIOLATION"
RECOVERY_BLOCKED_EVIDENCE = "RECOVERY_BLOCKED_INSUFFICIENT_EVIDENCE"
NO_ACTIVE_VIOLATION = "NO_ACTIVE_VIOLATION"

TRUE_UNSAFE_TOKENS = {
    "BROKER_API_USED",
    "BROKER_CREDENTIALS_USED",
    "BROKER_ORDER_SUBMISSION_ENABLED",
    "REAL_MONEY_TRADING_ENABLED",
    "LIVE_MONEY_RELEASE_AUTHORIZED",
    "PAPER_ONLY_DISABLED",
    "FAIL_CLOSED_POLICY_DISABLED",
    "EVIDENCE_CHAIN_BREAK",
    "UNAUTHORIZED_ORDER",
    "DRAWDOWN_LIMIT_EXCEEDED",
    "SAFETY_VIOLATION",
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
            msg = str(exc)
            if "HTTP 404" in msg or "PGRST205" in msg or "Could not find the table" in msg:
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
        if name in row and row.get(name) is not None:
            return str(row.get(name)).upper()
    return default

def reason_list(row: Optional[Dict[str, Any]]) -> List[str]:
    if not row:
        return []
    result: List[str] = []
    for field in (
        "reason_codes",
        "reasons",
        "revocation_reasons",
        "safety_reasons",
        "failure_reasons",
        "hard_failures",
        "notes",
    ):
        value = row.get(field)
        if value is None:
            continue
        if isinstance(value, list):
            result.extend(str(x) for x in value)
        elif isinstance(value, dict):
            result.extend(f"{k}:{v}" for k, v in value.items())
        else:
            result.append(str(value))
    return result

def bool_fact(row: Optional[Dict[str, Any]], names: List[str], default: bool) -> bool:
    if not row:
        return default
    for name in names:
        if name in row:
            return as_bool(row.get(name), default)
    return default

def sha(row: Optional[Dict[str, Any]]) -> Optional[str]:
    if not row:
        return None
    return row.get("evidence_sha256") or row.get("evidence_hash") or row.get("sha256")

def forensic_classify(
    supervision: Optional[Dict[str, Any]],
    controller: Optional[Dict[str, Any]],
    lifecycle: Optional[Dict[str, Any]],
    diagnostic: Optional[Dict[str, Any]],
    reconciliation: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    reasons: List[str] = []
    current_violations: List[str] = []
    stale_or_legacy_indicators: List[str] = []
    evidence_gaps: List[str] = []

    supervision_state = state(supervision, "supervision_state", "runtime_supervision_state", "state")
    controller_state = state(controller, "controller_state")
    lifecycle_state = state(lifecycle, "lifecycle_state")
    reconciliation_class = state(reconciliation, "classification")

    paper_only = bool_fact(supervision, ["paper_only"], True)
    broker_api_used = bool_fact(supervision, ["broker_api_used"], False)
    broker_credentials_used = bool_fact(supervision, ["broker_credentials_used"], False)
    broker_submission_enabled = bool_fact(
        supervision,
        ["broker_order_submission_enabled", "broker_order_submission"],
        False,
    )
    real_money_enabled = bool_fact(
        supervision,
        ["real_money_trading_enabled", "real_money_trading"],
        False,
    )
    live_release = bool_fact(supervision, ["live_money_release_authorized"], False)
    fail_closed_policy = bool_fact(supervision, ["fail_closed_policy"], True)

    if not paper_only:
        current_violations.append("PAPER_ONLY_DISABLED")
    if broker_api_used:
        current_violations.append("BROKER_API_USED")
    if broker_credentials_used:
        current_violations.append("BROKER_CREDENTIALS_USED")
    if broker_submission_enabled:
        current_violations.append("BROKER_ORDER_SUBMISSION_ENABLED")
    if real_money_enabled:
        current_violations.append("REAL_MONEY_TRADING_ENABLED")
    if live_release:
        current_violations.append("LIVE_MONEY_RELEASE_AUTHORIZED")
    if not fail_closed_policy:
        current_violations.append("FAIL_CLOSED_POLICY_DISABLED")

    combined_reason_text = " | ".join(
        reason_list(supervision)
        + reason_list(controller)
        + reason_list(lifecycle)
        + reason_list(diagnostic)
        + reason_list(reconciliation)
    ).upper()

    for token in sorted(TRUE_UNSAFE_TOKENS):
        if token in combined_reason_text:
            current_violations.append(f"EXPLICIT_REASON:{token}")

    dates = {
        "supervision": row_date(supervision, "supervision_date", "run_date", "created_at"),
        "controller": row_date(controller, "controller_date", "run_date", "created_at"),
        "lifecycle": row_date(lifecycle, "evidence_date", "run_date", "created_at"),
        "diagnostic": row_date(diagnostic, "diagnostic_date", "created_at"),
        "reconciliation": row_date(reconciliation, "reconciliation_date", "created_at"),
    }

    source_dates = [dates[k] for k in ("supervision", "controller", "lifecycle") if dates[k]]
    newest_source_date = max(source_dates) if source_dates else None

    if newest_source_date:
        for key in ("supervision", "controller", "lifecycle"):
            d = dates[key]
            if d and d != newest_source_date:
                stale_or_legacy_indicators.append(
                    f"{key.upper()}_DATE_MISMATCH:{d}!={newest_source_date}"
                )

    if reconciliation_class == "TRUE_SAFETY_VIOLATION" and not current_violations:
        stale_or_legacy_indicators.append(
            "PRIOR_TRUE_SAFETY_CLASSIFICATION_WITHOUT_CURRENT_EXPLICIT_UNSAFE_FACT"
        )

    if supervision_state == "REVOKED" and not current_violations:
        stale_or_legacy_indicators.append(
            "REVOKED_STATE_WITHOUT_CURRENT_EXPLICIT_UNSAFE_FACT"
        )

    if controller_state == "FAIL_CLOSED" and supervision_state == "REVOKED" and not current_violations:
        stale_or_legacy_indicators.append(
            "DOWNSTREAM_FAIL_CLOSED_PROPAGATED_FROM_REVOKED_SUPERVISION"
        )

    if not supervision:
        evidence_gaps.append("SUPERVISION_ROW_MISSING")
    if not controller:
        evidence_gaps.append("CONTROLLER_ROW_MISSING")
    if not lifecycle:
        evidence_gaps.append("LIFECYCLE_ROW_MISSING")
    if not diagnostic:
        evidence_gaps.append("PHASE3722_DIAGNOSTIC_ROW_MISSING")
    if not reconciliation:
        evidence_gaps.append("PHASE3723_RECONCILIATION_ROW_MISSING")

    hashes = {
        "supervision": sha(supervision),
        "controller": sha(controller),
        "lifecycle": sha(lifecycle),
        "diagnostic": sha(diagnostic),
        "reconciliation": sha(reconciliation),
    }

    for key, value in hashes.items():
        if not value:
            evidence_gaps.append(f"{key.upper()}_EVIDENCE_SHA_MISSING")

    if current_violations:
        classification = RECOVERY_BLOCKED_TRUE
        recovery_eligible = False
        reasons.extend(sorted(set(current_violations)))
    elif evidence_gaps:
        classification = RECOVERY_BLOCKED_EVIDENCE
        recovery_eligible = False
        reasons.extend(sorted(set(evidence_gaps)))
        reasons.extend(sorted(set(stale_or_legacy_indicators)))
    elif supervision_state != "REVOKED":
        classification = NO_ACTIVE_VIOLATION
        recovery_eligible = False
        reasons.append("LATEST_SUPERVISION_NOT_REVOKED")
    elif stale_or_legacy_indicators:
        classification = RECOVERY_ELIGIBLE
        recovery_eligible = True
        reasons.extend(sorted(set(stale_or_legacy_indicators)))
    else:
        classification = RECOVERY_BLOCKED_EVIDENCE
        recovery_eligible = False
        reasons.append("REVOCATION_PRESENT_WITHOUT_PROVABLE_RECOVERY_BASIS")

    return {
        "classification": classification,
        "recovery_eligible": recovery_eligible,
        "historical_rewrite_allowed": False,
        "supervision_state": supervision_state,
        "controller_state": controller_state,
        "lifecycle_state": lifecycle_state,
        "reconciliation_class": reconciliation_class,
        "dates": dates,
        "hashes": hashes,
        "current_violations": sorted(set(current_violations)),
        "stale_or_legacy_indicators": sorted(set(stale_or_legacy_indicators)),
        "evidence_gaps": sorted(set(evidence_gaps)),
        "reason_codes": reasons,
        "safety_facts": {
            "paper_only": paper_only,
            "broker_api_used": broker_api_used,
            "broker_credentials_used": broker_credentials_used,
            "broker_order_submission_enabled": broker_submission_enabled,
            "real_money_trading_enabled": real_money_enabled,
            "live_money_release_authorized": live_release,
            "fail_closed_policy": fail_closed_policy,
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--forensic-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.forensic_date)

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
    reconciliation = latest(
        sb,
        "paper_true_safety_revocation_reconciliation_v92",
        args.portfolio_id,
        "reconciliation_date",
    )

    result = forensic_classify(
        supervision,
        controller,
        lifecycle,
        diagnostic,
        reconciliation,
    )
    result["supervision_table"] = supervision_table
    result["supervision_compatibility_notes"] = supervision_notes
    result["reason_codes"].extend(supervision_notes)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "forensic_date": args.forensic_date,
        "result": result,
        "safety": {
            "paper_only": True,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "historical_rewrite_allowed": False,
            "fail_closed_policy": True,
        },
    }
    evidence_sha = stable_hash(evidence_doc)

    payload = {
        "forensic_date": args.forensic_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "classification": result["classification"],
        "recovery_eligible": result["recovery_eligible"],
        "historical_rewrite_allowed": False,

        "supervision_table": result["supervision_table"],
        "supervision_state": result["supervision_state"],
        "controller_state": result["controller_state"],
        "lifecycle_state": result["lifecycle_state"],
        "prior_reconciliation_class": result["reconciliation_class"],

        "supervision_date": result["dates"]["supervision"],
        "controller_date": result["dates"]["controller"],
        "lifecycle_date": result["dates"]["lifecycle"],
        "diagnostic_date": result["dates"]["diagnostic"],
        "reconciliation_date": result["dates"]["reconciliation"],

        "current_violations": result["current_violations"],
        "stale_or_legacy_indicators": result["stale_or_legacy_indicators"],
        "evidence_gaps": result["evidence_gaps"],
        "reason_codes": result["reason_codes"],

        "source_hashes": result["hashes"],

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
        "paper_true_safety_violation_forensics_v92",
        payload,
        "portfolio_id,forensic_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_true_safety_violation_forensics_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.4")
    print()
    print("## True Safety Violation Evidence Forensics + Recovery Eligibility")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Forensic Date: `{args.forensic_date}`")
    print(f"- Classification: **{result['classification']}**")
    print(f"- Recovery Eligible: **{'YES' if result['recovery_eligible'] else 'NO'}**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical Evidence Sources")
    print()
    print(f"- Runtime Supervision Table: **{result['supervision_table'] or 'NOT_FOUND'}**")
    print(f"- Supervision: **{result['supervision_state']}** (date `{result['dates']['supervision'] or 'MISSING'}`)")
    print(f"- Controller: **{result['controller_state']}** (date `{result['dates']['controller'] or 'MISSING'}`)")
    print(f"- Lifecycle: **{result['lifecycle_state']}** (date `{result['dates']['lifecycle'] or 'MISSING'}`)")
    print(f"- Prior Reconciliation: **{result['reconciliation_class']}**")
    print()
    print("## Current Unsafe Facts")
    print()
    if result["current_violations"]:
        for item in result["current_violations"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Stale / Legacy Indicators")
    print()
    if result["stale_or_legacy_indicators"]:
        for item in result["stale_or_legacy_indicators"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Evidence Gaps")
    print()
    if result["evidence_gaps"]:
        for item in result["evidence_gaps"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Recovery Instruction")
    print()
    if result["classification"] == RECOVERY_ELIGIBLE:
        print("- **RECOVERY ELIGIBLE:** stale/legacy revocation is sufficiently evidenced.")
        print("- Do not edit historical rows.")
        print("- Next phase may perform controlled canonical recovery and then re-run:")
        print("  `3.6.7 -> 3.6.8 -> 3.6.9 -> 3.7.0 -> 3.7.1 -> 3.7.2`")
    elif result["classification"] == RECOVERY_BLOCKED_TRUE:
        print("- **RECOVERY BLOCKED:** current unsafe fact(s) still exist.")
        print("- Resolve the actual safety condition before any recovery attempt.")
    elif result["classification"] == RECOVERY_BLOCKED_EVIDENCE:
        print("- **RECOVERY BLOCKED:** evidence is insufficient to prove a safe recovery.")
        print("- Keep fail-closed and inspect the listed evidence gaps.")
    else:
        print("- Latest supervision is not actively revoked; no special recovery is required.")
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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3724")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "true_safety_violation_forensics.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {"payload": payload, "evidence_document": evidence_doc},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3724_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.4 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_true_safety_violation_forensics_v92 (
    id bigint generated by default as identity primary key,
    forensic_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY',

    classification text not null,
    recovery_eligible boolean not null default false,
    historical_rewrite_allowed boolean not null default false,

    supervision_table text,
    supervision_state text not null default 'MISSING',
    controller_state text not null default 'MISSING',
    lifecycle_state text not null default 'MISSING',
    prior_reconciliation_class text not null default 'MISSING',

    supervision_date date,
    controller_date date,
    lifecycle_date date,
    diagnostic_date date,
    reconciliation_date date,

    current_violations jsonb not null default '[]'::jsonb,
    stale_or_legacy_indicators jsonb not null default '[]'::jsonb,
    evidence_gaps jsonb not null default '[]'::jsonb,
    reason_codes jsonb not null default '[]'::jsonb,
    source_hashes jsonb not null default '{}'::jsonb,

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

    constraint ck_phase3724_classification check (
        classification in (
            'RECOVERY_ELIGIBLE_STALE_OR_LEGACY',
            'RECOVERY_BLOCKED_TRUE_CURRENT_VIOLATION',
            'RECOVERY_BLOCKED_INSUFFICIENT_EVIDENCE',
            'NO_ACTIVE_VIOLATION'
        )
    ),
    constraint ck_phase3724_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3724_paper_only check (paper_only = true),
    constraint ck_phase3724_no_broker_api check (broker_api_used = false),
    constraint ck_phase3724_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3724_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3724_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3724_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3724_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_true_safety_violation_forensics_v92_portfolio_date
    on public.paper_true_safety_violation_forensics_v92 (portfolio_id, forensic_date);

create table if not exists public.paper_true_safety_violation_forensics_audit_v92 (
    id bigint generated by default as identity primary key,
    forensic_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY',

    classification text not null,
    recovery_eligible boolean not null default false,
    historical_rewrite_allowed boolean not null default false,

    supervision_table text,
    supervision_state text not null default 'MISSING',
    controller_state text not null default 'MISSING',
    lifecycle_state text not null default 'MISSING',
    prior_reconciliation_class text not null default 'MISSING',

    supervision_date date,
    controller_date date,
    lifecycle_date date,
    diagnostic_date date,
    reconciliation_date date,

    current_violations jsonb not null default '[]'::jsonb,
    stale_or_legacy_indicators jsonb not null default '[]'::jsonb,
    evidence_gaps jsonb not null default '[]'::jsonb,
    reason_codes jsonb not null default '[]'::jsonb,
    source_hashes jsonb not null default '{}'::jsonb,
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

    constraint ck_phase3724_audit_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3724_audit_paper_only check (paper_only = true),
    constraint ck_phase3724_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase3724_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3724_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3724_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3724_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3724_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_true_safety_violation_forensics_audit_v92_portfolio_created
    on public.paper_true_safety_violation_forensics_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_true_safety_violation_forensics_v92 enable row level security;
alter table public.paper_true_safety_violation_forensics_audit_v92 enable row level security;

comment on table public.paper_true_safety_violation_forensics_v92 is
'GPT Quant V9.2 Phase 3.7.2.4 safety-violation evidence forensics and recovery eligibility.';

comment on table public.paper_true_safety_violation_forensics_audit_v92 is
'GPT Quant V9.2 Phase 3.7.2.4 immutable-style safety-violation forensic audit evidence.';

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.4 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.2.4 - True Safety Violation Evidence Forensics Recovery Eligibility

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
  group: phase3724-true-safety-violation-forensics
  cancel-in-progress: false

jobs:
  true-safety-violation-forensics:
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

      - name: Compile Phase 3.7.2.4
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py

      - name: Validate forensic safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY' \
            automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py

          grep -q '"historical_rewrite_allowed": False' \
            automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py

          echo "Phase 3.7.2.4 forensic safety contract: PASS"

      - name: Execute Phase 3.7.2.4
        shell: bash
        run: |
          mkdir -p artifacts/phase3724

          python automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase3724/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3724/summary.md ]; then
            cat artifacts/phase3724/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload forensic evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3724-true-safety-violation-forensics
          path: artifacts/phase3724/
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
    Fail "Phase 3.7.2.4 Python compile failed."
}

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY",
    "RECOVERY_ELIGIBLE_STALE_OR_LEGACY",
    "RECOVERY_BLOCKED_TRUE_CURRENT_VIOLATION",
    "RECOVERY_BLOCKED_INSUFFICIENT_EVIDENCE",
    "paper_true_safety_violation_forensics_v92",
    "paper_runtime_supervision_state_v92"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Required Phase 3.7.2.4 token missing: $token"
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
    Fail "Phase 3.7.2.4 SQL unexpectedly small or empty."
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Safety-forensics contract scan: PASS" -ForegroundColor Green
Write-Host "Canonical evidence-source scan: PASS" -ForegroundColor Green
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
        Write-Host "No staged Phase 3.7.2.4 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.7.2.4 safety violation evidence forensics"
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
Write-Host "  automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py"
Write-Host "  supabase/PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3724-true-safety-violation-evidence-forensics-and-recovery-eligibility.yml"
Write-Host ""
Write-Host "Possible classifications:" -ForegroundColor Cyan
Write-Host "  RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
Write-Host "  RECOVERY_BLOCKED_TRUE_CURRENT_VIOLATION"
Write-Host "  RECOVERY_BLOCKED_INSUFFICIENT_EVIDENCE"
Write-Host "  NO_ACTIVE_VIOLATION"
Write-Host ""
Write-Host "Recovery policy:" -ForegroundColor Yellow
Write-Host "  RECOVERY_ELIGIBLE_STALE_OR_LEGACY => next phase may perform controlled canonical recovery."
Write-Host "  RECOVERY_BLOCKED_TRUE_CURRENT_VIOLATION => fix the actual safety condition first."
Write-Host "  RECOVERY_BLOCKED_INSUFFICIENT_EVIDENCE => keep fail-closed and inspect evidence gaps."
Write-Host "  Historical evidence rewrite remains DISABLED."
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run supabase/PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.2.4 - True Safety Violation Evidence Forensics Recovery Eligibility."
Write-Host "  4) Use the Summary classification to choose the next recovery step."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
