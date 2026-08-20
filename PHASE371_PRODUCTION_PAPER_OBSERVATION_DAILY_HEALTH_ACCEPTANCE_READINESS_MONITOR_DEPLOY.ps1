#requires -Version 5.1
<#
PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.1 — Production Paper Observation Daily Health + Acceptance Readiness Monitor

Purpose
-------
Reduce daily manual review during the Production Paper observation window.

The monitor reads:
  - Phase 3.7.0 observation/validation state
  - Phase 3.6.9 lifecycle evidence
  - Phase 3.6.8 daily autonomous controller state

It persists one daily readiness snapshot and produces a compact GitHub summary:
  Observation Day / Target
  Lifecycle PASS Rate
  Safety Revocations
  Evidence Chain Breaks
  Maximum Drawdown
  Signal / Fill Coverage
  Acceptance Readiness
  Remaining Days

This phase NEVER enables broker/live-money capabilities.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py
  supabase/PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase371-production-paper-observation-daily-health-acceptance-readiness-monitor.yml
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

Section "GPT Quant V9.2 — Phase 3.7.1 Daily Health + Acceptance Readiness Monitor"

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
    "automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py",
    "automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py",
    "automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase371-production-paper-observation-daily-health-acceptance-readiness-monitor.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase371-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.7.1 readiness monitor"

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

CONTRACT = "PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

READINESS_NOT_READY = "NOT_READY"
READINESS_READY_WITH_LIMITED_COVERAGE = "READY_WITH_LIMITED_COVERAGE"
READINESS_READY = "READY"
READINESS_BLOCKED = "BLOCKED"
READINESS_FAIL_CLOSED = "FAIL_CLOSED"

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

def evaluate(observation: Dict[str, Any], controller: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    observation_state = str(observation.get("observation_state") or "MISSING").upper()
    observation_days = as_int(observation.get("observation_days"), 0)
    remaining_days = as_int(observation.get("remaining_minimum_days"), 0)
    pass_rate = as_float(observation.get("pass_rate"), 0.0)
    safety_revocations = as_int(observation.get("safety_revocation_days"), 0)
    chain_breaks = as_int(observation.get("evidence_chain_break_count"), 0)
    max_drawdown = as_float(observation.get("max_drawdown"), 0.0)
    signal_days = as_int(observation.get("signal_days"), 0)
    fill_days = as_int(observation.get("fill_days"), 0)
    validated = as_bool(observation.get("validated"), False)
    acceptance_candidate = as_bool(observation.get("acceptance_candidate"), False)

    controller_state = str((controller or {}).get("controller_state") or "MISSING").upper()
    controller_passed = as_bool((controller or {}).get("controller_passed"), False)

    hard_failures: List[str] = []
    notes: List[str] = []

    if observation_state == "FAIL_CLOSED":
        hard_failures.append("OBSERVATION_FAIL_CLOSED")
    if safety_revocations > 0:
        hard_failures.append("SAFETY_REVOCATION_PRESENT")
    if chain_breaks > 0:
        hard_failures.append("EVIDENCE_CHAIN_BREAK_PRESENT")
    if max_drawdown < -0.15:
        hard_failures.append("MAX_DRAWDOWN_EXCEEDED")
    if controller and (controller_state not in {"COMPLETED", "COMPLETED_WITH_OBSERVATION"} or not controller_passed):
        hard_failures.append("LATEST_CONTROLLER_NOT_PASS")

    if observation_days < 20:
        notes.append("MINIMUM_OBSERVATION_WINDOW_NOT_COMPLETE")
    if pass_rate < 0.95:
        notes.append("LIFECYCLE_PASS_RATE_BELOW_TARGET")
    if signal_days == 0:
        notes.append("NO_SIGNAL_COVERAGE_YET")
    if fill_days == 0:
        notes.append("NO_FILL_COVERAGE_YET")

    if hard_failures:
        readiness = READINESS_FAIL_CLOSED
    elif validated and acceptance_candidate and fill_days > 0:
        readiness = READINESS_READY
    elif validated and not hard_failures:
        readiness = READINESS_READY_WITH_LIMITED_COVERAGE
    else:
        readiness = READINESS_NOT_READY

    return {
        "readiness_state": readiness,
        "observation_state": observation_state,
        "observation_days": observation_days,
        "remaining_days": remaining_days,
        "pass_rate": pass_rate,
        "safety_revocations": safety_revocations,
        "chain_breaks": chain_breaks,
        "max_drawdown": max_drawdown,
        "signal_days": signal_days,
        "fill_days": fill_days,
        "validated": validated,
        "acceptance_candidate": acceptance_candidate,
        "controller_state": controller_state,
        "hard_failures": hard_failures,
        "notes": notes,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--monitor-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.monitor_date)

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

    observation = latest(
        sb,
        "paper_operations_observation_validation_v92",
        args.portfolio_id,
        "observation_date",
    )
    if observation is None:
        raise RuntimeError("Phase 3.7.0 observation state missing")

    controller = latest(
        sb,
        "paper_daily_autonomous_controller_v92",
        args.portfolio_id,
        "controller_date",
    )

    result = evaluate(observation, controller)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "monitor_date": args.monitor_date,
        "result": result,
        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_controller_evidence_sha256": (controller or {}).get("evidence_sha256"),
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
    evidence_sha = stable_hash(evidence_doc)

    payload = {
        "monitor_date": args.monitor_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "readiness_state": result["readiness_state"],
        "observation_state": result["observation_state"],
        "observation_days": result["observation_days"],
        "remaining_days": result["remaining_days"],
        "lifecycle_pass_rate": result["pass_rate"],
        "safety_revocation_days": result["safety_revocations"],
        "evidence_chain_break_count": result["chain_breaks"],
        "max_drawdown": result["max_drawdown"],
        "signal_days": result["signal_days"],
        "fill_days": result["fill_days"],
        "observation_validated": result["validated"],
        "acceptance_candidate": result["acceptance_candidate"],
        "latest_controller_state": result["controller_state"],

        "hard_failures": result["hard_failures"],
        "notes": result["notes"],

        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_controller_evidence_sha256": (controller or {}).get("evidence_sha256"),

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
        "paper_observation_acceptance_readiness_v92",
        payload,
        "portfolio_id,monitor_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_observation_acceptance_readiness_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.1")
    print()
    print("## Production Paper Observation Daily Health + Acceptance Readiness Monitor")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Monitor Date: `{args.monitor_date}`")
    print(f"- Acceptance Readiness: **{result['readiness_state']}**")
    print()
    print("## Observation Progress")
    print()
    print(f"- Observation Day: **{result['observation_days']} / 20**")
    print(f"- Remaining Days: **{result['remaining_days']}**")
    print(f"- Observation State: **{result['observation_state']}**")
    print(f"- Lifecycle PASS Rate: **{result['pass_rate'] * 100:.2f}%**")
    print(f"- Observation Validated: **{'YES' if result['validated'] else 'NO'}**")
    print(f"- Acceptance Candidate: **{'YES' if result['acceptance_candidate'] else 'NO'}**")
    print()
    print("## Daily Health")
    print()
    print(f"- Latest Controller State: **{result['controller_state']}**")
    print(f"- Safety Revocations: **{result['safety_revocations']}**")
    print(f"- Evidence Chain Breaks: **{result['chain_breaks']}**")
    print(f"- Maximum Drawdown: **{result['max_drawdown'] * 100:.4f}%**")
    print()
    print("## Coverage")
    print()
    print(f"- Signal Days: **{result['signal_days']}**")
    print(f"- Fill Days: **{result['fill_days']}**")

    if result["hard_failures"]:
        print()
        print("## Hard Failures")
        print()
        for item in result["hard_failures"]:
            print(f"- `{item}`")

    if result["notes"]:
        print()
        print("## Readiness Notes")
        print()
        for item in result["notes"]:
            print(f"- `{item}`")

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
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase371")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "daily_acceptance_readiness.json"),
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
        print(f"PHASE371_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.1 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_observation_acceptance_readiness_v92 (
    id bigint generated by default as identity primary key,
    monitor_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR',

    readiness_state text not null,
    observation_state text not null default 'UNKNOWN',
    observation_days integer not null default 0,
    remaining_days integer not null default 0,
    lifecycle_pass_rate numeric not null default 0,
    safety_revocation_days integer not null default 0,
    evidence_chain_break_count integer not null default 0,
    max_drawdown numeric not null default 0,
    signal_days integer not null default 0,
    fill_days integer not null default 0,
    observation_validated boolean not null default false,
    acceptance_candidate boolean not null default false,
    latest_controller_state text not null default 'UNKNOWN',

    hard_failures jsonb not null default '[]'::jsonb,
    notes jsonb not null default '[]'::jsonb,

    source_observation_evidence_sha256 text,
    source_controller_evidence_sha256 text,

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

    constraint ck_phase371_readiness_state check (
        readiness_state in (
            'NOT_READY',
            'READY_WITH_LIMITED_COVERAGE',
            'READY',
            'BLOCKED',
            'FAIL_CLOSED'
        )
    ),
    constraint ck_phase371_paper_only check (paper_only = true),
    constraint ck_phase371_no_broker_api check (broker_api_used = false),
    constraint ck_phase371_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase371_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase371_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase371_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase371_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_observation_acceptance_readiness_v92_portfolio_date
    on public.paper_observation_acceptance_readiness_v92 (portfolio_id, monitor_date);

create table if not exists public.paper_observation_acceptance_readiness_audit_v92 (
    id bigint generated by default as identity primary key,
    monitor_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR',

    readiness_state text not null,
    observation_state text not null default 'UNKNOWN',
    observation_days integer not null default 0,
    remaining_days integer not null default 0,
    lifecycle_pass_rate numeric not null default 0,
    safety_revocation_days integer not null default 0,
    evidence_chain_break_count integer not null default 0,
    max_drawdown numeric not null default 0,
    signal_days integer not null default 0,
    fill_days integer not null default 0,
    observation_validated boolean not null default false,
    acceptance_candidate boolean not null default false,
    latest_controller_state text not null default 'UNKNOWN',

    hard_failures jsonb not null default '[]'::jsonb,
    notes jsonb not null default '[]'::jsonb,

    source_observation_evidence_sha256 text,
    source_controller_evidence_sha256 text,
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

    constraint ck_phase371_audit_paper_only check (paper_only = true),
    constraint ck_phase371_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase371_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase371_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase371_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase371_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase371_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_observation_acceptance_readiness_audit_v92_portfolio_created
    on public.paper_observation_acceptance_readiness_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_observation_acceptance_readiness_v92 enable row level security;
alter table public.paper_observation_acceptance_readiness_audit_v92 enable row level security;

comment on table public.paper_observation_acceptance_readiness_v92 is
'GPT Quant V9.2 Phase 3.7.1 daily Production Paper observation health and acceptance readiness state.';

comment on table public.paper_observation_acceptance_readiness_audit_v92 is
'GPT Quant V9.2 Phase 3.7.1 immutable-style acceptance readiness audit evidence.';

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.7.1 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.1 - Production Paper Observation Daily Health Acceptance Readiness Monitor

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

  schedule:
    # 13:30 UTC = 21:30 Asia/Taipei, weekdays.
    # Runs after Phase 3.7.0 scheduled observation validation.
    - cron: "30 13 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase371-production-paper-acceptance-readiness
  cancel-in-progress: false

jobs:
  observation-daily-health-acceptance-readiness:
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

      - name: Compile Phase 3.7.1
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py

      - name: Validate Phase 3.7.1 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR' \
            automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py

          grep -q '"paper_operations_observation_validation_v92"' \
            automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py

          grep -q '"paper_daily_autonomous_controller_v92"' \
            automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py

          echo "Phase 3.7.1 readiness monitor contract: PASS"

      - name: Execute Phase 3.7.1
        shell: bash
        run: |
          mkdir -p artifacts/phase371

          python automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase371/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase371/summary.md ]; then
            cat artifacts/phase371/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase371-observation-acceptance-readiness
          path: artifacts/phase371/
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
    Fail "Phase 3.7.1 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR",
    "paper_operations_observation_validation_v92",
    "paper_daily_autonomous_controller_v92",
    "paper_observation_acceptance_readiness_v92",
    "NOT_READY",
    "READY_WITH_LIMITED_COVERAGE",
    "READY",
    "FAIL_CLOSED"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.7.1 required token missing: $token"
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
        Fail "Forbidden live capability detected: $forbidden"
    }
}

if ((Get-Item $sqlTarget).Length -lt 3000) {
    Fail "Phase 3.7.1 SQL unexpectedly small or empty."
}

Write-Host "Readiness monitor contract scan: PASS" -ForegroundColor Green
Write-Host "Observation source alignment scan: PASS" -ForegroundColor Green
Write-Host "Daily health summary contract scan: PASS" -ForegroundColor Green
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
        Write-Host "No staged Phase 3.7.1 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.7.1 observation daily health acceptance readiness monitor"
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
Write-Host "  automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py"
Write-Host "  supabase/PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase371-production-paper-observation-daily-health-acceptance-readiness-monitor.yml"
Write-Host ""
Write-Host "Expected Day-1 result:" -ForegroundColor Cyan
Write-Host "  Acceptance Readiness: NOT_READY"
Write-Host "  Observation Day: 1 / 20"
Write-Host "  Remaining Days: 19"
Write-Host "  Lifecycle PASS Rate: 100%"
Write-Host "  Safety Revocations: 0"
Write-Host "  Evidence Chain Breaks: 0"
Write-Host ""
Write-Host "Expected mature result:" -ForegroundColor Cyan
Write-Host "  Acceptance Readiness: READY"
Write-Host "  Observation Validated: YES"
Write-Host "  Acceptance Candidate: YES"
Write-Host ""
Write-Host "Safety:" -ForegroundColor Yellow
Write-Host "  PAPER ONLY"
Write-Host "  Broker API: NO"
Write-Host "  Broker credentials: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release: NO"
Write-Host "  Fail-closed: ENABLED"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run supabase/PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.1 - Production Paper Observation Daily Health Acceptance Readiness Monitor."
Write-Host "  4) During the 20-day observation period, review only when readiness becomes FAIL_CLOSED or a hard failure appears."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
