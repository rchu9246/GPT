#requires -Version 5.1
<#
PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.8 — Production Paper Daily Autonomous Operations Controller

Purpose
-------
Create the fail-closed daily autonomous Production Paper control loop.

The controller:
  1) reads the latest Phase 3.6.7 runtime supervision state;
  2) requires ACTIVE/QUALIFIED/CONTINUE_* authorization;
  3) executes the validated Phase 3.6.0 daily master orchestrator only when authorized;
  4) re-reads the canonical master-cycle result;
  5) persists one controller state + immutable-style audit row;
  6) never enables broker, real-money, or live-money capabilities.

Valid zero-signal / zero-order / zero-fill days remain valid paper-operation days
when the Phase 3.6.0 master cycle itself passes.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py
  supabase/PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase368-production-paper-daily-autonomous-operations-controller.yml
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

Section "GPT Quant V9.2 — Phase 3.6.8 Daily Autonomous Operations Controller"

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
    "automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py",
    "automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py"
)
foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase368-production-paper-daily-autonomous-operations-controller.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase368-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.6.8 controller"

$py = @'
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
FAIL_CLOSED_POLICY = True

CONTROLLER_COMPLETED = "COMPLETED"
CONTROLLER_COMPLETED_OBSERVATION = "COMPLETED_WITH_OBSERVATION"
CONTROLLER_BLOCKED = "BLOCKED"
CONTROLLER_FAILED = "FAILED"
CONTROLLER_FAIL_CLOSED = "FAIL_CLOSED"

ALLOWED_ACTIVATION = {"ACTIVE", "ACTIVE_WITH_OBSERVATION"}
ALLOWED_QUALIFICATION = {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}
ALLOWED_SUPERVISION = {"CONTINUE_ACTIVE", "CONTINUE_WITH_OBSERVATION"}
PASS_MASTER_STATES = {
    "PASS",
    "COMPLETED",
    "DAILY_MASTER_CYCLE_COMPLETED",
    "MASTER_CYCLE_COMPLETED",
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

def master_state(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return "MISSING"
    return str(
        row.get("cycle_status")
        or row.get("master_status")
        or row.get("final_state")
        or row.get("status")
        or "UNKNOWN"
    ).upper()

def preflight(supervision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if supervision is None:
        return {
            "authorized": False,
            "activation_state": "MISSING",
            "qualification_state": "MISSING",
            "supervision_state": "MISSING",
            "supervision_score": 0.0,
            "reason": "RUNTIME_SUPERVISION_MISSING",
            "observation": False,
        }

    activation_state = str(supervision.get("activation_state") or "MISSING").upper()
    qualification_state = str(supervision.get("qualification_state") or "MISSING").upper()
    supervision_state = str(supervision.get("supervision_state") or "MISSING").upper()
    continued = as_bool(supervision.get("autonomous_paper_operations_continued"), False)
    revoked = as_bool(supervision.get("safety_revocation_triggered"), False)
    score = float(supervision.get("supervision_score") or 0.0)

    reasons: List[str] = []
    if activation_state not in ALLOWED_ACTIVATION:
        reasons.append("ACTIVATION_NOT_ACTIVE")
    if qualification_state not in ALLOWED_QUALIFICATION:
        reasons.append("QUALIFICATION_NOT_QUALIFIED")
    if supervision_state not in ALLOWED_SUPERVISION:
        reasons.append("SUPERVISION_NOT_CONTINUABLE")
    if not continued:
        reasons.append("AUTONOMOUS_CONTINUATION_NOT_AUTHORIZED")
    if revoked:
        reasons.append("SAFETY_REVOCATION_ALREADY_TRIGGERED")

    return {
        "authorized": not reasons,
        "activation_state": activation_state,
        "qualification_state": qualification_state,
        "supervision_state": supervision_state,
        "supervision_score": score,
        "reason": "PRECHECK_PASS" if not reasons else "|".join(reasons),
        "observation": (
            activation_state == "ACTIVE_WITH_OBSERVATION"
            or qualification_state == "QUALIFIED_WITH_OBSERVATION"
            or supervision_state == "CONTINUE_WITH_OBSERVATION"
        ),
    }

def run_master(approver: str, portfolio_id: str, strategy_version: str) -> subprocess.CompletedProcess[str]:
    script = os.path.join(
        os.getcwd(),
        "automation",
        "v92",
        "paper_trading_phase360_production_paper_daily_master_orchestrator.py",
    )
    if not os.path.isfile(script):
        raise RuntimeError("Phase 3.6.0 master orchestrator missing")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = "SHADOW_ONLY_NO_BROKER"
    env["PAPER_STRATEGY_VERSION"] = strategy_version
    env["STRATEGY_VERSION"] = strategy_version
    env["PHASE360_PORTFOLIO_ID"] = portfolio_id
    for phase in ("350", "351", "352", "353", "354", "355", "356"):
        env[f"PHASE{phase}_PORTFOLIO_ID"] = portfolio_id

    return subprocess.run(
        [sys.executable, script, "--approver", approver],
        env=env,
        text=True,
        capture_output=True,
        timeout=int(os.getenv("PHASE368_MASTER_TIMEOUT_SECONDS", "4800")),
        check=False,
    )

def persist(
    sb: Supabase,
    args: argparse.Namespace,
    state: str,
    pre: Dict[str, Any],
    master: Optional[Dict[str, Any]],
    executed: bool,
    exit_code: int,
    reasons: List[str],
    stdout_tail: str = "",
    stderr_tail: str = "",
) -> str:
    final_master_state = master_state(master)
    passed = state in {CONTROLLER_COMPLETED, CONTROLLER_COMPLETED_OBSERVATION}

    evidence = {
        "contract": CONTRACT,
        "controller_date": args.controller_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "controller_state": state,
        "preflight": pre,
        "master_cycle_state": final_master_state,
        "daily_paper_cycle_executed": executed,
        "master_exit_code": exit_code,
        "reason_codes": reasons,
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
    sha = stable_hash(evidence)

    payload = {
        "controller_date": args.controller_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "controller_state": state,
        "controller_passed": passed,
        "autonomous_daily_operations_authorized": bool(pre["authorized"]),
        "daily_paper_cycle_executed": executed,
        "activation_state": pre["activation_state"],
        "qualification_state": pre["qualification_state"],
        "runtime_supervision_state": pre["supervision_state"],
        "runtime_supervision_score": pre["supervision_score"],
        "master_cycle_state": final_master_state,
        "master_exit_code": exit_code,
        "safety_revocation_triggered": state in {CONTROLLER_BLOCKED, CONTROLLER_FAIL_CLOSED},
        "reason_codes": reasons,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": sha,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    sb.upsert("paper_daily_autonomous_controller_v92", payload, "portfolio_id,controller_date")

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["stdout_tail"] = stdout_tail[-4000:]
    audit["stderr_tail"] = stderr_tail[-4000:]
    audit["created_at"] = datetime.now(timezone.utc).isoformat()
    sb.request(
        "POST",
        "paper_daily_autonomous_controller_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )
    return sha

def print_summary(
    args: argparse.Namespace,
    state: str,
    pre: Dict[str, Any],
    master: Optional[Dict[str, Any]],
    executed: bool,
    reasons: List[str],
    sha: str,
) -> None:
    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.8")
    print()
    print("## Production Paper Daily Autonomous Operations Controller")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Controller Date: `{args.controller_date}`")
    print(f"- Controller State: **{state}**")
    print(f"- Qualification State: **{pre['qualification_state']}**")
    print(f"- Activation State: **{pre['activation_state']}**")
    print(f"- Runtime Supervision: **{pre['supervision_state']}**")
    print(f"- Runtime Supervision Score: **{pre['supervision_score']:.4f}**")
    print(f"- Daily Master Cycle: **{master_state(master)}**")
    print(f"- Autonomous Daily Operations Authorized: **{'YES' if pre['authorized'] else 'NO'}**")
    print(f"- Daily Paper Cycle Executed: **{'YES' if executed else 'NO'}**")
    print(f"- Safety Revocation Triggered: **{'YES' if state in {CONTROLLER_BLOCKED, CONTROLLER_FAIL_CLOSED} else 'NO'}**")
    print(f"- Final Controller Result: **{'PASS' if state in {CONTROLLER_COMPLETED, CONTROLLER_COMPLETED_OBSERVATION} else 'FAIL_CLOSED'}**")
    print()
    print("## Controller Reasons")
    print()
    for reason in reasons:
        print(f"- `{reason}`")
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
    print(f"- Evidence SHA256: `{sha}`")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--approver", default=os.getenv("PHASE368_APPROVER", "rchu9246"))
    parser.add_argument("--controller-date", default=str(date.today()))
    args = parser.parse_args()

    # Validate date early.
    date.fromisoformat(args.controller_date)
    if not args.approver.strip():
        raise RuntimeError("Approver must not be empty")

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

    supervision = latest(
        sb,
        "paper_runtime_supervision_state_v92",
        args.portfolio_id,
        "supervision_date",
    )
    pre = preflight(supervision)

    if not pre["authorized"]:
        reasons = ["PRECHECK_BLOCKED", pre["reason"]]
        sha = persist(
            sb, args, CONTROLLER_FAIL_CLOSED, pre, None, False, 0, reasons
        )
        print_summary(args, CONTROLLER_FAIL_CLOSED, pre, None, False, reasons, sha)
        return 2

    before_master = latest(sb, "paper_master_cycles_v92", args.portfolio_id, "cycle_date")

    proc = run_master(args.approver.strip(), args.portfolio_id, args.strategy_version)

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    after_master = latest(sb, "paper_master_cycles_v92", args.portfolio_id, "cycle_date")
    final_master = after_master or before_master
    final_master_state = master_state(final_master)

    if proc.returncode != 0:
        reasons = ["MASTER_ORCHESTRATOR_FAILED", f"MASTER_EXIT_CODE_{proc.returncode}"]
        sha = persist(
            sb,
            args,
            CONTROLLER_FAIL_CLOSED,
            pre,
            final_master,
            True,
            proc.returncode,
            reasons,
            proc.stdout,
            proc.stderr,
        )
        print_summary(args, CONTROLLER_FAIL_CLOSED, pre, final_master, True, reasons, sha)
        return proc.returncode if proc.returncode > 0 else 1

    if final_master_state not in PASS_MASTER_STATES:
        # Phase 3.6.0 historically persists final_state values; accept explicit
        # successful contract evidence when the subprocess passed.
        phase360_pass = "PHASE360 PASS:" in (proc.stdout or "")
        if not phase360_pass:
            reasons = ["MASTER_CANONICAL_STATE_NOT_PASS", final_master_state]
            sha = persist(
                sb,
                args,
                CONTROLLER_FAIL_CLOSED,
                pre,
                final_master,
                True,
                0,
                reasons,
                proc.stdout,
                proc.stderr,
            )
            print_summary(args, CONTROLLER_FAIL_CLOSED, pre, final_master, True, reasons, sha)
            return 3

    state = CONTROLLER_COMPLETED_OBSERVATION if pre["observation"] else CONTROLLER_COMPLETED
    reasons = [
        "AUTONOMOUS_PRECHECK_PASS",
        "DAILY_MASTER_ORCHESTRATOR_PASS",
        "DAILY_AUTONOMOUS_CONTROLLER_PASS",
    ]
    if pre["observation"]:
        reasons.append("AUTHORIZED_WITH_OBSERVATION")

    sha = persist(
        sb,
        args,
        state,
        pre,
        final_master,
        True,
        0,
        reasons,
        proc.stdout,
        proc.stderr,
    )
    print_summary(args, state, pre, final_master, True, reasons, sha)

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase368")
    os.makedirs(out_dir, exist_ok=True)
    evidence = {
        "contract": CONTRACT,
        "controller_state": state,
        "portfolio_id": args.portfolio_id,
        "controller_date": args.controller_date,
        "preflight": pre,
        "master_cycle_state": master_state(final_master),
        "reason_codes": reasons,
        "evidence_sha256": sha,
    }
    with open(
        os.path.join(out_dir, "daily_autonomous_controller_evidence.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE368_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.6.8 Supabase schema"

$sql = @'
begin;

create table if not exists public.paper_daily_autonomous_controller_v92 (
    id bigint generated by default as identity primary key,
    controller_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER',

    controller_state text not null,
    controller_passed boolean not null default false,
    autonomous_daily_operations_authorized boolean not null default false,
    daily_paper_cycle_executed boolean not null default false,

    activation_state text not null default 'UNKNOWN',
    qualification_state text not null default 'UNKNOWN',
    runtime_supervision_state text not null default 'UNKNOWN',
    runtime_supervision_score numeric not null default 0,
    master_cycle_state text not null default 'UNKNOWN',
    master_exit_code integer not null default 0,
    safety_revocation_triggered boolean not null default false,

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

    constraint ck_phase368_controller_state check (
        controller_state in (
            'COMPLETED',
            'COMPLETED_WITH_OBSERVATION',
            'BLOCKED',
            'FAILED',
            'FAIL_CLOSED'
        )
    ),
    constraint ck_phase368_paper_only check (paper_only = true),
    constraint ck_phase368_no_broker_api check (broker_api_used = false),
    constraint ck_phase368_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase368_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase368_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase368_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase368_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_daily_autonomous_controller_v92_portfolio_date
    on public.paper_daily_autonomous_controller_v92 (portfolio_id, controller_date);

create index if not exists ix_paper_daily_autonomous_controller_v92_state_date
    on public.paper_daily_autonomous_controller_v92 (controller_state, controller_date desc);

create table if not exists public.paper_daily_autonomous_controller_audit_v92 (
    id bigint generated by default as identity primary key,
    controller_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER',

    controller_state text not null,
    controller_passed boolean not null default false,
    autonomous_daily_operations_authorized boolean not null default false,
    daily_paper_cycle_executed boolean not null default false,

    activation_state text not null default 'UNKNOWN',
    qualification_state text not null default 'UNKNOWN',
    runtime_supervision_state text not null default 'UNKNOWN',
    runtime_supervision_score numeric not null default 0,
    master_cycle_state text not null default 'UNKNOWN',
    master_exit_code integer not null default 0,
    safety_revocation_triggered boolean not null default false,

    reason_codes jsonb not null default '[]'::jsonb,
    stdout_tail text not null default '',
    stderr_tail text not null default '',

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),

    constraint ck_phase368_audit_paper_only check (paper_only = true),
    constraint ck_phase368_audit_no_broker_api check (broker_api_used = false),
    constraint ck_phase368_audit_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase368_audit_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase368_audit_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase368_audit_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase368_audit_fail_closed check (fail_closed_policy = true)
);

create index if not exists ix_paper_daily_autonomous_controller_audit_v92_portfolio_created
    on public.paper_daily_autonomous_controller_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_daily_autonomous_controller_v92 enable row level security;
alter table public.paper_daily_autonomous_controller_audit_v92 enable row level security;

comment on table public.paper_daily_autonomous_controller_v92 is
'GPT Quant V9.2 Phase 3.6.8 daily autonomous Production Paper operations controller state. Paper-only and fail-closed.';

comment on table public.paper_daily_autonomous_controller_audit_v92 is
'GPT Quant V9.2 Phase 3.6.8 immutable-style daily autonomous controller audit ledger.';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.8 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.6.8 - Production Paper Daily Autonomous Operations Controller

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
      approver:
        description: Human approver/operator ID
        required: true
        default: rchu9246
        type: string
      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

  schedule:
    # 12:45 UTC = 20:45 Asia/Taipei, weekdays.
    # Runs after Phase 3.6.7 scheduled runtime supervision at 12:30 UTC.
    - cron: "45 12 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase368-production-paper-daily-autonomous-controller
  cancel-in-progress: false

jobs:
  daily-autonomous-controller:
    runs-on: ubuntu-latest
    timeout-minutes: 90

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      FINMIND_TOKEN: ${{ secrets.FINMIND_TOKEN }}

      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PHASE368_APPROVER: ${{ inputs.approver || 'rchu9246' }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE360_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE350_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE351_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE352_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE353_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE354_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE355_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE356_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE351_MIN_HISTORY: "5"
      PHASE353_BASE_RISK_BUDGET_PCT: "0.60"
      PHASE353_MAX_POSITION_PCT: "0.20"
      PHASE353_MAX_CANDIDATES: "3"
      PHASE353_ROUND_LOT: "1000"
      PHASE353_SCORE_THRESHOLD: "65"

      PHASE352_CAUTION_DRAWDOWN: "-0.05"
      PHASE352_REDUCE_DRAWDOWN: "-0.10"
      PHASE352_HALT_DRAWDOWN: "-0.15"
      PHASE352_CAUTION_DAILY_LOSS: "-0.025"
      PHASE352_HALT_DAILY_LOSS: "-0.05"
      PHASE352_MAX_EXPOSURE_CAUTION: "0.80"
      PHASE352_MAX_EXPOSURE_HALT: "0.95"
      PHASE352_MAX_CONCENTRATION_CAUTION: "0.35"
      PHASE352_MAX_CONCENTRATION_HALT: "0.50"
      PHASE352_CONSECUTIVE_LOSS_CAUTION: "3"
      PHASE352_CONSECUTIVE_LOSS_HALT: "5"

      PHASE348451_SCORE_THRESHOLD: "65"
      PHASE348451_MAX_CANDIDATES: "3"
      PHASE348451_MAX_ROWS_PER_TABLE: "5000"
      PHASE348_SCORE_THRESHOLD: "65"
      PHASE348_MAX_CANDIDATES: "3"
      PHASE348_INITIAL_CASH: "1000000"
      PHASE348_MAX_POSITION_PCT: "0.20"
      PHASE348_ROUND_LOT: "1000"
      PHASE349_INITIAL_CASH: "1000000"

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Install runtime dependencies
        run: python -m pip install --upgrade pip requests

      - name: Compile Phase 3.6.8
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py
          python -m py_compile automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py

      - name: Validate Phase 3.6.8 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          grep -q 'PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER' \
            automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py

          grep -q 'paper_runtime_supervision_state_v92' \
            automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py

          grep -q 'paper_master_cycles_v92' \
            automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py

          grep -q '"live_money_release_authorized": False' \
            automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py

          echo "Phase 3.6.8 autonomous controller safety contract: PASS"

      - name: Execute Phase 3.6.8 daily autonomous controller
        shell: bash
        run: |
          mkdir -p artifacts/phase368

          python automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            --approver "$PHASE368_APPROVER" \
            | tee artifacts/phase368/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase368/summary.md ]; then
            cat artifacts/phase368/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase368-daily-autonomous-controller-evidence
          path: artifacts/phase368/
          if-no-files-found: warn
          retention-days: 30
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
    Fail "Phase 3.6.8 Python compile failed."
}
Write-Host "Python compile: PASS" -ForegroundColor Green

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER",
    "paper_daily_autonomous_controller_v92",
    "paper_daily_autonomous_controller_audit_v92",
    "paper_runtime_supervision_state_v92",
    "paper_master_cycles_v92",
    "COMPLETED",
    "COMPLETED_WITH_OBSERVATION",
    "FAIL_CLOSED",
    "CONTINUE_ACTIVE",
    "CONTINUE_WITH_OBSERVATION",
    "DAILY_AUTONOMOUS_CONTROLLER_PASS"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.6.8 required contract token missing: $token"
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

Write-Host "Daily autonomous controller contract scan: PASS" -ForegroundColor Green
Write-Host "Runtime supervision authorization scan: PASS" -ForegroundColor Green
Write-Host "Phase 3.6.0 master integration scan: PASS" -ForegroundColor Green
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
        Write-Host "No staged Phase 3.6.8 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.6.8 production paper daily autonomous operations controller"
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
Write-Host "  automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py"
Write-Host "  supabase/PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase368-production-paper-daily-autonomous-operations-controller.yml"
Write-Host ""
Write-Host "Expected healthy result:" -ForegroundColor Cyan
Write-Host "  Controller State: COMPLETED"
Write-Host "  Qualification State: QUALIFIED"
Write-Host "  Activation State: ACTIVE"
Write-Host "  Runtime Supervision: CONTINUE_ACTIVE"
Write-Host "  Autonomous Daily Operations Authorized: YES"
Write-Host "  Daily Paper Cycle Executed: YES"
Write-Host "  Safety Revocation Triggered: NO"
Write-Host "  Final Controller Result: PASS"
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
Write-Host "  1) Run supabase/PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER.sql once."
Write-Host "  2) Commit and Push the generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.8 - Production Paper Daily Autonomous Operations Controller."
Write-Host "  4) Confirm Controller State=COMPLETED or COMPLETED_WITH_OBSERVATION."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
