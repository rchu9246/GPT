#requires -Version 5.1
<#
PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.0 — Production Paper Autonomous Operations Observation + Validation

Purpose
-------
Turn the Phase 3.6.9 daily lifecycle evidence ledger into a multi-day
Production Paper observation and validation program.

This phase DOES NOT authorize real-money trading.
It evaluates whether autonomous paper operations are stable enough to continue
the formal observation period and eventually enter a separate acceptance gate.

Default validation policy
-------------------------
  Minimum observation days        : 20
  Minimum lifecycle PASS rate     : 95%
  Maximum drawdown                : 15%
  Safety revocation tolerance     : 0
  Evidence-chain break tolerance  : 0

Signal/fill coverage is reported separately:
  - zero-signal days are valid;
  - lack of fill coverage does not FAIL the observation engine;
  - final state remains OBSERVING / VALIDATED_WITH_LIMITED_TRADE_COVERAGE until
    sufficient execution lifecycle evidence exists.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py
  supabase/PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase370-production-paper-autonomous-operations-observation-validation.yml
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

Section "GPT Quant V9.2 — Phase 3.7.0 Observation + Validation"

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
    "automation/v92/paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine.py",
    "automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase370-production-paper-autonomous-operations-observation-validation.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase370-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.7.0 observation engine"

$py = @'
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

STATE_OBSERVING = "OBSERVING"
STATE_VALIDATED = "VALIDATED"
STATE_LIMITED = "VALIDATED_WITH_LIMITED_TRADE_COVERAGE"
STATE_FAIL_CLOSED = "FAIL_CLOSED"

PASS_LIFECYCLE_STATES = {"PASS", "PASS_WITH_OBSERVATION"}

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

def evidence_history(sb: Supabase, portfolio_id: str, limit: int) -> List[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + "&order=evidence_date.asc"
        + "&limit=" + str(limit)
    )
    return sb.get("paper_daily_lifecycle_evidence_v92", query)

def chain_breaks(rows: List[Dict[str, Any]]) -> List[str]:
    breaks: List[str] = []
    previous_sha: Optional[str] = None

    for index, row in enumerate(rows):
        current_date = str(row.get("evidence_date") or f"row-{index+1}")
        declared_previous = str(row.get("previous_evidence_sha256") or "")
        current_sha = str(row.get("evidence_sha256") or "")

        if index == 0:
            if declared_previous not in {"GENESIS", ""}:
                breaks.append(f"{current_date}:FIRST_RECORD_PREVIOUS_NOT_GENESIS")
        else:
            if declared_previous != (previous_sha or ""):
                breaks.append(f"{current_date}:PREVIOUS_SHA_MISMATCH")

        if len(current_sha) != 64:
            breaks.append(f"{current_date}:INVALID_CURRENT_SHA256")

        previous_sha = current_sha

    return breaks

def nav_metrics(rows: List[Dict[str, Any]]) -> Tuple[float, float, float, float]:
    navs = [as_float(r.get("nav"), 0.0) for r in rows]
    navs = [v for v in navs if v > 0]

    if not navs:
        return 0.0, 0.0, 0.0, 0.0

    initial = navs[0]
    latest = navs[-1]
    cumulative_return = (latest / initial - 1.0) if initial else 0.0

    peak = navs[0]
    max_drawdown = 0.0
    for nav in navs:
        peak = max(peak, nav)
        if peak > 0:
            dd = nav / peak - 1.0
            max_drawdown = min(max_drawdown, dd)

    return initial, latest, cumulative_return, max_drawdown

def evaluate(rows: List[Dict[str, Any]], policy: Dict[str, Any]) -> Dict[str, Any]:
    count = len(rows)

    passed_days = sum(
        1 for r in rows
        if str(r.get("lifecycle_state") or "").upper() in PASS_LIFECYCLE_STATES
        and as_bool(r.get("lifecycle_passed"), False)
    )
    pass_rate = (passed_days / count) if count else 0.0

    fail_closed_days = sum(
        1 for r in rows
        if str(r.get("lifecycle_state") or "").upper() == "FAIL_CLOSED"
    )
    safety_revocation_days = sum(
        1 for r in rows
        if as_bool(r.get("safety_revocation_triggered"), False)
    )
    controller_executed_days = sum(
        1 for r in rows
        if as_bool(r.get("daily_paper_cycle_executed"), False)
    )
    authorized_days = sum(
        1 for r in rows
        if as_bool(r.get("autonomous_daily_operations_authorized"), False)
    )

    signal_days = sum(1 for r in rows if as_int(r.get("eligible_signals"), 0) > 0)
    order_days = sum(1 for r in rows if as_int(r.get("order_intents_created"), 0) > 0)
    fill_days = sum(1 for r in rows if as_int(r.get("simulated_fills_created"), 0) > 0)
    settled_fill_days = sum(1 for r in rows if as_int(r.get("fills_settled"), 0) > 0)

    breaks = chain_breaks(rows)
    initial_nav, latest_nav, cumulative_return, max_drawdown = nav_metrics(rows)

    hard_failures: List[str] = []
    observations: List[str] = []

    if safety_revocation_days > int(policy["max_safety_revocation_days"]):
        hard_failures.append("SAFETY_REVOCATION_TOLERANCE_EXCEEDED")
    if len(breaks) > int(policy["max_chain_breaks"]):
        hard_failures.append("EVIDENCE_CHAIN_BREAK")
    if max_drawdown < -abs(float(policy["max_drawdown_pct"])):
        hard_failures.append("MAX_DRAWDOWN_LIMIT_EXCEEDED")

    min_days = int(policy["min_observation_days"])
    min_pass_rate = float(policy["min_pass_rate"])

    history_ready = count >= min_days
    pass_rate_ready = pass_rate >= min_pass_rate

    if count < min_days:
        observations.append("INSUFFICIENT_OBSERVATION_DAYS")
    if count and pass_rate < min_pass_rate:
        observations.append("PASS_RATE_BELOW_TARGET")
    if signal_days == 0:
        observations.append("NO_SIGNAL_DAY_COVERAGE_YET")
    if fill_days == 0:
        observations.append("NO_SIMULATED_FILL_COVERAGE_YET")

    if hard_failures:
        state = STATE_FAIL_CLOSED
        validated = False
    elif not history_ready or not pass_rate_ready:
        state = STATE_OBSERVING
        validated = False
    elif fill_days == 0:
        state = STATE_LIMITED
        validated = True
    else:
        state = STATE_VALIDATED
        validated = True

    remaining_days = max(0, min_days - count)

    return {
        "observation_state": state,
        "validated": validated,
        "observation_days": count,
        "remaining_minimum_days": remaining_days,
        "passed_days": passed_days,
        "pass_rate": round(pass_rate, 6),
        "fail_closed_days": fail_closed_days,
        "safety_revocation_days": safety_revocation_days,
        "controller_executed_days": controller_executed_days,
        "authorized_days": authorized_days,
        "signal_days": signal_days,
        "order_days": order_days,
        "fill_days": fill_days,
        "settled_fill_days": settled_fill_days,
        "evidence_chain_breaks": breaks,
        "initial_nav": initial_nav,
        "latest_nav": latest_nav,
        "cumulative_return": cumulative_return,
        "max_drawdown": max_drawdown,
        "hard_failures": hard_failures,
        "observations": observations,
        "acceptance_candidate": (
            validated
            and state == STATE_VALIDATED
            and not hard_failures
        ),
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--observation-date", default=str(date.today()))
    parser.add_argument("--history-limit", type=int, default=120)
    args = parser.parse_args()

    date.fromisoformat(args.observation_date)

    policy = {
        "min_observation_days": int(os.getenv("PHASE370_MIN_OBSERVATION_DAYS", "20")),
        "min_pass_rate": float(os.getenv("PHASE370_MIN_PASS_RATE", "0.95")),
        "max_drawdown_pct": float(os.getenv("PHASE370_MAX_DRAWDOWN_PCT", "0.15")),
        "max_safety_revocation_days": int(os.getenv("PHASE370_MAX_SAFETY_REVOCATION_DAYS", "0")),
        "max_chain_breaks": int(os.getenv("PHASE370_MAX_CHAIN_BREAKS", "0")),
    }

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
    rows = evidence_history(sb, args.portfolio_id, args.history_limit)

    if not rows:
        raise RuntimeError("No Phase 3.6.9 lifecycle evidence found")

    result = evaluate(rows, policy)

    source_tail_sha = str(rows[-1].get("evidence_sha256") or "")
    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "observation_date": args.observation_date,
        "policy": policy,
        "result": result,
        "source_tail_evidence_sha256": source_tail_sha,
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
        "observation_date": args.observation_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "observation_state": result["observation_state"],
        "validated": result["validated"],
        "acceptance_candidate": result["acceptance_candidate"],

        "observation_days": result["observation_days"],
        "remaining_minimum_days": result["remaining_minimum_days"],
        "passed_days": result["passed_days"],
        "pass_rate": result["pass_rate"],

        "controller_executed_days": result["controller_executed_days"],
        "authorized_days": result["authorized_days"],
        "signal_days": result["signal_days"],
        "order_days": result["order_days"],
        "fill_days": result["fill_days"],
        "settled_fill_days": result["settled_fill_days"],

        "fail_closed_days": result["fail_closed_days"],
        "safety_revocation_days": result["safety_revocation_days"],
        "evidence_chain_break_count": len(result["evidence_chain_breaks"]),

        "initial_nav": result["initial_nav"],
        "latest_nav": result["latest_nav"],
        "cumulative_return": result["cumulative_return"],
        "max_drawdown": result["max_drawdown"],

        "hard_failures": result["hard_failures"],
        "observations": result["observations"],
        "policy": policy,

        "source_tail_evidence_sha256": source_tail_sha,

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
        "paper_operations_observation_validation_v92",
        payload,
        "portfolio_id,observation_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_operations_observation_validation_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.0")
    print()
    print("## Production Paper Autonomous Operations Observation + Validation")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Observation Date: `{args.observation_date}`")
    print(f"- Observation State: **{result['observation_state']}**")
    print(f"- Observation Validated: **{'YES' if result['validated'] else 'NO'}**")
    print(f"- Acceptance Candidate: **{'YES' if result['acceptance_candidate'] else 'NO'}**")
    print()
    print("## Observation Progress")
    print()
    print(f"- Observation Days: **{result['observation_days']} / {policy['min_observation_days']}**")
    print(f"- Remaining Minimum Days: **{result['remaining_minimum_days']}**")
    print(f"- Lifecycle PASS Days: **{result['passed_days']}**")
    print(f"- Lifecycle PASS Rate: **{result['pass_rate'] * 100:.2f}%**")
    print(f"- Controller Executed Days: **{result['controller_executed_days']}**")
    print(f"- Authorized Days: **{result['authorized_days']}**")
    print()
    print("## Trade-Lifecycle Coverage")
    print()
    print(f"- Signal Days: **{result['signal_days']}**")
    print(f"- Order Days: **{result['order_days']}**")
    print(f"- Simulated Fill Days: **{result['fill_days']}**")
    print(f"- Settled Fill Days: **{result['settled_fill_days']}**")
    print()
    print("## Portfolio Observation")
    print()
    print(f"- Initial NAV: **{result['initial_nav']:.2f}**")
    print(f"- Latest NAV: **{result['latest_nav']:.2f}**")
    print(f"- Cumulative Return: **{result['cumulative_return'] * 100:.4f}%**")
    print(f"- Maximum Drawdown: **{result['max_drawdown'] * 100:.4f}%**")
    print()
    print("## Governance Integrity")
    print()
    print(f"- FAIL_CLOSED Days: **{result['fail_closed_days']}**")
    print(f"- Safety Revocation Days: **{result['safety_revocation_days']}**")
    print(f"- Evidence Chain Breaks: **{len(result['evidence_chain_breaks'])}**")

    if result["hard_failures"]:
        print()
        print("## Hard Failures")
        print()
        for item in result["hard_failures"]:
            print(f"- `{item}`")

    if result["observations"]:
        print()
        print("## Observation Notes")
        print()
        for item in result["observations"]:
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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase370")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "observation_validation_evidence.json"),
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

    # OBSERVING is a successful governance state while history accumulates.
    # FAIL_CLOSED is also persisted as a governance outcome; only software/runtime
    # errors fail the GitHub job.
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE370_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.7.0 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_operations_observation_validation_v92 (
    id bigint generated by default as identity primary key,
    observation_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION',

    observation_state text not null,
    validated boolean not null default false,
    acceptance_candidate boolean not null default false,

    observation_days integer not null default 0,
    remaining_minimum_days integer not null default 0,
    passed_days integer not null default 0,
    pass_rate numeric not null default 0,

    controller_executed_days integer not null default 0,
    authorized_days integer not null default 0,
    signal_days integer not null default 0,
    order_days integer not null default 0,
    fill_days integer not null default 0,
    settled_fill_days integer not null default 0,

    fail_closed_days integer not null default 0,
    safety_revocation_days integer not null default 0,
    evidence_chain_break_count integer not null default 0,

    initial_nav numeric not null default 0,
    latest_nav numeric not null default 0,
    cumulative_return numeric not null default 0,
    max_drawdown numeric not null default 0,

    hard_failures jsonb not null default '[]'::jsonb,
    observations jsonb not null default '[]'::jsonb,
    policy jsonb not null default '{}'::jsonb,

    source_tail_evidence_sha256 text not null,

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

    constraint ck_phase370_observation_state check (
        observation_state in (
            'OBSERVING',
            'VALIDATED',
            'VALIDATED_WITH_LIMITED_TRADE_COVERAGE',
            'FAIL_CLOSED'
        )
    ),
    constraint ck_phase370_paper_only check (paper_only = true),
    constraint ck_phase370_no_broker_api check (broker_api_used = false),
    constraint ck_phase370_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase370_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase370_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase370_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase370_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_operations_observation_validation_v92_portfolio_date
    on public.paper_operations_observation_validation_v92 (portfolio_id, observation_date);

create index if not exists ix_paper_operations_observation_validation_v92_state_date
    on public.paper_operations_observation_validation_v92 (observation_state, observation_date desc);

create table if not exists public.paper_operations_observation_validation_audit_v92 (
    id bigint generated by default as identity primary key,
    observation_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION',

    observation_state text not null,
    validated boolean not null default false,
    acceptance_candidate boolean not null default false,

    observation_days integer not null default 0,
    remaining_minimum_days integer not null default 0,
    passed_days integer not null default 0,
    pass_rate numeric not null default 0,

    controller_executed_days integer not null default 0,
    authorized_days integer not null default 0,
    signal_days integer not null default 0,
    order_days integer not null default 0,
    fill_days integer not null default 0,
    settled_fill_days integer not null default 0,

    fail_closed_days integer not null default 0,
    safety_revocation_days integer not null default 0,
    evidence_chain_break_count integer not null default 0,

    initial_nav numeric not null default 0,
    latest_nav numeric not null default 0,
    cumulative_return numeric not null default 0,
    max_drawdown numeric not null default 0,

    hard_failures jsonb not null default '[]'::jsonb,
    observations jsonb not null default '[]'::jsonb,
    policy jsonb not null default '{}'::jsonb,

    source_tail_evidence_sha256 text not null,
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

    constraint ck_phase370_audit_paper_only check (paper_only = true),
    constraint ck_phase370_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase370_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase370_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase370_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase370_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase370_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_operations_observation_validation_audit_v92_portfolio_created
    on public.paper_operations_observation_validation_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_operations_observation_validation_v92 enable row level security;
alter table public.paper_operations_observation_validation_audit_v92 enable row level security;

comment on table public.paper_operations_observation_validation_v92 is
'GPT Quant V9.2 Phase 3.7.0 multi-day Production Paper autonomous operations observation and validation state.';

comment on table public.paper_operations_observation_validation_audit_v92 is
'GPT Quant V9.2 Phase 3.7.0 immutable-style observation/validation audit evidence.';

notify pgrst, 'reload schema';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.7.0 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.7.0 - Production Paper Autonomous Operations Observation Validation

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
    # 13:15 UTC = 21:15 Asia/Taipei, weekdays.
    # Runs after Phase 3.6.9 evidence lifecycle governance at 13:00 UTC.
    - cron: "15 13 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase370-production-paper-observation-validation
  cancel-in-progress: false

jobs:
  production-paper-observation-validation:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE370_MIN_OBSERVATION_DAYS: "20"
      PHASE370_MIN_PASS_RATE: "0.95"
      PHASE370_MAX_DRAWDOWN_PCT: "0.15"
      PHASE370_MAX_SAFETY_REVOCATION_DAYS: "0"
      PHASE370_MAX_CHAIN_BREAKS: "0"

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Compile Phase 3.7.0
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py

      - name: Validate Phase 3.7.0 observation contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION' \
            automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py

          grep -q '"paper_daily_lifecycle_evidence_v92"' \
            automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py

          grep -q '"live_money_release_authorized": False' \
            automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py

          echo "Phase 3.7.0 observation + validation contract: PASS"

      - name: Execute Phase 3.7.0
        shell: bash
        run: |
          mkdir -p artifacts/phase370

          python automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase370/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase370/summary.md ]; then
            cat artifacts/phase370/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase370-production-paper-observation-validation
          path: artifacts/phase370/
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
    Fail "Phase 3.7.0 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION",
    "paper_daily_lifecycle_evidence_v92",
    "paper_operations_observation_validation_v92",
    "paper_operations_observation_validation_audit_v92",
    "OBSERVING",
    "VALIDATED",
    "VALIDATED_WITH_LIMITED_TRADE_COVERAGE",
    "FAIL_CLOSED",
    "PHASE370_MIN_OBSERVATION_DAYS"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.7.0 required token missing: $token"
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

if ((Get-Item $sqlTarget).Length -lt 4000) {
    Fail "Phase 3.7.0 SQL unexpectedly small or empty."
}

Write-Host "Observation policy contract scan: PASS" -ForegroundColor Green
Write-Host "Lifecycle evidence source scan: PASS" -ForegroundColor Green
Write-Host "Multi-day metrics contract scan: PASS" -ForegroundColor Green
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
        Write-Host "No staged Phase 3.7.0 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.7.0 production paper observation validation"
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
Write-Host "  automation/v92/paper_trading_phase370_production_paper_autonomous_operations_observation_validation.py"
Write-Host "  supabase/PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase370-production-paper-autonomous-operations-observation-validation.yml"
Write-Host ""
Write-Host "Default observation policy:" -ForegroundColor Cyan
Write-Host "  Minimum observation days: 20"
Write-Host "  Minimum lifecycle PASS rate: 95%"
Write-Host "  Maximum drawdown: 15%"
Write-Host "  Safety revocation tolerance: 0"
Write-Host "  Evidence chain break tolerance: 0"
Write-Host ""
Write-Host "Expected first-day result:" -ForegroundColor Cyan
Write-Host "  Observation State: OBSERVING"
Write-Host "  Observation Days: 1 / 20"
Write-Host "  Observation Validated: NO"
Write-Host "  Acceptance Candidate: NO"
Write-Host "  Lifecycle PASS Rate: 100%"
Write-Host "  Evidence Chain Breaks: 0"
Write-Host ""
Write-Host "Expected mature result:" -ForegroundColor Cyan
Write-Host "  Observation State: VALIDATED"
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
Write-Host "  1) Run supabase/PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.7.0 - Production Paper Autonomous Operations Observation Validation."
Write-Host "  4) First run should normally report OBSERVING because only one/few lifecycle days exist."
Write-Host "  5) Let the Production Paper daily chain accumulate evidence; do not fabricate history."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
