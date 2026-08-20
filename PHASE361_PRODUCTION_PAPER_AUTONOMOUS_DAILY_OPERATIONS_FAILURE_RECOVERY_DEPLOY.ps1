#requires -Version 5.1
<#
PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.1 — Production Paper Autonomous Daily Operations + Failure Recovery

Purpose
-------
Turn Phase 3.6.0 into an autonomous daily production-paper operations layer with:
  - scheduled daily master-cycle execution;
  - persistent operations/recovery ledger;
  - bounded automatic retry;
  - idempotent recovery semantics;
  - explicit failed-stage capture;
  - artifact/evidence retention;
  - concurrency protection;
  - Python cache cleanup / .gitignore hardening;
  - fail-closed safety enforcement.

This remains PAPER-ONLY.
No broker integration is enabled by this package.

Created/overwritten
-------------------
  supabase/PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY.sql
  automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py
  .github/workflows/gpt-quant-v92-paper-trading-phase361-production-paper-autonomous-daily-operations-failure-recovery.yml

Updated
-------
  .gitignore
#>

param(
    [switch]$AutoGit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 120) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 120) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.6.1 Autonomous Daily Operations + Failure Recovery"

$repoRoot = $null
try {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repoRoot = $null
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    Fail "Run this deployment package inside the GPT Git repository."
}

Set-Location $repoRoot
Write-Host "Repository: $repoRoot" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py",
    ".github/workflows/gpt-quant-v92-paper-trading-phase360-production-paper-daily-master-orchestrator.yml",
    "supabase/PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required Phase 3.6.0 dependency missing: $item"
    }
}

$sqlTarget = "supabase/PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY.sql"
$pythonTarget = "automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase361-production-paper-autonomous-daily-operations-failure-recovery.yml"
$gitignoreTarget = ".gitignore"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase361-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget, $gitignoreTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Hardening .gitignore and cleaning Python cache"

if (-not (Test-Path $gitignoreTarget)) {
    New-Item -ItemType File -Path $gitignoreTarget | Out-Null
}

$gitignore = Get-Content -LiteralPath $gitignoreTarget -Raw -ErrorAction SilentlyContinue
if ($null -eq $gitignore) { $gitignore = "" }

$ignoreLines = @(
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/",
    ".mypy_cache/"
)

foreach ($line in $ignoreLines) {
    if (-not (($gitignore -split "`r?`n") -contains $line)) {
        Add-Content -LiteralPath $gitignoreTarget -Value $line -Encoding UTF8
        Write-Host "Added to .gitignore: $line" -ForegroundColor Green
    }
}

Get-ChildItem -Path $repoRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object {
        try {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
            Write-Host "Removed cache: $($_.FullName)" -ForegroundColor DarkGray
        } catch {
            Write-Host "Cache cleanup warning: $($_.FullName)" -ForegroundColor Yellow
        }
    }

Get-ChildItem -Path $repoRoot -Recurse -File -Include *.pyc,*.pyo -ErrorAction SilentlyContinue |
    ForEach-Object {
        try {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
        } catch {
            Write-Host "Bytecode cleanup warning: $($_.FullName)" -ForegroundColor Yellow
        }
    }

Section "Writing Phase 3.6.1 Supabase operations/recovery schema"

$sql = @'
begin;

create table if not exists public.paper_autonomous_operations_v92 (
    operation_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    operation_date date not null,

    operation_status text not null,
    recovery_state text not null,
    attempt_count integer not null default 1,
    max_attempts integer not null default 2,

    master_cycle_id text,
    master_final_state text,
    failed_stage text,
    failure_message text,

    zero_signal_valid boolean not null default false,
    zero_order_valid boolean not null default false,
    zero_fill_valid boolean not null default false,

    first_attempt_started_at timestamptz not null,
    last_attempt_started_at timestamptz not null,
    completed_at timestamptz,

    synthetic_market_data boolean not null default false,
    synthetic_signals boolean not null default false,
    fake_prices_allowed boolean not null default false,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_autonomous_operations_v92_portfolio_date
    on public.paper_autonomous_operations_v92 (portfolio_id, operation_date);

create table if not exists public.paper_operation_attempts_v92 (
    attempt_id text primary key,
    operation_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    operation_date date not null,

    attempt_number integer not null,
    attempt_status text not null,
    failed_stage text,
    failure_message text,

    master_cycle_id text,
    master_final_state text,

    started_at timestamptz not null,
    completed_at timestamptz not null,

    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_operation_attempts_v92_operation_attempt
    on public.paper_operation_attempts_v92 (operation_id, attempt_number);

alter table public.paper_autonomous_operations_v92 enable row level security;
alter table public.paper_operation_attempts_v92 enable row level security;

comment on table public.paper_autonomous_operations_v92 is
'GPT Quant V9.2 autonomous production-paper daily operations ledger with bounded recovery. No broker or real-money authority.';

comment on table public.paper_operation_attempts_v92 is
'GPT Quant V9.2 autonomous production-paper attempt/recovery audit trail.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.1 Python autonomous operations/recovery engine"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase361_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE361_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

MASTER = ROOT / "automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py"
MASTER_JSON = ROOT / "phase360_output/phase360_master_cycle.json"

OPERATIONS_TABLE = "paper_autonomous_operations_v92"
ATTEMPTS_TABLE = "paper_operation_attempts_v92"

RESULT_JSON = OUT / "phase361_autonomous_operation.json"
RESULT_MD = OUT / "phase361_autonomous_operation.md"

CONTRACT = "PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY"

VALID_MASTER_FINAL_STATES = {
    "DAILY_MASTER_CYCLE_COMPLETED",
    "PAPER_HALT_COMPLETED",
}

VALID_ZERO_RUNTIME_STATES = {
    "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS",
    "INSUFFICIENT_HISTORY_VALID_STATE",
    "ZERO_ORDER_VALID_STATE",
    "ZERO_FILL_VALID_STATE",
    "PAPER_HALT_ZERO_ORDERS",
    "PAPER_HALT_ZERO_SETTLEMENT",
    "ALREADY_SETTLED_IDEMPOTENT",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def supabase() -> tuple[str, dict[str, str]]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not base or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing")

    return base, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(table: str, params: list[tuple[str, str]]) -> list[dict[str, Any]]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:1000]}"
        )

    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"{table}: expected list response")

    return [x for x in data if isinstance(x, dict)]


def rest_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    if not rows:
        return

    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    response = requests.post(
        f"{base}/rest/v1/{quote(table, safe='')}",
        headers=headers,
        params={"on_conflict": on_conflict},
        data=json.dumps(rows, ensure_ascii=False, default=str),
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1400]}"
        )


def safety_env(approver: str) -> dict[str, str]:
    env = os.environ.copy()

    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE360_PORTFOLIO_ID"] = PORTFOLIO_ID
    env["PHASE360_APPROVER"] = approver

    return env


def infer_failed_stage(text: str) -> str | None:
    matches = re.findall(r"(phase3(?:50|51|52|53|54|55|56))", text.lower())
    if matches:
        return matches[-1]
    return None


def run_master(approver: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(MASTER), "--approver", approver],
        cwd=str(ROOT),
        env=safety_env(approver),
        text=True,
        capture_output=True,
    )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")

    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")

    return proc.returncode, stdout, stderr


def validate_master(payload: dict[str, Any]) -> None:
    if payload.get("status") != "PASS":
        raise RuntimeError("Phase 3.6.0 master status is not PASS")

    if payload.get("final_state") not in VALID_MASTER_FINAL_STATES:
        raise RuntimeError(
            f"Unexpected master final state: {payload.get('final_state')!r}"
        )

    stages = payload.get("stages")
    if not isinstance(stages, list) or len(stages) != 7:
        raise RuntimeError("Phase 3.6.0 did not report seven stages")

    if not all(x.get("status") == "PASS" for x in stages):
        raise RuntimeError("One or more Phase 3.6.0 stages did not PASS")

    for key in (
        "synthetic_market_data",
        "synthetic_signals",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    ):
        if payload.get(key) is not False:
            raise RuntimeError(
                f"Master safety violation: {key}={payload.get(key)!r}"
            )

    if payload.get("fail_closed_policy") is not True:
        raise RuntimeError("Master fail_closed_policy must remain enabled")


def operation_id(operation_date: str) -> str:
    return "P361O-" + stable_hash(
        {
            "portfolio_id": PORTFOLIO_ID,
            "strategy_version": STRATEGY,
            "operation_date": operation_date,
        }
    )[:28]


def persist_attempt(
    op_id: str,
    operation_date: str,
    attempt_number: int,
    status: str,
    started_at: str,
    completed_at: str,
    failed_stage: str | None,
    failure_message: str | None,
    master: dict[str, Any] | None,
) -> None:
    seed = {
        "operation_id": op_id,
        "attempt_number": attempt_number,
        "status": status,
        "failed_stage": failed_stage,
        "master_cycle_id": master.get("master_cycle_id") if master else None,
        "master_final_state": master.get("final_state") if master else None,
    }

    row = {
        "attempt_id": "P361A-" + stable_hash(seed)[:28],
        "operation_id": op_id,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "operation_date": operation_date,
        "attempt_number": attempt_number,
        "attempt_status": status,
        "failed_stage": failed_stage,
        "failure_message": failure_message,
        "master_cycle_id": master.get("master_cycle_id") if master else None,
        "master_final_state": master.get("final_state") if master else None,
        "started_at": started_at,
        "completed_at": completed_at,
        "evidence_sha256": stable_hash(seed),
    }

    rest_upsert(
        ATTEMPTS_TABLE,
        [row],
        "operation_id,attempt_number",
    )


def persist_operation(
    op_id: str,
    operation_date: str,
    first_started_at: str,
    last_started_at: str,
    completed_at: str | None,
    attempt_count: int,
    max_attempts: int,
    operation_status: str,
    recovery_state: str,
    failed_stage: str | None,
    failure_message: str | None,
    master: dict[str, Any] | None,
) -> dict[str, Any]:
    canonical_runtime_state = master.get("canonical_runtime_state") if master else None
    execution_state = master.get("execution_state") if master else None
    settlement_state = master.get("settlement_state") if master else None

    zero_signal_valid = canonical_runtime_state in VALID_ZERO_RUNTIME_STATES
    zero_order_valid = execution_state in VALID_ZERO_RUNTIME_STATES
    zero_fill_valid = settlement_state in VALID_ZERO_RUNTIME_STATES

    seed = {
        "operation_id": op_id,
        "attempt_count": attempt_count,
        "operation_status": operation_status,
        "recovery_state": recovery_state,
        "failed_stage": failed_stage,
        "master_cycle_id": master.get("master_cycle_id") if master else None,
        "master_final_state": master.get("final_state") if master else None,
    }

    row = {
        "operation_id": op_id,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "operation_date": operation_date,
        "operation_status": operation_status,
        "recovery_state": recovery_state,
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "master_cycle_id": master.get("master_cycle_id") if master else None,
        "master_final_state": master.get("final_state") if master else None,
        "failed_stage": failed_stage,
        "failure_message": failure_message,
        "zero_signal_valid": zero_signal_valid,
        "zero_order_valid": zero_order_valid,
        "zero_fill_valid": zero_fill_valid,
        "first_attempt_started_at": first_started_at,
        "last_attempt_started_at": last_started_at,
        "completed_at": completed_at,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": stable_hash(seed),
        "updated_at": now_iso(),
    }

    rest_upsert(
        OPERATIONS_TABLE,
        [row],
        "portfolio_id,operation_date",
    )

    rows = rest_get(
        OPERATIONS_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("operation_date", f"eq.{operation_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Autonomous operations persistence verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.6.1",
        "",
        "## Production Paper Autonomous Daily Operations + Failure Recovery",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Operation Date: `{result['operation_date']}`",
        f"- Operation Status: **{result['operation_status']}**",
        f"- Recovery State: **{result['recovery_state']}**",
        f"- Attempts: **{result['attempt_count']} / {result['max_attempts']}**",
        "",
        "### Master Cycle",
        "",
        f"- Master Cycle ID: `{result.get('master_cycle_id')}`",
        f"- Master Final State: **{result.get('master_final_state')}**",
        f"- Failed Stage: **{result.get('failed_stage') or 'NONE'}**",
        "",
        "### Valid Zero-Activity Semantics",
        "",
        f"- Zero Signal Valid: **{'YES' if result['zero_signal_valid'] else 'NO'}**",
        f"- Zero Order Valid: **{'YES' if result['zero_order_valid'] else 'NO'}**",
        f"- Zero Fill Valid: **{'YES' if result['zero_fill_valid'] else 'NO'}**",
        "",
        "### Safety Boundary",
        "",
        "- Synthetic market data: **DISABLED**",
        "- Synthetic signals: **DISABLED**",
        "- Fake prices: **DISABLED**",
        "- Broker API used: **NO**",
        "- Broker credentials used: **NO**",
        "- Broker order submission: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Live-money release authorized: **NO**",
        "- Fail-closed policy: **ENABLED**",
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    text = "\n".join(lines) + "\n"
    RESULT_MD.write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE361_APPROVER", "github-actions"),
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=int(os.getenv("PHASE361_MAX_ATTEMPTS", "2")),
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=int,
        default=int(os.getenv("PHASE361_RETRY_DELAY_SECONDS", "10")),
    )
    args = parser.parse_args()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    if args.max_attempts < 1 or args.max_attempts > 3:
        raise RuntimeError("max-attempts must be between 1 and 3")

    operation_date = today_utc()
    op_id = operation_id(operation_date)
    first_started_at = now_iso()

    final_master: dict[str, Any] | None = None
    last_error: str | None = None
    last_failed_stage: str | None = None
    last_started_at = first_started_at

    for attempt in range(1, args.max_attempts + 1):
        last_started_at = now_iso()
        print(
            f"\n>>> PHASE361 autonomous attempt {attempt}/{args.max_attempts}"
        )

        returncode, stdout, stderr = run_master(args.approver)

        master: dict[str, Any] | None = None

        if MASTER_JSON.exists():
            try:
                master = read_json(MASTER_JSON)
            except Exception:
                master = None

        if returncode == 0 and master is not None:
            try:
                validate_master(master)

                persist_attempt(
                    op_id=op_id,
                    operation_date=operation_date,
                    attempt_number=attempt,
                    status="PASS",
                    started_at=last_started_at,
                    completed_at=now_iso(),
                    failed_stage=None,
                    failure_message=None,
                    master=master,
                )

                final_master = master
                break

            except Exception as exc:
                last_error = str(exc)
                last_failed_stage = infer_failed_stage(
                    stdout + "\n" + stderr + "\n" + last_error
                )

        else:
            combined = stdout + "\n" + stderr
            last_error = (
                f"Phase 3.6.0 master process failed with exit code {returncode}"
            )
            last_failed_stage = infer_failed_stage(combined)

        persist_attempt(
            op_id=op_id,
            operation_date=operation_date,
            attempt_number=attempt,
            status="FAILED",
            started_at=last_started_at,
            completed_at=now_iso(),
            failed_stage=last_failed_stage,
            failure_message=last_error,
            master=master,
        )

        if attempt < args.max_attempts:
            print(
                f"Attempt {attempt} failed; bounded recovery retry will start "
                f"after {args.retry_delay_seconds}s."
            )
            time.sleep(args.retry_delay_seconds)

    if final_master is None:
        persisted = persist_operation(
            op_id=op_id,
            operation_date=operation_date,
            first_started_at=first_started_at,
            last_started_at=last_started_at,
            completed_at=now_iso(),
            attempt_count=args.max_attempts,
            max_attempts=args.max_attempts,
            operation_status="FAILED",
            recovery_state="RECOVERY_EXHAUSTED",
            failed_stage=last_failed_stage,
            failure_message=last_error,
            master=None,
        )

        result = {
            "version": "3.6.1",
            "status": "FAIL",
            "strategy_version": STRATEGY,
            "trading_mode": MODE,
            "contract": CONTRACT,
            "portfolio_id": PORTFOLIO_ID,
            "operation_id": persisted["operation_id"],
            "operation_date": str(persisted["operation_date"]),
            "operation_status": persisted["operation_status"],
            "recovery_state": persisted["recovery_state"],
            "attempt_count": int(persisted["attempt_count"]),
            "max_attempts": int(persisted["max_attempts"]),
            "master_cycle_id": None,
            "master_final_state": None,
            "failed_stage": persisted.get("failed_stage"),
            "failure_message": persisted.get("failure_message"),
            "zero_signal_valid": False,
            "zero_order_valid": False,
            "zero_fill_valid": False,
            "synthetic_market_data": False,
            "synthetic_signals": False,
            "fake_prices_allowed": False,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "evidence_sha256": persisted["evidence_sha256"],
        }

        write_json(RESULT_JSON, result)
        write_summary(result)

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    attempt_count = 0
    attempts = rest_get(
        ATTEMPTS_TABLE,
        [
            ("select", "attempt_number"),
            ("operation_id", f"eq.{op_id}"),
            ("order", "attempt_number.desc"),
            ("limit", "1"),
        ],
    )
    if attempts:
        attempt_count = int(attempts[0]["attempt_number"])

    recovery_state = (
        "NOT_REQUIRED"
        if attempt_count <= 1
        else "RECOVERED_AFTER_RETRY"
    )

    persisted = persist_operation(
        op_id=op_id,
        operation_date=operation_date,
        first_started_at=first_started_at,
        last_started_at=last_started_at,
        completed_at=now_iso(),
        attempt_count=attempt_count,
        max_attempts=args.max_attempts,
        operation_status="PASS",
        recovery_state=recovery_state,
        failed_stage=None,
        failure_message=None,
        master=final_master,
    )

    result = {
        "version": "3.6.1",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "operation_id": persisted["operation_id"],
        "operation_date": str(persisted["operation_date"]),
        "operation_status": persisted["operation_status"],
        "recovery_state": persisted["recovery_state"],
        "attempt_count": int(persisted["attempt_count"]),
        "max_attempts": int(persisted["max_attempts"]),
        "master_cycle_id": persisted.get("master_cycle_id"),
        "master_final_state": persisted.get("master_final_state"),
        "failed_stage": persisted.get("failed_stage"),
        "failure_message": persisted.get("failure_message"),
        "zero_signal_valid": bool(persisted["zero_signal_valid"]),
        "zero_order_valid": bool(persisted["zero_order_valid"]),
        "zero_fill_valid": bool(persisted["zero_fill_valid"]),
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": persisted["evidence_sha256"],
    }

    write_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE361 PASS: autonomous production-paper operation completed. "
        f"recovery={result['recovery_state']}, "
        f"attempts={result['attempt_count']}, "
        f"master_state={result['master_final_state']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.6.1 GitHub Actions autonomous workflow"

$workflow = @'
name: GPT Quant Phase 3.6.1 - Production Paper Autonomous Daily Operations Failure Recovery

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
        default: github-actions
        type: string

      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

      max_attempts:
        description: Maximum bounded recovery attempts
        required: true
        default: "2"
        type: string

  schedule:
    - cron: "45 10 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase361-production-paper-autonomous-daily
  cancel-in-progress: false

jobs:
  autonomous-daily-operations:
    runs-on: ubuntu-latest
    timeout-minutes: 120

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      FINMIND_TOKEN: ${{ secrets.FINMIND_TOKEN }}

      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}

      PHASE361_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE360_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE361_APPROVER: ${{ inputs.approver || 'github-actions' }}
      PHASE361_MAX_ATTEMPTS: ${{ inputs.max_attempts || '2' }}
      PHASE361_RETRY_DELAY_SECONDS: "10"

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
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependencies
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.6.1 autonomous safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py
          test -f automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py
          test -f supabase/PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY.sql

          grep -q 'PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY' \
            automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py

          grep -q 'RECOVERY_EXHAUSTED' \
            automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py

          grep -q 'RECOVERED_AFTER_RETRY' \
            automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py

          echo "Phase 3.6.1 autonomous safety contract: PASS"

      - name: Execute Phase 3.6.1 autonomous daily operation
        shell: bash
        run: |
          set -euo pipefail

          APPROVER="${{ inputs.approver }}"
          if [ -z "${APPROVER}" ]; then
            APPROVER="github-actions"
          fi

          MAX_ATTEMPTS="${{ inputs.max_attempts }}"
          if [ -z "${MAX_ATTEMPTS}" ]; then
            MAX_ATTEMPTS="2"
          fi

          python automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py \
            --approver "${APPROVER}" \
            --max-attempts "${MAX_ATTEMPTS}" \
            --retry-delay-seconds 10

      - name: Validate Phase 3.6.1 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase361_output/phase361_autonomous_operation.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase361_output/phase361_autonomous_operation.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.6.1", data
          assert data["status"] == "PASS", data
          assert data["operation_status"] == "PASS", data

          assert data["recovery_state"] in {
              "NOT_REQUIRED",
              "RECOVERED_AFTER_RETRY",
          }, data

          assert 1 <= data["attempt_count"] <= data["max_attempts"], data

          assert data["master_final_state"] in {
              "DAILY_MASTER_CYCLE_COMPLETED",
              "PAPER_HALT_COMPLETED",
          }, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          print("Phase 3.6.1 output validation: PASS")
          PY

      - name: Upload Phase 3.6.1 autonomous evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase361-production-paper-autonomous-daily-${{ github.run_id }}
          path: |
            phase350_output/
            phase351_output/
            phase352_output/
            phase353_output/
            phase354_output/
            phase355_output/
            phase360_output/
            phase361_output/
          if-no-files-found: warn
          retention-days: 90
'@

Set-Content -LiteralPath $workflowTarget -Value $workflow -Encoding UTF8
Write-Host "Wrote: $workflowTarget" -ForegroundColor Green

Section "Static validation"

$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} else {
    Fail "Python was not found in PATH."
}

if ($pythonCmd -eq "py") {
    & py -3 -m py_compile $pythonTarget
} else {
    & python -m py_compile $pythonTarget
}

if ($LASTEXITCODE -ne 0) {
    Fail "Python compile validation failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$source = Get-Content -LiteralPath $pythonTarget -Raw
$needles = @(
    'PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY',
    'paper_autonomous_operations_v92',
    'paper_operation_attempts_v92',
    'RECOVERY_EXHAUSTED',
    'RECOVERED_AFTER_RETRY',
    'NOT_REQUIRED',
    'VALID_ZERO_RUNTIME_STATES',
    '"synthetic_market_data": False',
    '"synthetic_signals": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.6.1 token missing: $needle"
    }
}

Write-Host "Phase 3.6.1 autonomous/recovery contract scan: PASS" -ForegroundColor Green

$gitignoreNow = Get-Content -LiteralPath $gitignoreTarget -Raw
foreach ($requiredIgnore in @("__pycache__/", "*.pyc", "*.pyo")) {
    if (-not $gitignoreNow.Contains($requiredIgnore)) {
        Fail ".gitignore hardening missing required rule: $requiredIgnore"
    }
}

Write-Host ".gitignore Python-cache hardening: PASS" -ForegroundColor Green

Section "Git status"
& git status --short

if ($AutoGit) {
    Section "Optional AutoGit"

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    & git add -- $sqlTarget $pythonTarget $workflowTarget $gitignoreTarget
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed"
    }

    $pending = (& git diff --cached --name-only)

    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged Phase 3.6.1 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.6.1 autonomous daily operations failure recovery"
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

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $sqlTarget"
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host "  $gitignoreTarget"
Write-Host ""

Write-Host "Autonomous operations behavior:" -ForegroundColor Cyan
Write-Host "  Phase 3.6.0 Master"
Write-Host "      -> PASS: persist autonomous operation PASS"
Write-Host "      -> FAIL: bounded automatic retry"
Write-Host "      -> recovered: RECOVERED_AFTER_RETRY"
Write-Host "      -> exhausted: RECOVERY_EXHAUSTED + fail-closed"
Write-Host ""

Write-Host "Valid no-trade semantics:" -ForegroundColor Cyan
Write-Host "  0 eligible signals = valid"
Write-Host "  0 orders           = valid"
Write-Host "  0 fills            = valid"
Write-Host ""

Write-Host "Supabase SQL required before first autonomous run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY.sql"
Write-Host ""

Write-Host "Autonomous schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 45 10 * * 1-5"
Write-Host "  10:45 UTC = 18:45 Taiwan time, weekdays"
Write-Host ""

Write-Host "Hard safety locks:" -ForegroundColor Yellow
Write-Host "  Synthetic market data: DISABLED"
Write-Host "  Synthetic signals: DISABLED"
Write-Host "  Fake prices: DISABLED"
Write-Host "  Broker API used: NO"
Write-Host "  Broker credentials used: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host "  Fail-closed: ENABLED"
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run Phase 3.6.1 Supabase SQL once."
Write-Host "  2) Commit/Push Phase 3.6.1 files (or deploy with -AutoGit)."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.1 - Production Paper Autonomous Daily Operations Failure Recovery."
Write-Host "  4) Confirm Operation Status=PASS and Recovery State=NOT_REQUIRED or RECOVERED_AFTER_RETRY."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
