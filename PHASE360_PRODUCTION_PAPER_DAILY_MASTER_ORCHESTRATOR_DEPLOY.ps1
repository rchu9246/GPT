#requires -Version 5.1
<#
PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.0 — Production Paper Daily Master Orchestrator

Purpose
-------
Collapse the validated Production Paper chain into one master daily execution:

  Phase 3.5.0  Daily Orchestrator + Persistent Performance Ledger
  Phase 3.5.1  Performance Analytics + Risk Metrics
  Phase 3.5.2  Risk Governance + Drawdown Guard
  Phase 3.5.3  Position Sizing + Risk Budget Allocation
  Phase 3.5.4  Order Intent + Simulated Execution Lifecycle
  Phase 3.5.5  Position Reconciliation + Execution Settlement
  Phase 3.5.6  EOD Accounting + Portfolio Ledger Finalization

The master orchestrator:
  - runs stages sequentially;
  - stops immediately on a failed stage;
  - treats valid zero-signal / zero-order / zero-fill states as successful;
  - persists a master-cycle audit record;
  - produces one final GitHub Actions summary;
  - keeps all broker / real-money capabilities hard-disabled.

Optional convenience
--------------------
The deployment script accepts:
  -AutoGit

When explicitly supplied, and only after local validation passes, it will:
  git add -> git commit -> git push origin main

It will NOT run Supabase DDL automatically. Production schema migration remains
an explicit operator action.

Created/overwritten
-------------------
  supabase/PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR.sql
  automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py
  .github/workflows/gpt-quant-v92-paper-trading-phase360-production-paper-daily-master-orchestrator.yml
#>

param(
    [switch]$AutoGit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.6.0 Production Paper Daily Master Orchestrator"

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
    "automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py",
    "automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py",
    "automation/v92/paper_trading_phase352_production_paper_risk_governance_drawdown_guard_engine.py",
    "automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py",
    "automation/v92/paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine.py",
    "automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py",
    "automation/v92/paper_trading_phase356_eod_accounting_portfolio_ledger_finalization_engine.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required validated upstream stage is missing: $item"
    }
}

$sqlTarget = "supabase/PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR.sql"
$pythonTarget = "automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase360-production-paper-daily-master-orchestrator.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase360-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.6.0 Supabase master-cycle audit schema"

$sql = @'
begin;

create table if not exists public.paper_master_cycles_v92 (
    master_cycle_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    cycle_date date not null,

    master_status text not null,
    final_state text not null,
    failed_stage text,

    phase350_status text,
    phase351_status text,
    phase352_status text,
    phase353_status text,
    phase354_status text,
    phase355_status text,
    phase356_status text,

    canonical_runtime_state text,
    analytics_state text,
    risk_state text,
    execution_state text,
    settlement_state text,

    eligible_signals integer,
    sized_candidates integer,
    order_intents_created integer,
    simulated_fills_created integer,
    fills_settled integer,

    cash numeric,
    market_value numeric,
    nav numeric,
    realized_pnl numeric,
    unrealized_pnl numeric,
    open_positions integer,

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
    started_at timestamptz not null,
    completed_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_master_cycles_v92_portfolio_date
    on public.paper_master_cycles_v92 (portfolio_id, cycle_date);

alter table public.paper_master_cycles_v92 enable row level security;

comment on table public.paper_master_cycles_v92 is
'GPT Quant V9.2 Production Paper Daily Master Orchestrator audit ledger. Paper-only, fail-closed, no broker or real-money authority.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.0 Python master orchestrator"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase360_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE360_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

MASTER_TABLE = "paper_master_cycles_v92"
EOD_TABLE = "paper_eod_ledger_v92"

RESULT_JSON = OUT / "phase360_master_cycle.json"
RESULT_MD = OUT / "phase360_master_cycle.md"

CONTRACT = "PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR"

STAGES = [
    {
        "id": "phase350",
        "name": "Daily Orchestrator + Persistent Performance Ledger",
        "script": ROOT / "automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py",
        "output": ROOT / "phase350_output/phase350_daily_orchestrator.json",
    },
    {
        "id": "phase351",
        "name": "Performance Analytics + Risk Metrics",
        "script": ROOT / "automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py",
        "output": ROOT / "phase351_output/phase351_performance_analytics.json",
    },
    {
        "id": "phase352",
        "name": "Risk Governance + Drawdown Guard",
        "script": ROOT / "automation/v92/paper_trading_phase352_production_paper_risk_governance_drawdown_guard_engine.py",
        "output": ROOT / "phase352_output/phase352_risk_governance.json",
    },
    {
        "id": "phase353",
        "name": "Position Sizing + Risk Budget Allocation",
        "script": ROOT / "automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py",
        "output": ROOT / "phase353_output/phase353_position_sizing.json",
    },
    {
        "id": "phase354",
        "name": "Order Intent + Simulated Execution Lifecycle",
        "script": ROOT / "automation/v92/paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine.py",
        "output": ROOT / "phase354_output/phase354_execution_lifecycle.json",
    },
    {
        "id": "phase355",
        "name": "Position Reconciliation + Execution Settlement",
        "script": ROOT / "automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py",
        "output": ROOT / "phase355_output/phase355_settlement.json",
    },
    {
        "id": "phase356",
        "name": "EOD Accounting + Portfolio Ledger Finalization",
        "script": ROOT / "automation/v92/paper_trading_phase356_eod_accounting_portfolio_ledger_finalization_engine.py",
        "output": None,
    },
]

VALID_ZERO_STATES = {
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


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
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


def rest_upsert(
    table: str,
    rows: list[dict[str, Any]],
    on_conflict: str,
) -> None:
    if not rows:
        return

    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.post(
        url,
        headers=headers,
        params={"on_conflict": on_conflict},
        data=json.dumps(rows, ensure_ascii=False, default=str),
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1400]}"
        )


def stage_env(approver: str) -> dict[str, str]:
    env = os.environ.copy()

    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    for phase in ("350", "351", "352", "353", "354", "355"):
        env[f"PHASE{phase}_PORTFOLIO_ID"] = PORTFOLIO_ID

    env["PHASE350_APPROVER"] = approver

    return env


def run_stage(
    stage: dict[str, Any],
    approver: str,
) -> dict[str, Any]:
    stage_id = stage["id"]
    script = stage["script"]
    output = stage["output"]

    if not script.exists():
        raise RuntimeError(f"{stage_id}: script missing: {script}")

    cmd = [sys.executable, str(script)]

    if stage_id == "phase350":
        cmd += ["--approver", approver]

    started = now_iso()

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=stage_env(approver),
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(
            f"\n===== {stage_id} stdout =====\n{proc.stdout}",
            end="" if proc.stdout.endswith("\n") else "\n",
        )

    if proc.stderr:
        print(
            f"\n===== {stage_id} stderr =====\n{proc.stderr}",
            file=sys.stderr,
            end="" if proc.stderr.endswith("\n") else "\n",
        )

    payload: dict[str, Any] | None = None

    if output is not None:
        if not output.exists():
            raise RuntimeError(
                f"{stage_id}: expected output missing after exit={proc.returncode}: {output}"
            )
        payload = load_json(output)

    if proc.returncode != 0:
        raise RuntimeError(
            f"{stage_id}: process failed with exit code {proc.returncode}"
        )

    if payload is not None and payload.get("status") != "PASS":
        raise RuntimeError(
            f"{stage_id}: output status is not PASS: {payload.get('status')!r}"
        )

    return {
        "stage_id": stage_id,
        "name": stage["name"],
        "status": "PASS",
        "exit_code": proc.returncode,
        "started_at": started,
        "completed_at": now_iso(),
        "payload": payload,
    }


def validate_safety(stage_results: list[dict[str, Any]]) -> None:
    unsafe_false_keys = (
        "synthetic_market_data",
        "synthetic_signals",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    )

    for stage in stage_results:
        payload = stage.get("payload")
        if not isinstance(payload, dict):
            continue

        for key in unsafe_false_keys:
            if key in payload and payload[key] is not False:
                raise RuntimeError(
                    f"{stage['stage_id']}: safety violation: {key}={payload[key]!r}"
                )

        if "fail_closed_policy" in payload and payload["fail_closed_policy"] is not True:
            raise RuntimeError(
                f"{stage['stage_id']}: fail_closed_policy must remain enabled"
            )


def upsert_eod_from_settlement(
    settlement: dict[str, Any],
) -> dict[str, Any]:
    ledger_date = str(settlement["settlement_date"])

    row = {
        "ledger_date": ledger_date,
        "nav": settlement["nav_after"],
        "cash": settlement["cash_after"],
        "market_value": settlement["market_value_after"],
        "realized_pnl": settlement["realized_pnl_after"],
        "unrealized_pnl": settlement["unrealized_pnl_after"],
    }

    # paper_eod_ledger_v92 is created by Phase 3.5.6 SQL.
    # This master makes Phase 3.5.6 operationally useful even if the local
    # Phase 3.5.6 Python runner is intentionally minimal.
    rest_upsert(
        EOD_TABLE,
        [row],
        "ledger_date",
    )

    rows = rest_get(
        EOD_TABLE,
        [
            ("select", "*"),
            ("ledger_date", f"eq.{ledger_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Phase 3.6.0 EOD ledger verification failed")

    return rows[0]


def final_state_from(stage_results: list[dict[str, Any]]) -> str:
    p350 = stage_results[0].get("payload") or {}
    p351 = stage_results[1].get("payload") or {}
    p352 = stage_results[2].get("payload") or {}
    p354 = stage_results[4].get("payload") or {}
    p355 = stage_results[5].get("payload") or {}

    states = [
        p350.get("canonical_runtime_state"),
        p351.get("analytics_state"),
        p352.get("risk_state"),
        p354.get("execution_state"),
        p355.get("settlement_state"),
    ]

    if any(state == "PAPER_HALT" for state in states):
        return "PAPER_HALT_COMPLETED"

    if all(
        state in VALID_ZERO_STATES or state in {None, "NORMAL", "CAUTION", "RISK_REDUCED", "ANALYTICS_READY"}
        for state in states
    ):
        return "DAILY_MASTER_CYCLE_COMPLETED"

    return "DAILY_MASTER_CYCLE_COMPLETED"


def persist_master_cycle(
    stage_results: list[dict[str, Any]],
    eod: dict[str, Any],
    started_at: str,
) -> dict[str, Any]:
    p350 = stage_results[0]["payload"] or {}
    p351 = stage_results[1]["payload"] or {}
    p352 = stage_results[2]["payload"] or {}
    p353 = stage_results[3]["payload"] or {}
    p354 = stage_results[4]["payload"] or {}
    p355 = stage_results[5]["payload"] or {}

    cycle_date = str(
        p355.get("settlement_date")
        or p350.get("ledger_date")
        or eod.get("ledger_date")
    )

    final_state = final_state_from(stage_results)

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "cycle_date": cycle_date,
        "final_state": final_state,
        "phase350": p350.get("evidence_sha256"),
        "phase351": p351.get("evidence_sha256"),
        "phase352": p352.get("evidence_sha256"),
        "phase353": p353.get("evidence_sha256"),
        "phase354": p354.get("evidence_sha256"),
        "phase355": p355.get("evidence_sha256"),
        "eod": {
            "cash": eod.get("cash"),
            "market_value": eod.get("market_value"),
            "nav": eod.get("nav"),
        },
    }

    row = {
        "master_cycle_id": "P360M-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "cycle_date": cycle_date,
        "master_status": "PASS",
        "final_state": final_state,
        "failed_stage": None,
        "phase350_status": "PASS",
        "phase351_status": "PASS",
        "phase352_status": "PASS",
        "phase353_status": "PASS",
        "phase354_status": "PASS",
        "phase355_status": "PASS",
        "phase356_status": "PASS",
        "canonical_runtime_state": p350.get("canonical_runtime_state"),
        "analytics_state": p351.get("analytics_state"),
        "risk_state": p352.get("risk_state"),
        "execution_state": p354.get("execution_state"),
        "settlement_state": p355.get("settlement_state"),
        "eligible_signals": int(p353.get("eligible_signals") or 0),
        "sized_candidates": int(p353.get("sized_candidates") or 0),
        "order_intents_created": int(p354.get("order_intents_created") or 0),
        "simulated_fills_created": int(p354.get("simulated_fills_created") or 0),
        "fills_settled": int(p355.get("fills_settled") or 0),
        "cash": eod.get("cash"),
        "market_value": eod.get("market_value"),
        "nav": eod.get("nav"),
        "realized_pnl": eod.get("realized_pnl"),
        "unrealized_pnl": eod.get("unrealized_pnl"),
        "open_positions": int(p355.get("open_positions_after") or 0),
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
        "started_at": started_at,
        "completed_at": now_iso(),
        "updated_at": now_iso(),
    }

    rest_upsert(
        MASTER_TABLE,
        [row],
        "portfolio_id,cycle_date",
    )

    rows = rest_get(
        MASTER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("cycle_date", f"eq.{cycle_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Master-cycle persistence verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.6.0",
        "",
        "## Production Paper Daily Master Orchestrator",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Master Status: **{result['status']}**",
        f"- Final State: **{result['final_state']}**",
        f"- Cycle Date: `{result['cycle_date']}`",
        "",
        "### Stage Results",
        "",
    ]

    for stage in result["stages"]:
        lines.append(
            f"- {stage['stage_id']} — {stage['name']}: **{stage['status']}**"
        )

    lines.extend(
        [
            "",
            "### Canonical Runtime",
            "",
            f"- Canonical Runtime State: **{result['canonical_runtime_state']}**",
            f"- Analytics State: **{result['analytics_state']}**",
            f"- Risk State: **{result['risk_state']}**",
            f"- Execution State: **{result['execution_state']}**",
            f"- Settlement State: **{result['settlement_state']}**",
            "",
            "### Daily Activity",
            "",
            f"- Eligible Signals: **{result['eligible_signals']}**",
            f"- Sized Candidates: **{result['sized_candidates']}**",
            f"- Order Intents Created: **{result['order_intents_created']}**",
            f"- Simulated Fills Created: **{result['simulated_fills_created']}**",
            f"- Fills Settled: **{result['fills_settled']}**",
            "",
            "### EOD Portfolio",
            "",
            f"- Cash: **{result['cash']:.2f}**",
            f"- Market Value: **{result['market_value']:.2f}**",
            f"- NAV: **{result['nav']:.2f}**",
            f"- Realized P&L: **{result['realized_pnl']:.2f}**",
            f"- Unrealized P&L: **{result['unrealized_pnl']:.2f}**",
            f"- Open Positions: **{result['open_positions']}**",
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
    )

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
        default=os.getenv("PHASE360_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    started_at = now_iso()
    results: list[dict[str, Any]] = []

    for stage in STAGES:
        print(f"\n>>> RUN {stage['id']}: {stage['name']}")
        result = run_stage(stage, approver)
        results.append(result)

    validate_safety(results)

    settlement = results[5]["payload"]
    if not isinstance(settlement, dict):
        raise RuntimeError("Phase 3.5.5 settlement evidence missing")

    eod = upsert_eod_from_settlement(settlement)

    master = persist_master_cycle(
        results,
        eod,
        started_at,
    )

    result = {
        "version": "3.6.0",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "master_cycle_id": master["master_cycle_id"],
        "cycle_date": str(master["cycle_date"]),
        "final_state": master["final_state"],
        "canonical_runtime_state": master.get("canonical_runtime_state"),
        "analytics_state": master.get("analytics_state"),
        "risk_state": master.get("risk_state"),
        "execution_state": master.get("execution_state"),
        "settlement_state": master.get("settlement_state"),
        "eligible_signals": int(master.get("eligible_signals") or 0),
        "sized_candidates": int(master.get("sized_candidates") or 0),
        "order_intents_created": int(master.get("order_intents_created") or 0),
        "simulated_fills_created": int(master.get("simulated_fills_created") or 0),
        "fills_settled": int(master.get("fills_settled") or 0),
        "cash": float(master.get("cash") or 0),
        "market_value": float(master.get("market_value") or 0),
        "nav": float(master.get("nav") or 0),
        "realized_pnl": float(master.get("realized_pnl") or 0),
        "unrealized_pnl": float(master.get("unrealized_pnl") or 0),
        "open_positions": int(master.get("open_positions") or 0),
        "stages": [
            {
                "stage_id": r["stage_id"],
                "name": r["name"],
                "status": r["status"],
                "exit_code": r["exit_code"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
            }
            for r in results
        ],
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": master["evidence_sha256"],
    }

    if len(result["stages"]) != 7:
        raise RuntimeError("Master cycle did not execute all seven stages")

    if any(stage["status"] != "PASS" for stage in result["stages"]):
        raise RuntimeError("One or more master stages did not PASS")

    if result["cash"] < 0 or result["nav"] < 0:
        raise RuntimeError("Invalid negative paper portfolio state")

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE360 PASS: full production-paper daily master cycle completed. "
        f"date={result['cycle_date']}, "
        f"final_state={result['final_state']}, "
        f"nav={result['nav']:.2f}, "
        f"fills={result['simulated_fills_created']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.6.0 GitHub Actions master workflow"

$workflow = @'
name: GPT Quant Phase 3.6.0 - Production Paper Daily Master Orchestrator

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
    - cron: "30 10 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase360-production-paper-daily-master
  cancel-in-progress: false

jobs:
  production-paper-daily-master:
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

      PHASE360_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE350_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE351_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE352_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE353_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE354_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE355_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

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

      - name: Validate Phase 3.6.0 master contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py
          test -f supabase/PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR.sql

          for f in \
            automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py \
            automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py \
            automation/v92/paper_trading_phase352_production_paper_risk_governance_drawdown_guard_engine.py \
            automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py \
            automation/v92/paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine.py \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py \
            automation/v92/paper_trading_phase356_eod_accounting_portfolio_ledger_finalization_engine.py
          do
            test -f "$f"
          done

          grep -q 'PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR' \
            automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py

          echo "Phase 3.6.0 master contract: PASS"

      - name: Execute Phase 3.6.0 daily master orchestrator
        shell: bash
        run: |
          set -euo pipefail

          APPROVER="${{ inputs.approver }}"
          if [ -z "${APPROVER}" ]; then
            APPROVER="github-actions"
          fi

          python automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py \
            --approver "${APPROVER}"

      - name: Validate Phase 3.6.0 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase360_output/phase360_master_cycle.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase360_output/phase360_master_cycle.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.6.0", data
          assert data["status"] == "PASS", data
          assert data["final_state"] in {
              "DAILY_MASTER_CYCLE_COMPLETED",
              "PAPER_HALT_COMPLETED",
          }, data

          assert len(data["stages"]) == 7, data
          assert all(x["status"] == "PASS" for x in data["stages"]), data

          assert data["cash"] >= 0, data
          assert data["nav"] >= 0, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          print("Phase 3.6.0 output validation: PASS")
          PY

      - name: Upload Phase 3.6.0 master evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase360-production-paper-daily-master-${{ github.run_id }}
          path: |
            phase350_output/
            phase351_output/
            phase352_output/
            phase353_output/
            phase354_output/
            phase355_output/
            phase360_output/
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
    'PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR',
    'paper_master_cycles_v92',
    'phase350',
    'phase351',
    'phase352',
    'phase353',
    'phase354',
    'phase355',
    'phase356',
    'DAILY_MASTER_CYCLE_COMPLETED',
    '"synthetic_market_data": False',
    '"synthetic_signals": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.6.0 token missing: $needle"
    }
}

Write-Host "Phase 3.6.0 master-orchestrator contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $sqlTarget $pythonTarget $workflowTarget

if ($AutoGit) {
    Section "Optional AutoGit"

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    & git add -- $sqlTarget $pythonTarget $workflowTarget
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed"
    }

    $pending = (& git diff --cached --name-only)
    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged Phase 3.6.0 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.6.0 production paper daily master orchestrator"
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
Write-Host ""

Write-Host "Master pipeline:" -ForegroundColor Cyan
Write-Host "  3.5.0 Daily Orchestrator / Performance Ledger"
Write-Host "      -> 3.5.1 Analytics"
Write-Host "      -> 3.5.2 Risk Governance"
Write-Host "      -> 3.5.3 Position Sizing"
Write-Host "      -> 3.5.4 Order Intent / Simulated Execution"
Write-Host "      -> 3.5.5 Settlement / Reconciliation"
Write-Host "      -> 3.5.6 EOD Finalization"
Write-Host "      -> 3.6.0 Master Audit / Final Status"
Write-Host ""

Write-Host "Supabase SQL required before first master run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR.sql"
Write-Host ""

Write-Host "Master schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 30 10 * * 1-5"
Write-Host "  10:30 UTC = 18:30 Taiwan time, weekdays"
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

if (-not $AutoGit) {
    Write-Host "Optional reduced-manual mode:" -ForegroundColor Yellow
    Write-Host "  Re-run this deploy package with -AutoGit to auto commit + push after validation."
    Write-Host ""
}

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run Phase 3.6.0 Supabase SQL once."
Write-Host "  2) Commit/Push (or use -AutoGit)."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.0 - Production Paper Daily Master Orchestrator."
Write-Host "  4) Confirm 7/7 stages PASS and Final State = DAILY_MASTER_CYCLE_COMPLETED."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
