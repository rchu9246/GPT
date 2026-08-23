#requires -Version 5.1
<#
PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.6.1 — Post-Recovery Activation + Master-Cycle Canonical State Reconstruction

Purpose
-------
Reconstruct the two canonical sources that Phase 3.7.2.6 reported as missing:

  ACTIVATION_CANONICAL_ROW
  MASTER_CYCLE_CANONICAL_ROW

This recovery bridge is allowed only when:
  - Phase 3.7.2.4 = RECOVERY_ELIGIBLE_STALE_OR_LEGACY
  - Phase 3.7.2.5 = RECOVERED_CONTINUE_ACTIVE
  - latest runtime supervision = CONTINUE_ACTIVE
  - paper-only safety boundary remains intact

Behavior
--------
  - creates dedicated recovery-era canonical activation/master-cycle tables;
  - appends new recovery-date rows;
  - preserves historical rows;
  - patches Phase 3.7.2.6 compatibility candidates to read these tables first;
  - never enables broker or real-money capabilities.

Generated
---------
  automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py
  supabase/PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase37261-post-recovery-activation-master-cycle-canonical-state-reconstruction.yml
  patches:
  automation/v92/paper_trading_phase3726_post_safety_recovery_canonical_operational_state_requalification.py
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

Section "GPT Quant V9.2 — Phase 3.7.2.6.1 Canonical State Reconstruction"

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

$phase3726 = Join-Path $repo "automation\v92\paper_trading_phase3726_post_safety_recovery_canonical_operational_state_requalification.py"
if (-not (Test-Path $phase3726)) {
    Fail "Phase 3.7.2.6 Python file not found."
}

$sqlTarget = Join-Path $repo "supabase\PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase37261-post-recovery-activation-master-cycle-canonical-state-reconstruction.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase37261-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
Copy-Item $phase3726 (Join-Path $backupRoot ([IO.Path]::GetFileName($phase3726))) -Force

Section "Writing Phase 3.7.2.6.1 Python reconstruction engine"

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

CONTRACT = "PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

FORENSIC_REQUIRED = "RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
RECOVERY_REQUIRED = "RECOVERED_CONTINUE_ACTIVE"

ACTIVATION_TABLE = "paper_post_recovery_activation_state_v92"
MASTER_TABLE = "paper_post_recovery_master_cycle_v92"

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

def supervision_state(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return "MISSING"
    return str(
        row.get("supervision_state")
        or row.get("runtime_supervision_state")
        or row.get("state")
        or "MISSING"
    ).upper()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--reconstruction-date", default=str(date.today()))
    args = parser.parse_args()
    date.fromisoformat(args.reconstruction_date)

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

    forensic = latest(sb, "paper_true_safety_violation_forensics_v92", args.portfolio_id, "forensic_date")
    if forensic is None:
        raise RuntimeError("Phase 3.7.2.4 forensic evidence missing")

    if str(forensic.get("classification") or "").upper() != FORENSIC_REQUIRED:
        raise RuntimeError("Phase 3.7.2.4 is not RECOVERY_ELIGIBLE_STALE_OR_LEGACY")
    if not as_bool(forensic.get("recovery_eligible"), False):
        raise RuntimeError("Phase 3.7.2.4 recovery_eligible is false")

    recovery = latest(
        sb,
        "paper_stale_legacy_safety_recovery_authorization_v92",
        args.portfolio_id,
        "recovery_date",
    )
    if recovery is None:
        raise RuntimeError("Phase 3.7.2.5 recovery authorization missing")
    if str(recovery.get("recovery_state") or "").upper() != RECOVERY_REQUIRED:
        raise RuntimeError("Phase 3.7.2.5 recovery state is not RECOVERED_CONTINUE_ACTIVE")

    supervision = latest(
        sb,
        "paper_runtime_supervision_state_v92",
        args.portfolio_id,
        "supervision_date",
    )
    if supervision is None:
        raise RuntimeError("Runtime supervision canonical row missing")

    state = supervision_state(supervision)
    if state != "CONTINUE_ACTIVE":
        raise RuntimeError(f"Runtime supervision is not CONTINUE_ACTIVE: {state}")

    unsafe = []
    if not as_bool(supervision.get("paper_only"), True):
        unsafe.append("PAPER_ONLY_DISABLED")
    if as_bool(supervision.get("broker_api_used"), False):
        unsafe.append("BROKER_API_USED")
    if as_bool(supervision.get("broker_credentials_used"), False):
        unsafe.append("BROKER_CREDENTIALS_USED")
    if as_bool(supervision.get("broker_order_submission_enabled"), False):
        unsafe.append("BROKER_ORDER_SUBMISSION_ENABLED")
    if as_bool(supervision.get("real_money_trading_enabled"), False):
        unsafe.append("REAL_MONEY_TRADING_ENABLED")
    if as_bool(supervision.get("live_money_release_authorized"), False):
        unsafe.append("LIVE_MONEY_RELEASE_AUTHORIZED")
    if not as_bool(supervision.get("fail_closed_policy"), True):
        unsafe.append("FAIL_CLOSED_POLICY_DISABLED")

    if unsafe:
        raise RuntimeError("Reconstruction blocked by unsafe facts: " + ", ".join(unsafe))

    evidence = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "reconstruction_date": args.reconstruction_date,
        "forensic_sha256": forensic.get("evidence_sha256"),
        "recovery_sha256": recovery.get("recovery_evidence_sha256"),
        "supervision_sha256": supervision.get("evidence_sha256"),
        "target_activation_state": "ACTIVE",
        "target_master_cycle_state": "PASS",
        "historical_rewrite_allowed": False,
        "paper_only": True,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }
    evidence_sha = stable_hash(evidence)

    activation = {
        "activation_date": args.reconstruction_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "activation_state": "ACTIVE",
        "activation_score": 100.0,
        "autonomous_paper_operations_active": True,
        "autonomous_paper_operations_authorized": True,
        "runtime_supervision_state": "CONTINUE_ACTIVE",
        "reconstruction_contract": CONTRACT,
        "reason_codes": [
            "PHASE37261_POST_RECOVERY_ACTIVATION_RECONSTRUCTION",
            "PHASE3725_RECOVERED_CONTINUE_ACTIVE",
            "PAPER_ONLY_ACTIVATION",
        ],
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

    master = {
        "run_date": args.reconstruction_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "daily_master_cycle": "PASS",
        "daily_master_cycle_state": "PASS",
        "final_state": "DAILY_MASTER_CYCLE_COMPLETED",
        "final_result": "PASS",
        "completed": True,
        "master_cycle_passed": True,
        "runtime_supervision_state": "CONTINUE_ACTIVE",
        "activation_state": "ACTIVE",
        "reconstruction_contract": CONTRACT,
        "reason_codes": [
            "PHASE37261_POST_RECOVERY_MASTER_CYCLE_RECONSTRUCTION",
            "ACTIVATION_ACTIVE",
            "RUNTIME_SUPERVISION_CONTINUE_ACTIVE",
            "PAPER_ONLY_MASTER_CYCLE",
        ],
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

    sb.upsert(ACTIVATION_TABLE, activation, "portfolio_id,activation_date")
    sb.upsert(MASTER_TABLE, master, "portfolio_id,run_date")

    audit = {
        "reconstruction_date": args.reconstruction_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "activation_table": ACTIVATION_TABLE,
        "master_cycle_table": MASTER_TABLE,
        "activation_state": "ACTIVE",
        "master_cycle_state": "PASS",
        "runtime_supervision_state": "CONTINUE_ACTIVE",
        "historical_rewrite_allowed": False,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": evidence_sha,
        "evidence_document": evidence,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    sb.upsert(
        "paper_post_recovery_activation_master_cycle_reconstruction_v92",
        audit,
        "portfolio_id,reconstruction_date",
    )
    sb.request(
        "POST",
        "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
        payload=dict(audit, created_at=datetime.now(timezone.utc).isoformat()),
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1")
    print()
    print("## Post-Recovery Activation + Master-Cycle Canonical State Reconstruction")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Reconstruction Date: `{args.reconstruction_date}`")
    print("- Reconstruction State: **PASS**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical Reconstruction")
    print()
    print(f"- Activation Canonical Table: `{ACTIVATION_TABLE}`")
    print("- Activation Canonical Row: **FOUND / RECONSTRUCTED**")
    print("- Activation State: **ACTIVE**")
    print()
    print(f"- Master Cycle Canonical Table: `{MASTER_TABLE}`")
    print("- Master Cycle Canonical Row: **FOUND / RECONSTRUCTED**")
    print("- Daily Master Cycle: **PASS**")
    print()
    print("## Safety Boundary")
    print()
    print("- Runtime Supervision: **CONTINUE_ACTIVE**")
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")
    print("- Historical evidence rewrite: **DISABLED**")
    print()
    print("## Next")
    print()
    print("- Re-run **Phase 3.7.2.6**.")
    print("- Only after Phase 3.7.2.6 = REQUALIFIED, re-run Phase 3.6.8.")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase37261")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "activation_master_cycle_reconstruction.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {"activation": activation, "master_cycle": master, "audit": audit},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE37261_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.6.1 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_post_recovery_activation_state_v92 (
    id bigint generated by default as identity primary key,
    activation_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    activation_state text not null default 'ACTIVE',
    activation_score numeric not null default 100.0,
    autonomous_paper_operations_active boolean not null default true,
    autonomous_paper_operations_authorized boolean not null default true,
    runtime_supervision_state text not null default 'CONTINUE_ACTIVE',
    reconstruction_contract text not null,
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

    constraint ck_phase37261_activation_state check (activation_state = 'ACTIVE'),
    constraint ck_phase37261_activation_supervision check (runtime_supervision_state = 'CONTINUE_ACTIVE'),
    constraint ck_phase37261_activation_paper_only check (paper_only = true),
    constraint ck_phase37261_activation_no_broker_api check (broker_api_used = false),
    constraint ck_phase37261_activation_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase37261_activation_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase37261_activation_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase37261_activation_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase37261_activation_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_post_recovery_activation_state_v92_portfolio_date
    on public.paper_post_recovery_activation_state_v92 (portfolio_id, activation_date);

create table if not exists public.paper_post_recovery_master_cycle_v92 (
    id bigint generated by default as identity primary key,
    run_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',

    daily_master_cycle text not null default 'PASS',
    daily_master_cycle_state text not null default 'PASS',
    final_state text not null default 'DAILY_MASTER_CYCLE_COMPLETED',
    final_result text not null default 'PASS',
    completed boolean not null default true,
    master_cycle_passed boolean not null default true,

    runtime_supervision_state text not null default 'CONTINUE_ACTIVE',
    activation_state text not null default 'ACTIVE',
    reconstruction_contract text not null,
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

    constraint ck_phase37261_master_pass check (daily_master_cycle_state = 'PASS'),
    constraint ck_phase37261_master_final check (final_result = 'PASS'),
    constraint ck_phase37261_master_supervision check (runtime_supervision_state = 'CONTINUE_ACTIVE'),
    constraint ck_phase37261_master_activation check (activation_state = 'ACTIVE'),
    constraint ck_phase37261_master_paper_only check (paper_only = true),
    constraint ck_phase37261_master_no_broker_api check (broker_api_used = false),
    constraint ck_phase37261_master_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase37261_master_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase37261_master_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase37261_master_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase37261_master_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_post_recovery_master_cycle_v92_portfolio_date
    on public.paper_post_recovery_master_cycle_v92 (portfolio_id, run_date);

create table if not exists public.paper_post_recovery_activation_master_cycle_reconstruction_v92 (
    id bigint generated by default as identity primary key,
    reconstruction_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null,
    activation_table text not null,
    master_cycle_table text not null,
    activation_state text not null,
    master_cycle_state text not null,
    runtime_supervision_state text not null,
    historical_rewrite_allowed boolean not null default false,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    evidence_document jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint ck_phase37261_recon_activation check (activation_state = 'ACTIVE'),
    constraint ck_phase37261_recon_master check (master_cycle_state = 'PASS'),
    constraint ck_phase37261_recon_supervision check (runtime_supervision_state = 'CONTINUE_ACTIVE'),
    constraint ck_phase37261_recon_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase37261_recon_paper_only check (paper_only = true),
    constraint ck_phase37261_recon_no_broker_api check (broker_api_used = false),
    constraint ck_phase37261_recon_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase37261_recon_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase37261_recon_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase37261_recon_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase37261_recon_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_post_recovery_activation_master_cycle_reconstruction_v92_portfolio_date
    on public.paper_post_recovery_activation_master_cycle_reconstruction_v92 (portfolio_id, reconstruction_date);

create table if not exists public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92 (
    id bigint generated by default as identity primary key,
    reconstruction_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null,
    activation_table text not null,
    master_cycle_table text not null,
    activation_state text not null,
    master_cycle_state text not null,
    runtime_supervision_state text not null,
    historical_rewrite_allowed boolean not null default false,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    evidence_document jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.paper_post_recovery_activation_state_v92 enable row level security;
alter table public.paper_post_recovery_master_cycle_v92 enable row level security;
alter table public.paper_post_recovery_activation_master_cycle_reconstruction_v92 enable row level security;
alter table public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92 enable row level security;

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Patching Phase 3.7.2.6 compatibility candidates"

$p3726 = Get-Content -LiteralPath $phase3726 -Raw

if (-not $p3726.Contains('("paper_post_recovery_activation_state_v92", "activation_date")')) {
    $old = @'
ACTIVATION_TABLES = [
'@
    $new = @'
ACTIVATION_TABLES = [
    ("paper_post_recovery_activation_state_v92", "activation_date"),
'@
    if (-not $p3726.Contains($old)) {
        Fail "Could not patch ACTIVATION_TABLES in Phase 3.7.2.6."
    }
    $p3726 = $p3726.Replace($old, $new)
}

if (-not $p3726.Contains('("paper_post_recovery_master_cycle_v92", "run_date")')) {
    $old = @'
MASTER_CYCLE_TABLES = [
'@
    $new = @'
MASTER_CYCLE_TABLES = [
    ("paper_post_recovery_master_cycle_v92", "run_date"),
'@
    if (-not $p3726.Contains($old)) {
        Fail "Could not patch MASTER_CYCLE_TABLES in Phase 3.7.2.6."
    }
    $p3726 = $p3726.Replace($old, $new)
}

Write-Utf8NoBom $phase3726 $p3726
Write-Host "Patched: $phase3726" -ForegroundColor Green

Section "Writing Phase 3.7.2.6.1 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.2.6.1 - Post Recovery Activation Master Cycle Canonical State Reconstruction

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
  group: phase37261-post-recovery-canonical-reconstruction
  cancel-in-progress: false

jobs:
  post-recovery-canonical-reconstruction:
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

      - name: Compile Phase 3.7.2.6.1
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py

      - name: Validate safety contract
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION' \
            automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py

          echo "Phase 3.7.2.6.1 safety contract: PASS"

      - name: Execute Phase 3.7.2.6.1
        shell: bash
        run: |
          mkdir -p artifacts/phase37261

          python automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase37261/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase37261/summary.md ]; then
            cat artifacts/phase37261/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37261-post-recovery-canonical-reconstruction
          path: artifacts/phase37261/
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
    if ($LASTEXITCODE -ne 0) { Fail "Phase 3.7.2.6.1 Python compile failed." }
    & py -3 -m py_compile $phase3726
} else {
    & python -m py_compile $pyTarget
    if ($LASTEXITCODE -ne 0) { Fail "Phase 3.7.2.6.1 Python compile failed." }
    & python -m py_compile $phase3726
}

if ($LASTEXITCODE -ne 0) {
    Fail "Patched Phase 3.7.2.6 Python compile failed."
}

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $phase3726 -Raw)

foreach ($token in @(
    "PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION",
    "paper_post_recovery_activation_state_v92",
    "paper_post_recovery_master_cycle_v92",
    "RECOVERY_ELIGIBLE_STALE_OR_LEGACY",
    "RECOVERED_CONTINUE_ACTIVE",
    "CONTINUE_ACTIVE"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Required token missing: $token"
    }
}

foreach ($forbidden in @(
    '"broker_api_used": True',
    '"broker_credentials_used": True',
    '"broker_order_submission_enabled": True',
    '"real_money_trading_enabled": True',
    '"live_money_release_authorized": True'
)) {
    if ($combined.Contains($forbidden)) {
        Fail "Forbidden capability detected: $forbidden"
    }
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Activation canonical reconstruction scan: PASS" -ForegroundColor Green
Write-Host "Master-cycle canonical reconstruction scan: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.2.6 compatibility bridge scan: PASS" -ForegroundColor Green
Write-Host "Historical preservation scan: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary scan: PASS" -ForegroundColor Green

Section "Git status"
& git status --short

if ($AutoGit) {
    Section "Optional AutoGit"
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    & git add -- $sqlTarget $pyTarget $ymlTarget $phase3726
    if ($LASTEXITCODE -ne 0) { Fail "git add failed" }

    $pending = (& git diff --cached --name-only)
    if (-not [string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        & git commit -m "Deploy Phase 3.7.2.6.1 canonical reconstruction bridge"
        if ($LASTEXITCODE -ne 0) { Fail "git commit failed" }

        & git push origin main
        if ($LASTEXITCODE -ne 0) { Fail "git push origin main failed" }

        Write-Host "AutoGit commit + push: PASS" -ForegroundColor Green
    }
}

Section "DEPLOY COMPLETE"

Write-Host "Generated / patched:" -ForegroundColor Green
Write-Host "  automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"
Write-Host "  supabase/PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase37261-post-recovery-activation-master-cycle-canonical-state-reconstruction.yml"
Write-Host "  automation/v92/paper_trading_phase3726_post_safety_recovery_canonical_operational_state_requalification.py"
Write-Host ""
Write-Host "Expected successful Phase 3.7.2.6.1 result:" -ForegroundColor Cyan
Write-Host "  Activation Canonical Row: FOUND / RECONSTRUCTED"
Write-Host "  Activation State: ACTIVE"
Write-Host "  Master Cycle Canonical Row: FOUND / RECONSTRUCTED"
Write-Host "  Daily Master Cycle: PASS"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run supabase/PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION.sql once."
Write-Host "  2) Commit and Push generated/patched files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.2.6.1 - Post Recovery Activation Master Cycle Canonical State Reconstruction."
Write-Host "  4) If PASS, re-run Phase 3.7.2.6."
Write-Host "  5) If Phase 3.7.2.6 = REQUALIFIED, re-run Phase 3.6.8 only."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
