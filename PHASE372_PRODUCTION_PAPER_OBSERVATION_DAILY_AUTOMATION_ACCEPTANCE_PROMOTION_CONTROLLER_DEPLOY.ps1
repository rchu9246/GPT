#requires -Version 5.1
<#
PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2 — Production Paper Observation Daily Automation + Acceptance Promotion Controller

Purpose
-------
Automate the acceptance-promotion decision at the end of each Production Paper
observation day without bypassing the Phase 3.7.0 / 3.7.1 evidence gates.

The controller:
  1) reads the latest Phase 3.7.1 acceptance-readiness snapshot;
  2) verifies the latest Phase 3.7.0 observation state;
  3) verifies the latest Phase 3.6.9 lifecycle evidence;
  4) keeps the system in OBSERVATION while readiness is NOT_READY;
  5) promotes only to PAPER_ACCEPTANCE_ELIGIBLE when readiness becomes READY;
  6) never authorizes broker/live-money execution;
  7) persists canonical state + immutable-style audit evidence;
  8) fail-closes on contradictory or unsafe canonical states.

Important
---------
PAPER_ACCEPTANCE_ELIGIBLE means "eligible for the later Paper Production
Acceptance Gate". It does NOT mean real-money/live-broker authorization.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py
  supabase/PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase372-production-paper-observation-daily-automation-acceptance-promotion-controller.yml
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

Section "GPT Quant V9.2 — Phase 3.7.2 Daily Automation + Acceptance Promotion Controller"

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
    "automation/v92/paper_trading_phase371_production_paper_observation_daily_health_acceptance_readiness_monitor.py",
    "automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py",
    "automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase372-production-paper-observation-daily-automation-acceptance-promotion-controller.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase372-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.7.2 acceptance promotion controller"

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

CONTRACT = "PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

STATE_OBSERVATION_CONTINUES = "OBSERVATION_CONTINUES"
STATE_ACCEPTANCE_ELIGIBLE = "PAPER_ACCEPTANCE_ELIGIBLE"
STATE_LIMITED_COVERAGE = "PAPER_ACCEPTANCE_LIMITED_COVERAGE"
STATE_HELD = "PROMOTION_HELD"
STATE_FAIL_CLOSED = "FAIL_CLOSED"

SAFE_READINESS = {
    "NOT_READY",
    "READY",
    "READY_WITH_LIMITED_COVERAGE",
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

def latest(
    sb: Supabase,
    table: str,
    portfolio_id: str,
    order_column: str,
) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def evaluate(
    readiness: Dict[str, Any],
    observation: Dict[str, Any],
    lifecycle: Dict[str, Any],
) -> Dict[str, Any]:
    readiness_state = str(readiness.get("readiness_state") or "MISSING").upper()
    observation_state = str(observation.get("observation_state") or "MISSING").upper()
    lifecycle_state = str(lifecycle.get("lifecycle_state") or "MISSING").upper()

    observation_days = as_int(readiness.get("observation_days"), 0)
    remaining_days = as_int(readiness.get("remaining_days"), 0)
    pass_rate = as_float(readiness.get("lifecycle_pass_rate"), 0.0)
    safety_revocations = as_int(readiness.get("safety_revocation_days"), 0)
    chain_breaks = as_int(readiness.get("evidence_chain_break_count"), 0)
    max_drawdown = as_float(readiness.get("max_drawdown"), 0.0)
    signal_days = as_int(readiness.get("signal_days"), 0)
    fill_days = as_int(readiness.get("fill_days"), 0)

    observation_validated = as_bool(readiness.get("observation_validated"), False)
    acceptance_candidate = as_bool(readiness.get("acceptance_candidate"), False)
    lifecycle_passed = as_bool(lifecycle.get("lifecycle_passed"), False)

    reasons: List[str] = []
    hard_failures: List[str] = []

    if readiness_state not in SAFE_READINESS:
        hard_failures.append("READINESS_UNSAFE_OR_UNKNOWN")
    if observation_state == "FAIL_CLOSED":
        hard_failures.append("OBSERVATION_FAIL_CLOSED")
    if lifecycle_state == "FAIL_CLOSED" or not lifecycle_passed:
        hard_failures.append("LATEST_LIFECYCLE_NOT_PASS")
    if safety_revocations > 0:
        hard_failures.append("SAFETY_REVOCATION_PRESENT")
    if chain_breaks > 0:
        hard_failures.append("EVIDENCE_CHAIN_BREAK_PRESENT")
    if max_drawdown < -0.15:
        hard_failures.append("MAX_DRAWDOWN_EXCEEDED")

    if hard_failures:
        promotion_state = STATE_FAIL_CLOSED
        promotion_authorized = False
        reasons.extend(hard_failures)

    elif readiness_state == "READY":
        if (
            observation_days >= 20
            and remaining_days == 0
            and pass_rate >= 0.95
            and observation_validated
            and acceptance_candidate
        ):
            promotion_state = STATE_ACCEPTANCE_ELIGIBLE
            promotion_authorized = True
            reasons.append("PAPER_ACCEPTANCE_ELIGIBILITY_PROMOTED")
        else:
            promotion_state = STATE_HELD
            promotion_authorized = False
            reasons.append("READY_STATE_CANONICAL_CONTRACT_INCONSISTENT")

    elif readiness_state == "READY_WITH_LIMITED_COVERAGE":
        if observation_days >= 20 and observation_validated:
            promotion_state = STATE_LIMITED_COVERAGE
            promotion_authorized = False
            reasons.append("VALIDATED_BUT_TRADE_COVERAGE_LIMITED")
        else:
            promotion_state = STATE_HELD
            promotion_authorized = False
            reasons.append("LIMITED_COVERAGE_STATE_NOT_MATURE")

    else:
        promotion_state = STATE_OBSERVATION_CONTINUES
        promotion_authorized = False
        reasons.append("OBSERVATION_WINDOW_CONTINUES")

    return {
        "promotion_state": promotion_state,
        "promotion_authorized": promotion_authorized,
        "readiness_state": readiness_state,
        "observation_state": observation_state,
        "lifecycle_state": lifecycle_state,
        "observation_days": observation_days,
        "remaining_days": remaining_days,
        "pass_rate": pass_rate,
        "safety_revocations": safety_revocations,
        "chain_breaks": chain_breaks,
        "max_drawdown": max_drawdown,
        "signal_days": signal_days,
        "fill_days": fill_days,
        "observation_validated": observation_validated,
        "acceptance_candidate": acceptance_candidate,
        "reasons": reasons,
        "hard_failures": hard_failures,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--promotion-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.promotion_date)

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

    readiness = latest(
        sb,
        "paper_observation_acceptance_readiness_v92",
        args.portfolio_id,
        "monitor_date",
    )
    if readiness is None:
        raise RuntimeError("Phase 3.7.1 readiness state missing")

    observation = latest(
        sb,
        "paper_operations_observation_validation_v92",
        args.portfolio_id,
        "observation_date",
    )
    if observation is None:
        raise RuntimeError("Phase 3.7.0 observation state missing")

    lifecycle = latest(
        sb,
        "paper_daily_lifecycle_evidence_v92",
        args.portfolio_id,
        "evidence_date",
    )
    if lifecycle is None:
        raise RuntimeError("Phase 3.6.9 lifecycle evidence missing")

    result = evaluate(readiness, observation, lifecycle)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "promotion_date": args.promotion_date,
        "result": result,
        "source_readiness_evidence_sha256": readiness.get("evidence_sha256"),
        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_lifecycle_evidence_sha256": lifecycle.get("evidence_sha256"),
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
        "promotion_date": args.promotion_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "promotion_state": result["promotion_state"],
        "paper_acceptance_eligibility_promoted": result["promotion_authorized"],

        "readiness_state": result["readiness_state"],
        "observation_state": result["observation_state"],
        "lifecycle_state": result["lifecycle_state"],

        "observation_days": result["observation_days"],
        "remaining_days": result["remaining_days"],
        "lifecycle_pass_rate": result["pass_rate"],
        "safety_revocation_days": result["safety_revocations"],
        "evidence_chain_break_count": result["chain_breaks"],
        "max_drawdown": result["max_drawdown"],
        "signal_days": result["signal_days"],
        "fill_days": result["fill_days"],

        "observation_validated": result["observation_validated"],
        "acceptance_candidate": result["acceptance_candidate"],

        "reason_codes": result["reasons"],
        "hard_failures": result["hard_failures"],

        "source_readiness_evidence_sha256": readiness.get("evidence_sha256"),
        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_lifecycle_evidence_sha256": lifecycle.get("evidence_sha256"),

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
        "paper_acceptance_promotion_control_v92",
        payload,
        "portfolio_id,promotion_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_acceptance_promotion_control_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2")
    print()
    print("## Production Paper Observation Daily Automation + Acceptance Promotion Controller")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Promotion Date: `{args.promotion_date}`")
    print(f"- Promotion State: **{result['promotion_state']}**")
    print(f"- Paper Acceptance Eligibility Promoted: **{'YES' if result['promotion_authorized'] else 'NO'}**")
    print()
    print("## Canonical Inputs")
    print()
    print(f"- Acceptance Readiness: **{result['readiness_state']}**")
    print(f"- Observation State: **{result['observation_state']}**")
    print(f"- Lifecycle State: **{result['lifecycle_state']}**")
    print(f"- Observation Day: **{result['observation_days']} / 20**")
    print(f"- Remaining Days: **{result['remaining_days']}**")
    print(f"- Lifecycle PASS Rate: **{result['pass_rate'] * 100:.2f}%**")
    print(f"- Observation Validated: **{'YES' if result['observation_validated'] else 'NO'}**")
    print(f"- Acceptance Candidate: **{'YES' if result['acceptance_candidate'] else 'NO'}**")
    print()
    print("## Safety / Coverage")
    print()
    print(f"- Safety Revocations: **{result['safety_revocations']}**")
    print(f"- Evidence Chain Breaks: **{result['chain_breaks']}**")
    print(f"- Maximum Drawdown: **{result['max_drawdown'] * 100:.4f}%**")
    print(f"- Signal Days: **{result['signal_days']}**")
    print(f"- Fill Days: **{result['fill_days']}**")
    print()
    print("## Promotion Reasons")
    print()
    for item in result["reasons"]:
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
    print("- Real-money promotion authority: **NOT PRESENT IN THIS PHASE**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase372")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "acceptance_promotion_control.json"),
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

    # OBSERVATION_CONTINUES is the expected successful state during Day 1..19.
    # FAIL_CLOSED is persisted as a governance outcome; runtime faults still fail.
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE372_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_acceptance_promotion_control_v92 (
    id bigint generated by default as identity primary key,
    promotion_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER',

    promotion_state text not null,
    paper_acceptance_eligibility_promoted boolean not null default false,

    readiness_state text not null default 'UNKNOWN',
    observation_state text not null default 'UNKNOWN',
    lifecycle_state text not null default 'UNKNOWN',

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

    reason_codes jsonb not null default '[]'::jsonb,
    hard_failures jsonb not null default '[]'::jsonb,

    source_readiness_evidence_sha256 text,
    source_observation_evidence_sha256 text,
    source_lifecycle_evidence_sha256 text,

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

    constraint ck_phase372_promotion_state check (
        promotion_state in (
            'OBSERVATION_CONTINUES',
            'PAPER_ACCEPTANCE_ELIGIBLE',
            'PAPER_ACCEPTANCE_LIMITED_COVERAGE',
            'PROMOTION_HELD',
            'FAIL_CLOSED'
        )
    ),
    constraint ck_phase372_paper_only check (paper_only = true),
    constraint ck_phase372_no_broker_api check (broker_api_used = false),
    constraint ck_phase372_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase372_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase372_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase372_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase372_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_acceptance_promotion_control_v92_portfolio_date
    on public.paper_acceptance_promotion_control_v92 (portfolio_id, promotion_date);

create index if not exists ix_paper_acceptance_promotion_control_v92_state_date
    on public.paper_acceptance_promotion_control_v92 (promotion_state, promotion_date desc);

create table if not exists public.paper_acceptance_promotion_control_audit_v92 (
    id bigint generated by default as identity primary key,
    promotion_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER',

    promotion_state text not null,
    paper_acceptance_eligibility_promoted boolean not null default false,

    readiness_state text not null default 'UNKNOWN',
    observation_state text not null default 'UNKNOWN',
    lifecycle_state text not null default 'UNKNOWN',

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

    reason_codes jsonb not null default '[]'::jsonb,
    hard_failures jsonb not null default '[]'::jsonb,

    source_readiness_evidence_sha256 text,
    source_observation_evidence_sha256 text,
    source_lifecycle_evidence_sha256 text,
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

    constraint ck_phase372_audit_paper_only check (paper_only = true),
    constraint ck_phase372_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase372_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase372_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase372_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase372_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase372_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_acceptance_promotion_control_audit_v92_portfolio_created
    on public.paper_acceptance_promotion_control_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_acceptance_promotion_control_v92 enable row level security;
alter table public.paper_acceptance_promotion_control_audit_v92 enable row level security;

comment on table public.paper_acceptance_promotion_control_v92 is
'GPT Quant V9.2 Phase 3.7.2 automated Production Paper observation acceptance-promotion state. No real-money authority.';

comment on table public.paper_acceptance_promotion_control_audit_v92 is
'GPT Quant V9.2 Phase 3.7.2 immutable-style acceptance-promotion audit evidence.';

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.7.2 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.2 - Production Paper Observation Daily Automation Acceptance Promotion Controller

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
    # 13:45 UTC = 21:45 Asia/Taipei, weekdays.
    # Runs after Phase 3.7.1 readiness monitor at 13:30 UTC.
    - cron: "45 13 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase372-production-paper-acceptance-promotion
  cancel-in-progress: false

jobs:
  observation-daily-automation-acceptance-promotion:
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

      - name: Compile Phase 3.7.2
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

      - name: Validate Phase 3.7.2 contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER' \
            automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

          grep -q '"paper_observation_acceptance_readiness_v92"' \
            automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

          grep -q '"paper_operations_observation_validation_v92"' \
            automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

          grep -q '"paper_daily_lifecycle_evidence_v92"' \
            automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

          grep -q 'Real-money promotion authority: \*\*NOT PRESENT IN THIS PHASE\*\*' \
            automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py

          echo "Phase 3.7.2 acceptance promotion controller contract: PASS"

      - name: Execute Phase 3.7.2
        shell: bash
        run: |
          mkdir -p artifacts/phase372

          python automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase372/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase372/summary.md ]; then
            cat artifacts/phase372/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase372-paper-acceptance-promotion-control
          path: artifacts/phase372/
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
    Fail "Phase 3.7.2 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER",
    "paper_observation_acceptance_readiness_v92",
    "paper_operations_observation_validation_v92",
    "paper_daily_lifecycle_evidence_v92",
    "paper_acceptance_promotion_control_v92",
    "OBSERVATION_CONTINUES",
    "PAPER_ACCEPTANCE_ELIGIBLE",
    "PAPER_ACCEPTANCE_LIMITED_COVERAGE",
    "PROMOTION_HELD",
    "FAIL_CLOSED"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.7.2 required token missing: $token"
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

if ((Get-Item $sqlTarget).Length -lt 3500) {
    Fail "Phase 3.7.2 SQL unexpectedly small or empty."
}

Write-Host "Acceptance promotion contract scan: PASS" -ForegroundColor Green
Write-Host "Observation/readiness canonical source scan: PASS" -ForegroundColor Green
Write-Host "20-day non-bypass gate scan: PASS" -ForegroundColor Green
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
        Write-Host "No staged Phase 3.7.2 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.7.2 observation daily automation acceptance promotion controller"
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
Write-Host "  automation/v92/paper_trading_phase372_production_paper_observation_daily_automation_acceptance_promotion_controller.py"
Write-Host "  supabase/PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase372-production-paper-observation-daily-automation-acceptance-promotion-controller.yml"
Write-Host ""
Write-Host "Expected Day 1-19 result:" -ForegroundColor Cyan
Write-Host "  Promotion State: OBSERVATION_CONTINUES"
Write-Host "  Paper Acceptance Eligibility Promoted: NO"
Write-Host "  Acceptance Readiness: NOT_READY"
Write-Host ""
Write-Host "Expected mature result after real observation evidence:" -ForegroundColor Cyan
Write-Host "  Promotion State: PAPER_ACCEPTANCE_ELIGIBLE"
Write-Host "  Paper Acceptance Eligibility Promoted: YES"
Write-Host "  Observation Day: 20+ / 20"
Write-Host "  Lifecycle PASS Rate: >= 95%"
Write-Host "  Observation Validated: YES"
Write-Host "  Acceptance Candidate: YES"
Write-Host ""
Write-Host "Important:" -ForegroundColor Yellow
Write-Host "  PAPER_ACCEPTANCE_ELIGIBLE authorizes only the NEXT PAPER acceptance gate."
Write-Host "  It does NOT authorize broker orders or real-money trading."
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
Write-Host "  1) Run supabase/PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.2 - Production Paper Observation Daily Automation Acceptance Promotion Controller."
Write-Host "  4) During Days 1-19, OBSERVATION_CONTINUES is the expected PASS state."
Write-Host "  5) Do not fabricate or backfill observation days to force promotion."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
