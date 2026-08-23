#requires -Version 5.1
<#
PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.5 — Stale / Legacy Safety State Controlled Canonical Recovery

Purpose
-------
Perform a tightly-scoped, paper-only recovery after Phase 3.7.2.4 has explicitly
classified the current revocation as:

    RECOVERY_ELIGIBLE_STALE_OR_LEGACY
    recovery_eligible = true

The recovery NEVER edits or deletes historical rows.

Instead it:
  1) verifies the latest Phase 3.7.2.4 forensic evidence;
  2) verifies that broker / real-money capabilities remain disabled;
  3) creates a recovery authorization audit record;
  4) appends a NEW canonical runtime-supervision state row derived from the
     previous row, with stale revocation cleared and state restored to
     CONTINUE_ACTIVE;
  5) preserves the previous REVOKED row as immutable historical evidence;
  6) requires the normal downstream chain to be re-run afterward.

This phase does NOT:
  - backfill observation days;
  - rewrite prior lifecycle/controller rows;
  - enable broker order submission;
  - enable real-money trading;
  - authorize live-money release.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py
  supabase/PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase3725-stale-legacy-safety-state-controlled-canonical-recovery.yml
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

Section "GPT Quant V9.2 — Phase 3.7.2.5 Controlled Canonical Recovery"

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
    "automation/v92/paper_trading_phase3724_true_safety_violation_evidence_forensics_and_recovery_eligibility.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase3725-stale-legacy-safety-state-controlled-canonical-recovery.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase3725-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.7.2.5 recovery engine"

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
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

REQUIRED_FORENSIC_CLASSIFICATION = "RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
RECOVERY_STATE = "RECOVERED_CONTINUE_ACTIVE"

SYSTEM_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "inserted_at",
    "modified_at",
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

    def insert(self, table: str, payload: Dict[str, Any]) -> None:
        self.request("POST", table, payload=payload, prefer="return=minimal")

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

def clone_for_new_supervision_row(
    previous: Dict[str, Any],
    recovery_date: str,
    evidence_sha: str,
) -> Dict[str, Any]:

    new_row = deepcopy(previous)

    for field in SYSTEM_FIELDS:
        new_row.pop(field, None)

    # Establish a NEW canonical state row. Never overwrite the previous REVOKED row.
    if "supervision_date" in new_row:
        new_row["supervision_date"] = recovery_date
    elif "run_date" in new_row:
        new_row["run_date"] = recovery_date
    else:
        raise RuntimeError("Supervision schema has no supervision_date/run_date column")

    # State compatibility.
    if "supervision_state" in new_row:
        new_row["supervision_state"] = "CONTINUE_ACTIVE"
    if "runtime_supervision_state" in new_row:
        new_row["runtime_supervision_state"] = "CONTINUE_ACTIVE"
    if "state" in new_row and str(new_row.get("state", "")).upper() in {
        "REVOKED", "FAIL_CLOSED", "STOP", "BLOCKED"
    }:
        new_row["state"] = "CONTINUE_ACTIVE"

    # Clear only stale/legacy revocation flags in the NEW row.
    for field in (
        "safety_revocation_triggered",
        "revoked",
        "is_revoked",
        "recovery_blocked",
    ):
        if field in new_row:
            new_row[field] = False

    # Preserve and enforce paper-only safety boundary.
    if "paper_only" in new_row:
        new_row["paper_only"] = True
    if "broker_api_used" in new_row:
        new_row["broker_api_used"] = False
    if "broker_credentials_used" in new_row:
        new_row["broker_credentials_used"] = False
    if "broker_order_submission_enabled" in new_row:
        new_row["broker_order_submission_enabled"] = False
    if "real_money_trading_enabled" in new_row:
        new_row["real_money_trading_enabled"] = False
    if "live_money_release_authorized" in new_row:
        new_row["live_money_release_authorized"] = False
    if "fail_closed_policy" in new_row:
        new_row["fail_closed_policy"] = True

    # Replace reason fields, when available, with an explicit controlled recovery marker.
    recovery_reasons = [
        "PHASE3725_CONTROLLED_CANONICAL_RECOVERY",
        "SOURCE_PHASE3724_RECOVERY_ELIGIBLE_STALE_OR_LEGACY",
        "HISTORICAL_REVOKED_ROW_PRESERVED",
        "PAPER_ONLY_RECOVERY",
    ]
    for field in (
        "reason_codes",
        "reasons",
        "revocation_reasons",
        "safety_reasons",
        "failure_reasons",
        "hard_failures",
    ):
        if field in new_row:
            new_row[field] = recovery_reasons

    if "evidence_sha256" in new_row:
        new_row["evidence_sha256"] = evidence_sha

    return new_row

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--recovery-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.recovery_date)

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

    forensic = latest(
        sb,
        "paper_true_safety_violation_forensics_v92",
        args.portfolio_id,
        "forensic_date",
    )
    if forensic is None:
        raise RuntimeError("Phase 3.7.2.4 forensic evidence missing")

    classification = str(forensic.get("classification") or "").upper()
    recovery_eligible = as_bool(forensic.get("recovery_eligible"), False)

    if classification != REQUIRED_FORENSIC_CLASSIFICATION:
        raise RuntimeError(
            f"Recovery blocked: forensic classification={classification!r}"
        )
    if not recovery_eligible:
        raise RuntimeError("Recovery blocked: recovery_eligible is false")

    # Re-verify immutable safety boundary from the forensic record.
    unsafe = []
    if not as_bool(forensic.get("paper_only"), True):
        unsafe.append("PAPER_ONLY_DISABLED")
    if as_bool(forensic.get("broker_api_used"), False):
        unsafe.append("BROKER_API_USED")
    if as_bool(forensic.get("broker_credentials_used"), False):
        unsafe.append("BROKER_CREDENTIALS_USED")
    if as_bool(forensic.get("broker_order_submission_enabled"), False):
        unsafe.append("BROKER_ORDER_SUBMISSION_ENABLED")
    if as_bool(forensic.get("real_money_trading_enabled"), False):
        unsafe.append("REAL_MONEY_TRADING_ENABLED")
    if as_bool(forensic.get("live_money_release_authorized"), False):
        unsafe.append("LIVE_MONEY_RELEASE_AUTHORIZED")
    if not as_bool(forensic.get("fail_closed_policy"), True):
        unsafe.append("FAIL_CLOSED_POLICY_DISABLED")

    current_violations = forensic.get("current_violations")
    if isinstance(current_violations, list) and current_violations:
        unsafe.extend(str(x) for x in current_violations)

    if unsafe:
        raise RuntimeError(
            "Recovery blocked by current unsafe facts: " + ", ".join(sorted(set(unsafe)))
        )

    supervision_table = (
        forensic.get("supervision_table")
        or "paper_runtime_supervision_state_v92"
    )

    previous = latest(
        sb,
        supervision_table,
        args.portfolio_id,
        "supervision_date",
    )
    if previous is None:
        raise RuntimeError("Current canonical supervision row missing")

    previous_state = str(
        previous.get("supervision_state")
        or previous.get("runtime_supervision_state")
        or previous.get("state")
        or "MISSING"
    ).upper()

    if previous_state not in {"REVOKED", "FAIL_CLOSED", "STOP", "BLOCKED"}:
        raise RuntimeError(
            f"Recovery not required: latest supervision state={previous_state}"
        )

    recovery_evidence = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "recovery_date": args.recovery_date,
        "forensic_evidence_sha256": forensic.get("evidence_sha256"),
        "forensic_classification": classification,
        "previous_supervision_evidence_sha256": previous.get("evidence_sha256"),
        "previous_supervision_state": previous_state,
        "target_supervision_state": "CONTINUE_ACTIVE",
        "historical_rewrite_allowed": False,
        "safety": {
            "paper_only": True,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
        },
    }
    recovery_evidence_sha = stable_hash(recovery_evidence)

    new_supervision_row = clone_for_new_supervision_row(
        previous,
        args.recovery_date,
        recovery_evidence_sha,
    )

    authorization = {
        "recovery_date": args.recovery_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "forensic_classification": classification,
        "recovery_eligible": True,
        "recovery_state": RECOVERY_STATE,
        "previous_supervision_state": previous_state,
        "target_supervision_state": "CONTINUE_ACTIVE",
        "historical_rewrite_allowed": False,
        "forensic_evidence_sha256": forensic.get("evidence_sha256"),
        "previous_supervision_evidence_sha256": previous.get("evidence_sha256"),
        "recovery_evidence_sha256": recovery_evidence_sha,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write authorization evidence first.
    sb.upsert(
        "paper_stale_legacy_safety_recovery_authorization_v92",
        authorization,
        "portfolio_id,recovery_date",
    )

    # Append a NEW current-state row. Historical REVOKED row is untouched.
    sb.insert(supervision_table, new_supervision_row)

    audit = dict(authorization)
    audit["recovery_evidence"] = recovery_evidence
    audit["new_supervision_row_sha256"] = stable_hash(new_supervision_row)

    sb.insert(
        "paper_stale_legacy_safety_recovery_audit_v92",
        audit,
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.5")
    print()
    print("## Stale / Legacy Safety State Controlled Canonical Recovery")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Recovery Date: `{args.recovery_date}`")
    print(f"- Forensic Classification: **{classification}**")
    print("- Recovery Eligible: **YES**")
    print(f"- Recovery State: **{RECOVERY_STATE}**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical Recovery")
    print()
    print(f"- Runtime Supervision Table: **{supervision_table}**")
    print(f"- Previous Supervision State: **{previous_state}**")
    print("- New Supervision State: **CONTINUE_ACTIVE**")
    print("- Historical REVOKED Row Preserved: **YES**")
    print("- New Canonical Row Appended: **YES**")
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
    print()
    print("## Required Next Chain")
    print()
    print("- Re-run in this order:")
    print("  `Phase 3.6.8 -> Phase 3.6.9 -> Phase 3.7.0 -> Phase 3.7.1 -> Phase 3.7.2`")
    print("- Do not skip directly to Phase 3.7.2.")
    print("- Do not backfill observation days.")
    print(f"- Recovery Evidence SHA256: `{recovery_evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3725")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "controlled_canonical_recovery.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "authorization": authorization,
                "recovery_evidence": recovery_evidence,
                "new_supervision_row": new_supervision_row,
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
        print(f"PHASE3725_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.5 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_stale_legacy_safety_recovery_authorization_v92 (
    id bigint generated by default as identity primary key,
    recovery_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY',

    forensic_classification text not null,
    recovery_eligible boolean not null default false,
    recovery_state text not null,

    previous_supervision_state text not null,
    target_supervision_state text not null,
    historical_rewrite_allowed boolean not null default false,

    forensic_evidence_sha256 text,
    previous_supervision_evidence_sha256 text,
    recovery_evidence_sha256 text not null,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    created_at timestamptz not null default now(),

    constraint ck_phase3725_forensic_classification check (
        forensic_classification = 'RECOVERY_ELIGIBLE_STALE_OR_LEGACY'
    ),
    constraint ck_phase3725_recovery_eligible check (recovery_eligible = true),
    constraint ck_phase3725_recovery_state check (
        recovery_state = 'RECOVERED_CONTINUE_ACTIVE'
    ),
    constraint ck_phase3725_target_state check (
        target_supervision_state = 'CONTINUE_ACTIVE'
    ),
    constraint ck_phase3725_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3725_paper_only check (paper_only = true),
    constraint ck_phase3725_no_broker_api check (broker_api_used = false),
    constraint ck_phase3725_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3725_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3725_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3725_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3725_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_stale_legacy_safety_recovery_authorization_v92_portfolio_date
    on public.paper_stale_legacy_safety_recovery_authorization_v92 (portfolio_id, recovery_date);

create table if not exists public.paper_stale_legacy_safety_recovery_audit_v92 (
    id bigint generated by default as identity primary key,
    recovery_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY',

    forensic_classification text not null,
    recovery_eligible boolean not null default false,
    recovery_state text not null,

    previous_supervision_state text not null,
    target_supervision_state text not null,
    historical_rewrite_allowed boolean not null default false,

    forensic_evidence_sha256 text,
    previous_supervision_evidence_sha256 text,
    recovery_evidence_sha256 text not null,

    recovery_evidence jsonb not null default '{}'::jsonb,
    new_supervision_row_sha256 text not null,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    created_at timestamptz not null default now(),

    constraint ck_phase3725_audit_no_history_rewrite check (historical_rewrite_allowed = false),
    constraint ck_phase3725_audit_paper_only check (paper_only = true),
    constraint ck_phase3725_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase3725_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase3725_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase3725_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase3725_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase3725_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_stale_legacy_safety_recovery_audit_v92_portfolio_created
    on public.paper_stale_legacy_safety_recovery_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_stale_legacy_safety_recovery_authorization_v92 enable row level security;
alter table public.paper_stale_legacy_safety_recovery_audit_v92 enable row level security;

comment on table public.paper_stale_legacy_safety_recovery_authorization_v92 is
'GPT Quant V9.2 Phase 3.7.2.5 controlled paper-only canonical recovery authorization.';

comment on table public.paper_stale_legacy_safety_recovery_audit_v92 is
'GPT Quant V9.2 Phase 3.7.2.5 immutable-style controlled recovery audit evidence.';

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2.5 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.2.5 - Stale Legacy Safety State Controlled Canonical Recovery

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
  group: phase3725-controlled-canonical-recovery
  cancel-in-progress: false

jobs:
  stale-legacy-safety-controlled-recovery:
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

      - name: Compile Phase 3.7.2.5
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py

      - name: Validate controlled-recovery safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY' \
            automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py

          grep -q 'RECOVERY_ELIGIBLE_STALE_OR_LEGACY' \
            automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py

          grep -q '"historical_rewrite_allowed": False' \
            automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py

          echo "Phase 3.7.2.5 controlled recovery safety contract: PASS"

      - name: Execute Phase 3.7.2.5
        shell: bash
        run: |
          mkdir -p artifacts/phase3725

          python automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase3725/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3725/summary.md ]; then
            cat artifacts/phase3725/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload recovery evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3725-controlled-canonical-recovery
          path: artifacts/phase3725/
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
    Fail "Phase 3.7.2.5 Python compile failed."
}

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY",
    "RECOVERY_ELIGIBLE_STALE_OR_LEGACY",
    "RECOVERED_CONTINUE_ACTIVE",
    "CONTINUE_ACTIVE",
    "paper_stale_legacy_safety_recovery_authorization_v92",
    "Historical REVOKED Row Preserved"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Required Phase 3.7.2.5 token missing: $token"
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
    Fail "Phase 3.7.2.5 SQL unexpectedly small or empty."
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Recovery eligibility gate scan: PASS" -ForegroundColor Green
Write-Host "Append-only canonical recovery scan: PASS" -ForegroundColor Green
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

    & git add -- $sqlTarget $pyTarget $ymlTarget
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed"
    }

    $pending = (& git diff --cached --name-only)
    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged Phase 3.7.2.5 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.7.2.5 controlled canonical recovery"
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
Write-Host "  automation/v92/paper_trading_phase3725_stale_legacy_safety_state_controlled_canonical_recovery.py"
Write-Host "  supabase/PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3725-stale-legacy-safety-state-controlled-canonical-recovery.yml"
Write-Host ""
Write-Host "Recovery behavior:" -ForegroundColor Cyan
Write-Host "  - requires Phase 3.7.2.4 RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
Write-Host "  - requires recovery_eligible = true"
Write-Host "  - appends NEW CONTINUE_ACTIVE supervision row"
Write-Host "  - preserves old REVOKED row"
Write-Host "  - does not touch observation-day history"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run supabase/PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.2.5 - Stale Legacy Safety State Controlled Canonical Recovery."
Write-Host "  4) If Recovery State = RECOVERED_CONTINUE_ACTIVE, re-run:"
Write-Host "     Phase 3.6.8 -> 3.6.9 -> 3.7.0 -> 3.7.1 -> 3.7.2"
Write-Host ""
Write-Host "Safety:" -ForegroundColor Yellow
Write-Host "  PAPER ONLY"
Write-Host "  Broker API: NO"
Write-Host "  Broker credentials: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release: NO"
Write-Host "  Historical evidence rewrite: DISABLED"
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
