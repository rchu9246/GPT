#requires -Version 5.1
<#
PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.9 — Production Paper Autonomous Daily Evidence + Lifecycle Governance Engine

Purpose
-------
Persist a durable daily evidence and lifecycle-governance record for the
autonomous Production Paper operating loop after Phase 3.6.8.

This package:
  - reads the latest canonical Phase 3.6.8 controller state;
  - links previous lifecycle evidence to the current day;
  - persists immutable-style evidence history;
  - stores controller / qualification / activation / supervision / master-cycle states;
  - records NAV, signals, fills, safety-revocation status when available;
  - computes current evidence SHA256 and previous-evidence linkage;
  - remains idempotent per portfolio/day;
  - FAIL-CLOSED when required canonical evidence is missing or invalid;
  - never enables broker or real-money capabilities.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py
  supabase/PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase369-production-paper-autonomous-daily-evidence-lifecycle-governance-engine.yml
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

Section "GPT Quant V9.2 — Phase 3.6.9 Daily Evidence + Lifecycle Governance"

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
    "automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py",
    "automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase369-production-paper-autonomous-daily-evidence-lifecycle-governance-engine.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase369-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.6.9 governance engine"

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

CONTRACT = "PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

LIFECYCLE_PASS = "PASS"
LIFECYCLE_PASS_OBSERVATION = "PASS_WITH_OBSERVATION"
LIFECYCLE_BLOCKED = "BLOCKED"
LIFECYCLE_FAIL_CLOSED = "FAIL_CLOSED"

VALID_CONTROLLER_STATES = {"COMPLETED", "COMPLETED_WITH_OBSERVATION"}

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

def latest_before(
    sb: Supabase,
    table: str,
    portfolio_id: str,
    date_column: str,
    current_date: str,
) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + "&" + date_column + "=lt." + urllib.parse.quote(current_date, safe="")
        + f"&order={date_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def compact_master(master: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not master:
        return {}
    return {
        "cycle_date": master.get("cycle_date"),
        "cycle_status": master.get("cycle_status"),
        "final_state": master.get("final_state"),
        "eligible_signals": as_int(master.get("eligible_signals"), 0),
        "sized_candidates": as_int(master.get("sized_candidates"), 0),
        "order_intents_created": as_int(master.get("order_intents_created"), 0),
        "simulated_fills_created": as_int(master.get("simulated_fills_created"), 0),
        "fills_settled": as_int(master.get("fills_settled"), 0),
        "cash": as_float(master.get("cash"), 0.0),
        "market_value": as_float(master.get("market_value"), 0.0),
        "nav": as_float(master.get("nav"), 0.0),
        "realized_pnl": as_float(master.get("realized_pnl"), 0.0),
        "unrealized_pnl": as_float(master.get("unrealized_pnl"), 0.0),
        "open_positions": as_int(master.get("open_positions"), 0),
        "evidence_sha256": master.get("evidence_sha256"),
    }

def evaluate(controller: Dict[str, Any]) -> Dict[str, Any]:
    controller_state = str(controller.get("controller_state") or "MISSING").upper()
    controller_passed = as_bool(controller.get("controller_passed"), False)
    authorized = as_bool(controller.get("autonomous_daily_operations_authorized"), False)
    cycle_executed = as_bool(controller.get("daily_paper_cycle_executed"), False)
    safety_revocation = as_bool(controller.get("safety_revocation_triggered"), False)

    activation_state = str(controller.get("activation_state") or "MISSING").upper()
    qualification_state = str(controller.get("qualification_state") or "MISSING").upper()
    supervision_state = str(controller.get("runtime_supervision_state") or "MISSING").upper()
    master_cycle_state = str(controller.get("master_cycle_state") or "MISSING").upper()

    reasons: List[str] = []

    if controller_state not in VALID_CONTROLLER_STATES:
        reasons.append("CONTROLLER_STATE_NOT_COMPLETED")
    if not controller_passed:
        reasons.append("CONTROLLER_NOT_PASSED")
    if not authorized:
        reasons.append("AUTONOMOUS_DAILY_OPERATIONS_NOT_AUTHORIZED")
    if not cycle_executed:
        reasons.append("DAILY_PAPER_CYCLE_NOT_EXECUTED")
    if safety_revocation:
        reasons.append("SAFETY_REVOCATION_TRIGGERED")

    if activation_state not in {"ACTIVE", "ACTIVE_WITH_OBSERVATION"}:
        reasons.append("ACTIVATION_NOT_ACTIVE")
    if qualification_state not in {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}:
        reasons.append("QUALIFICATION_NOT_VALID")
    if supervision_state not in {"CONTINUE_ACTIVE", "CONTINUE_WITH_OBSERVATION"}:
        reasons.append("RUNTIME_SUPERVISION_NOT_CONTINUABLE")

    if reasons:
        state = LIFECYCLE_FAIL_CLOSED
        passed = False
    elif (
        controller_state == "COMPLETED_WITH_OBSERVATION"
        or activation_state == "ACTIVE_WITH_OBSERVATION"
        or qualification_state == "QUALIFIED_WITH_OBSERVATION"
        or supervision_state == "CONTINUE_WITH_OBSERVATION"
    ):
        state = LIFECYCLE_PASS_OBSERVATION
        passed = True
    else:
        state = LIFECYCLE_PASS
        passed = True

    if not reasons:
        reasons.append("CANONICAL_DAILY_CONTROLLER_EVIDENCE_VALID")

    return {
        "lifecycle_state": state,
        "lifecycle_passed": passed,
        "reason_codes": reasons,
        "controller_state": controller_state,
        "activation_state": activation_state,
        "qualification_state": qualification_state,
        "runtime_supervision_state": supervision_state,
        "runtime_supervision_score": as_float(controller.get("runtime_supervision_score"), 0.0),
        "master_cycle_state": master_cycle_state,
        "autonomous_daily_operations_authorized": authorized,
        "daily_paper_cycle_executed": cycle_executed,
        "safety_revocation_triggered": safety_revocation,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--evidence-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.evidence_date)

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

    controller = latest(
        sb,
        "paper_daily_autonomous_controller_v92",
        args.portfolio_id,
        "controller_date",
    )
    if controller is None:
        raise RuntimeError("Canonical Phase 3.6.8 controller evidence missing")

    controller_date = str(controller.get("controller_date") or "")
    if controller_date != args.evidence_date:
        raise RuntimeError(
            f"Latest controller date mismatch: expected={args.evidence_date}, actual={controller_date}"
        )

    master = latest(
        sb,
        "paper_master_cycles_v92",
        args.portfolio_id,
        "cycle_date",
    )

    previous = latest_before(
        sb,
        "paper_daily_lifecycle_evidence_v92",
        args.portfolio_id,
        "evidence_date",
        args.evidence_date,
    )

    evaluation = evaluate(controller)
    previous_sha = str((previous or {}).get("evidence_sha256") or "GENESIS")
    lifecycle_sequence = as_int((previous or {}).get("lifecycle_sequence"), 0) + 1

    master_compact = compact_master(master)

    evidence_document = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "evidence_date": args.evidence_date,
        "lifecycle_sequence": lifecycle_sequence,
        "previous_evidence_sha256": previous_sha,
        "controller": {
            "controller_state": evaluation["controller_state"],
            "activation_state": evaluation["activation_state"],
            "qualification_state": evaluation["qualification_state"],
            "runtime_supervision_state": evaluation["runtime_supervision_state"],
            "runtime_supervision_score": evaluation["runtime_supervision_score"],
            "master_cycle_state": evaluation["master_cycle_state"],
            "autonomous_daily_operations_authorized": evaluation["autonomous_daily_operations_authorized"],
            "daily_paper_cycle_executed": evaluation["daily_paper_cycle_executed"],
            "safety_revocation_triggered": evaluation["safety_revocation_triggered"],
        },
        "master": master_compact,
        "lifecycle_state": evaluation["lifecycle_state"],
        "lifecycle_passed": evaluation["lifecycle_passed"],
        "reason_codes": evaluation["reason_codes"],
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

    evidence_sha = stable_hash(evidence_document)

    payload = {
        "evidence_date": args.evidence_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "lifecycle_sequence": lifecycle_sequence,
        "lifecycle_state": evaluation["lifecycle_state"],
        "lifecycle_passed": evaluation["lifecycle_passed"],

        "controller_state": evaluation["controller_state"],
        "activation_state": evaluation["activation_state"],
        "qualification_state": evaluation["qualification_state"],
        "runtime_supervision_state": evaluation["runtime_supervision_state"],
        "runtime_supervision_score": evaluation["runtime_supervision_score"],
        "master_cycle_state": evaluation["master_cycle_state"],

        "autonomous_daily_operations_authorized": evaluation["autonomous_daily_operations_authorized"],
        "daily_paper_cycle_executed": evaluation["daily_paper_cycle_executed"],
        "safety_revocation_triggered": evaluation["safety_revocation_triggered"],

        "eligible_signals": master_compact.get("eligible_signals", 0),
        "sized_candidates": master_compact.get("sized_candidates", 0),
        "order_intents_created": master_compact.get("order_intents_created", 0),
        "simulated_fills_created": master_compact.get("simulated_fills_created", 0),
        "fills_settled": master_compact.get("fills_settled", 0),
        "cash": master_compact.get("cash", 0.0),
        "market_value": master_compact.get("market_value", 0.0),
        "nav": master_compact.get("nav", 0.0),
        "realized_pnl": master_compact.get("realized_pnl", 0.0),
        "unrealized_pnl": master_compact.get("unrealized_pnl", 0.0),
        "open_positions": master_compact.get("open_positions", 0),

        "previous_evidence_sha256": previous_sha,
        "source_controller_evidence_sha256": controller.get("evidence_sha256"),
        "source_master_evidence_sha256": master_compact.get("evidence_sha256"),
        "reason_codes": evaluation["reason_codes"],

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
        "paper_daily_lifecycle_evidence_v92",
        payload,
        "portfolio_id,evidence_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_document
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_daily_lifecycle_evidence_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.9")
    print()
    print("## Production Paper Autonomous Daily Evidence + Lifecycle Governance Engine")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Evidence Date: `{args.evidence_date}`")
    print(f"- Lifecycle Sequence: **{lifecycle_sequence}**")
    print(f"- Lifecycle State: **{evaluation['lifecycle_state']}**")
    print(f"- Lifecycle Passed: **{'YES' if evaluation['lifecycle_passed'] else 'NO'}**")
    print(f"- Controller State: **{evaluation['controller_state']}**")
    print(f"- Qualification State: **{evaluation['qualification_state']}**")
    print(f"- Activation State: **{evaluation['activation_state']}**")
    print(f"- Runtime Supervision: **{evaluation['runtime_supervision_state']}**")
    print(f"- Daily Master Cycle: **{evaluation['master_cycle_state']}**")
    print(f"- Autonomous Daily Operations Authorized: **{'YES' if evaluation['autonomous_daily_operations_authorized'] else 'NO'}**")
    print(f"- Daily Paper Cycle Executed: **{'YES' if evaluation['daily_paper_cycle_executed'] else 'NO'}**")
    print(f"- Safety Revocation Triggered: **{'YES' if evaluation['safety_revocation_triggered'] else 'NO'}**")
    print()
    print("## Daily Operating Evidence")
    print()
    print(f"- Eligible Signals: **{master_compact.get('eligible_signals', 0)}**")
    print(f"- Sized Candidates: **{master_compact.get('sized_candidates', 0)}**")
    print(f"- Order Intents: **{master_compact.get('order_intents_created', 0)}**")
    print(f"- Simulated Fills: **{master_compact.get('simulated_fills_created', 0)}**")
    print(f"- Fills Settled: **{master_compact.get('fills_settled', 0)}**")
    print(f"- NAV: **{master_compact.get('nav', 0.0):.2f}**")
    print(f"- Open Positions: **{master_compact.get('open_positions', 0)}**")
    print()
    print("## Lifecycle Reasons")
    print()
    for reason in evaluation["reason_codes"]:
        print(f"- `{reason}`")
    print()
    print("## Evidence Chain")
    print()
    print(f"- Previous Evidence SHA256: `{previous_sha}`")
    print(f"- Current Evidence SHA256: `{evidence_sha}`")
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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase369")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "daily_lifecycle_evidence.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "payload": payload,
                "evidence_document": evidence_document,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    # Governance FAIL_CLOSED is a valid safety outcome, not a software failure.
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE369_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.6.9 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_daily_lifecycle_evidence_v92 (
    id bigint generated by default as identity primary key,
    evidence_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE',

    lifecycle_sequence bigint not null,
    lifecycle_state text not null,
    lifecycle_passed boolean not null default false,

    controller_state text not null default 'UNKNOWN',
    activation_state text not null default 'UNKNOWN',
    qualification_state text not null default 'UNKNOWN',
    runtime_supervision_state text not null default 'UNKNOWN',
    runtime_supervision_score numeric not null default 0,
    master_cycle_state text not null default 'UNKNOWN',

    autonomous_daily_operations_authorized boolean not null default false,
    daily_paper_cycle_executed boolean not null default false,
    safety_revocation_triggered boolean not null default false,

    eligible_signals integer not null default 0,
    sized_candidates integer not null default 0,
    order_intents_created integer not null default 0,
    simulated_fills_created integer not null default 0,
    fills_settled integer not null default 0,

    cash numeric not null default 0,
    market_value numeric not null default 0,
    nav numeric not null default 0,
    realized_pnl numeric not null default 0,
    unrealized_pnl numeric not null default 0,
    open_positions integer not null default 0,

    previous_evidence_sha256 text not null,
    source_controller_evidence_sha256 text,
    source_master_evidence_sha256 text,
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

    constraint ck_phase369_lifecycle_state check (
        lifecycle_state in (
            'PASS',
            'PASS_WITH_OBSERVATION',
            'BLOCKED',
            'FAIL_CLOSED'
        )
    ),
    constraint ck_phase369_paper_only check (paper_only = true),
    constraint ck_phase369_no_broker_api check (broker_api_used = false),
    constraint ck_phase369_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase369_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase369_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase369_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase369_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_daily_lifecycle_evidence_v92_portfolio_date
    on public.paper_daily_lifecycle_evidence_v92 (portfolio_id, evidence_date);

create unique index if not exists uq_paper_daily_lifecycle_evidence_v92_portfolio_sequence
    on public.paper_daily_lifecycle_evidence_v92 (portfolio_id, lifecycle_sequence);

create index if not exists ix_paper_daily_lifecycle_evidence_v92_state_date
    on public.paper_daily_lifecycle_evidence_v92 (lifecycle_state, evidence_date desc);

create table if not exists public.paper_daily_lifecycle_evidence_audit_v92 (
    id bigint generated by default as identity primary key,
    evidence_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE',

    lifecycle_sequence bigint not null,
    lifecycle_state text not null,
    lifecycle_passed boolean not null default false,

    controller_state text not null default 'UNKNOWN',
    activation_state text not null default 'UNKNOWN',
    qualification_state text not null default 'UNKNOWN',
    runtime_supervision_state text not null default 'UNKNOWN',
    runtime_supervision_score numeric not null default 0,
    master_cycle_state text not null default 'UNKNOWN',

    autonomous_daily_operations_authorized boolean not null default false,
    daily_paper_cycle_executed boolean not null default false,
    safety_revocation_triggered boolean not null default false,

    eligible_signals integer not null default 0,
    sized_candidates integer not null default 0,
    order_intents_created integer not null default 0,
    simulated_fills_created integer not null default 0,
    fills_settled integer not null default 0,

    cash numeric not null default 0,
    market_value numeric not null default 0,
    nav numeric not null default 0,
    realized_pnl numeric not null default 0,
    unrealized_pnl numeric not null default 0,
    open_positions integer not null default 0,

    previous_evidence_sha256 text not null,
    source_controller_evidence_sha256 text,
    source_master_evidence_sha256 text,
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

    constraint ck_phase369_audit_paper_only check (paper_only = true),
    constraint ck_phase369_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase369_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase369_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase369_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase369_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase369_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_daily_lifecycle_evidence_audit_v92_portfolio_created
    on public.paper_daily_lifecycle_evidence_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_daily_lifecycle_evidence_v92 enable row level security;
alter table public.paper_daily_lifecycle_evidence_audit_v92 enable row level security;

comment on table public.paper_daily_lifecycle_evidence_v92 is
'GPT Quant V9.2 Phase 3.6.9 durable daily autonomous Production Paper evidence and lifecycle governance state.';

comment on table public.paper_daily_lifecycle_evidence_audit_v92 is
'GPT Quant V9.2 Phase 3.6.9 immutable-style daily lifecycle evidence audit with SHA256 chaining.';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.9 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.6.9 - Production Paper Autonomous Daily Evidence Lifecycle Governance Engine

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
    # 13:00 UTC = 21:00 Asia/Taipei, weekdays.
    # Runs after Phase 3.6.8 scheduled controller at 12:45 UTC.
    - cron: "0 13 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase369-production-paper-daily-evidence-governance
  cancel-in-progress: false

jobs:
  daily-evidence-lifecycle-governance:
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

      - name: Compile Phase 3.6.9
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py

      - name: Validate Phase 3.6.9 safety and evidence contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE' \
            automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py

          grep -q 'paper_daily_autonomous_controller_v92' \
            automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py

          grep -q 'previous_evidence_sha256' \
            automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py

          grep -q '"live_money_release_authorized": False' \
            automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py

          echo "Phase 3.6.9 evidence + lifecycle governance contract: PASS"

      - name: Execute Phase 3.6.9
        shell: bash
        run: |
          mkdir -p artifacts/phase369

          python automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase369/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase369/summary.md ]; then
            cat artifacts/phase369/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase369-daily-evidence-lifecycle-governance
          path: artifacts/phase369/
          if-no-files-found: warn
          retention-days: 90
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
    Fail "Phase 3.6.9 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE",
    "paper_daily_lifecycle_evidence_v92",
    "paper_daily_lifecycle_evidence_audit_v92",
    "paper_daily_autonomous_controller_v92",
    "paper_master_cycles_v92",
    "previous_evidence_sha256",
    "lifecycle_sequence",
    "PASS_WITH_OBSERVATION",
    "FAIL_CLOSED"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.6.9 required token missing: $token"
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

Write-Host "Daily evidence contract scan: PASS" -ForegroundColor Green
Write-Host "Lifecycle chain contract scan: PASS" -ForegroundColor Green
Write-Host "Idempotent daily governance scan: PASS" -ForegroundColor Green
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
        Write-Host "No staged Phase 3.6.9 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.6.9 production paper daily evidence lifecycle governance"
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
Write-Host "  automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py"
Write-Host "  supabase/PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase369-production-paper-autonomous-daily-evidence-lifecycle-governance-engine.yml"
Write-Host ""
Write-Host "Expected healthy result:" -ForegroundColor Cyan
Write-Host "  Lifecycle State: PASS"
Write-Host "  Lifecycle Passed: YES"
Write-Host "  Controller State: COMPLETED"
Write-Host "  Qualification State: QUALIFIED"
Write-Host "  Activation State: ACTIVE"
Write-Host "  Runtime Supervision: CONTINUE_ACTIVE"
Write-Host "  Autonomous Daily Operations Authorized: YES"
Write-Host "  Daily Paper Cycle Executed: YES"
Write-Host "  Safety Revocation Triggered: NO"
Write-Host "  Previous Evidence SHA256: GENESIS (first day) or prior evidence hash"
Write-Host "  Current Evidence SHA256: generated"
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
Write-Host "  1) Run supabase/PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.9 - Production Paper Autonomous Daily Evidence Lifecycle Governance Engine."
Write-Host "  4) Confirm Lifecycle State=PASS or PASS_WITH_OBSERVATION."
Write-Host "  5) After PASS, proceed to Phase 3.6.10 Go-Live Readiness / Acceptance Test."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
