#requires -Version 5.1
<#
PHASE350_PRODUCTION_PAPER_DAILY_ORCHESTRATOR_PERSISTENT_PERFORMANCE_LEDGER_DEPLOY.ps1

GPT Quant V9.2
Phase 3.5.0 — Production Paper Daily Orchestrator + Persistent Performance Ledger

Purpose
-------
Create the first long-running Production Paper daily master cycle.

This phase chains the already validated production-paper runtime into a single
daily orchestrator and persists one performance-ledger row per trading day.

Daily orchestration:
  1) Phase 3.4.8.4.6 Daily Production Paper Cycle
  2) Phase 3.4.9 Persistent Paper Portfolio Lifecycle + MTM
  3) Daily performance ledger computation
  4) Idempotent Supabase persistence
  5) GitHub Actions job summary + evidence artifact

Performance ledger metrics:
  - cash
  - market value
  - NAV
  - realized P&L
  - unrealized P&L
  - daily return
  - cumulative return
  - high-water mark
  - drawdown
  - open positions
  - eligible signals
  - fills applied
  - runtime state
  - evidence SHA256

Hard safety locks:
  - Synthetic market data: DISABLED
  - Synthetic signals: DISABLED
  - Fake prices: DISABLED
  - Broker API: NO
  - Broker credentials: NO
  - Broker order submission: DISABLED
  - Real-money trading: DISABLED
  - Live-money release: NO
  - Fail-closed: ENABLED

Created/overwritten
-------------------
  supabase/PHASE350_PRODUCTION_PAPER_PERFORMANCE_LEDGER.sql
  automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py
  .github/workflows/gpt-quant-v92-paper-trading-phase350-production-paper-daily-orchestrator-persistent-performance-ledger.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 112) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 112) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.5.0 Production Paper Daily Orchestrator"

$repoRoot = $null
try {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repoRoot = $null
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    Fail "Run this script inside the GPT Git repository."
}

Set-Location $repoRoot
Write-Host "Repository: $repoRoot" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py",
    "automation/v92/paper_trading_phase349_production_paper_portfolio_lifecycle_daily_mark_to_market_engine.py",
    "supabase/PHASE349_PRODUCTION_PAPER_PORTFOLIO_LIFECYCLE.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$sqlTarget = "supabase/PHASE350_PRODUCTION_PAPER_PERFORMANCE_LEDGER.sql"
$pythonTarget = "automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase350-production-paper-daily-orchestrator-persistent-performance-ledger.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase350-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.5.0 Supabase performance ledger schema"

$sql = @'
begin;

create table if not exists public.paper_performance_ledger_v92 (
    ledger_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    ledger_date date not null,

    cycle_status text not null,
    canonical_runtime_state text not null,
    market_data_source text,
    latest_market_date date,

    cash numeric not null,
    market_value numeric not null,
    nav numeric not null,
    realized_pnl numeric not null,
    unrealized_pnl numeric not null,

    previous_nav numeric,
    initial_nav numeric not null,
    daily_return numeric not null,
    cumulative_return numeric not null,
    high_water_mark numeric not null,
    drawdown numeric not null,

    open_positions integer not null,
    eligible_signals integer not null,
    fills_applied integer not null,

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

create unique index if not exists uq_paper_performance_ledger_v92_portfolio_date
    on public.paper_performance_ledger_v92 (portfolio_id, ledger_date);

alter table public.paper_performance_ledger_v92 enable row level security;

comment on table public.paper_performance_ledger_v92 is
'GPT Quant V9.2 persistent daily paper performance ledger. Simulation only; broker and real-money trading hard-disabled.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.5.0 Python daily orchestrator"

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
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase350_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE350_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase349_production_paper_portfolio_lifecycle_daily_mark_to_market_engine.py"
UPSTREAM_JSON = ROOT / "phase349_output/phase349_portfolio_lifecycle_mtm.json"

LEDGER_TABLE = "paper_performance_ledger_v92"
RESULT_JSON = OUT / "phase350_daily_orchestrator.json"

CONTRACT = "PHASE350_PRODUCTION_PAPER_DAILY_ORCHESTRATOR_PERSISTENT_PERFORMANCE_LEDGER"


def D(value: Any) -> Decimal:
    return Decimal(str(value))


def q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


def rest_get(
    table: str,
    params: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:700]}"
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
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1000]}"
        )


def run_upstream(approver: str) -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()

    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE349_PORTFOLIO_ID"] = PORTFOLIO_ID

    proc = subprocess.run(
        [sys.executable, str(UPSTREAM), "--approver", approver],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")

    if proc.stderr:
        print(
            proc.stderr,
            file=sys.stderr,
            end="" if proc.stderr.endswith("\n") else "\n",
        )

    if not UPSTREAM_JSON.exists():
        raise RuntimeError(
            f"Phase 3.4.9 evidence missing; upstream exit={proc.returncode}"
        )

    return proc.returncode, load_json(UPSTREAM_JSON)


def validate_safety(data: dict[str, Any]) -> None:
    if data.get("status") != "PASS":
        raise RuntimeError("Phase 3.4.9 did not PASS")

    for key in (
        "synthetic_market_data",
        "synthetic_fallback_allowed",
        "synthetic_evidence_present",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    ):
        if data.get(key) is not False:
            raise RuntimeError(
                f"Safety contract violation: {key}={data.get(key)!r}"
            )

    if data.get("fail_closed_policy") is not True:
        raise RuntimeError("fail_closed_policy must remain enabled")

    if str(data.get("portfolio_id") or "") != PORTFOLIO_ID:
        raise RuntimeError(
            f"Portfolio mismatch: {data.get('portfolio_id')!r} != {PORTFOLIO_ID!r}"
        )

    if D(data.get("nav", 0)) < 0:
        raise RuntimeError("NAV cannot be negative")

    if D(data.get("cash", 0)) < 0:
        raise RuntimeError("Cash cannot be negative")


def load_previous_ledger(ledger_date: str) -> dict[str, Any] | None:
    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("ledger_date", f"lt.{ledger_date}"),
            ("order", "ledger_date.desc"),
            ("limit", "1"),
        ],
    )

    return rows[0] if rows else None


def load_first_ledger() -> dict[str, Any] | None:
    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("order", "ledger_date.asc"),
            ("limit", "1"),
        ],
    )

    return rows[0] if rows else None


def build_ledger(upstream: dict[str, Any]) -> dict[str, Any]:
    ledger_date = str(
        upstream.get("latest_market_date")
        or datetime.now(timezone.utc).date().isoformat()
    )

    nav = money(D(upstream["nav"]))
    cash = money(D(upstream["cash"]))
    market_value = money(D(upstream["market_value"]))
    realized_pnl = money(D(upstream["realized_pnl"]))
    unrealized_pnl = money(D(upstream["unrealized_pnl"]))

    previous = load_previous_ledger(ledger_date)
    first = load_first_ledger()

    previous_nav = (
        money(D(previous["nav"]))
        if previous is not None
        else None
    )

    initial_nav = (
        money(D(first["initial_nav"]))
        if first is not None and first.get("initial_nav") is not None
        else nav
    )

    if previous_nav is not None and previous_nav != 0:
        daily_return = q((nav / previous_nav) - D(1))
    else:
        daily_return = D(0)

    if initial_nav != 0:
        cumulative_return = q((nav / initial_nav) - D(1))
    else:
        cumulative_return = D(0)

    previous_hwm = (
        money(D(previous["high_water_mark"]))
        if previous is not None
        else nav
    )

    high_water_mark = max(previous_hwm, nav)

    if high_water_mark != 0:
        drawdown = q((nav / high_water_mark) - D(1))
    else:
        drawdown = D(0)

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "ledger_date": ledger_date,
        "nav": str(nav),
        "cash": str(cash),
        "market_value": str(market_value),
        "canonical_runtime_state": upstream.get("canonical_runtime_state"),
        "daily_cycle_status": upstream.get("daily_cycle_status"),
        "open_positions": int(upstream.get("open_positions") or 0),
        "eligible_signals": int(upstream.get("eligible_v91_signals") or 0),
        "fills_applied": int(upstream.get("fills_applied") or 0),
    }

    ledger_id = "P350L-" + stable_hash(seed)[:28]

    row = {
        "ledger_id": ledger_id,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "ledger_date": ledger_date,
        "cycle_status": "COMPLETED",
        "canonical_runtime_state": upstream.get("canonical_runtime_state"),
        "market_data_source": upstream.get("market_data_source"),
        "latest_market_date": upstream.get("latest_market_date"),
        "cash": str(cash),
        "market_value": str(market_value),
        "nav": str(nav),
        "realized_pnl": str(realized_pnl),
        "unrealized_pnl": str(unrealized_pnl),
        "previous_nav": str(previous_nav) if previous_nav is not None else None,
        "initial_nav": str(initial_nav),
        "daily_return": str(daily_return),
        "cumulative_return": str(cumulative_return),
        "high_water_mark": str(high_water_mark),
        "drawdown": str(drawdown),
        "open_positions": int(upstream.get("open_positions") or 0),
        "eligible_signals": int(upstream.get("eligible_v91_signals") or 0),
        "fills_applied": int(upstream.get("fills_applied") or 0),
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
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return row


def persist_ledger(row: dict[str, Any]) -> dict[str, Any]:
    rest_upsert(
        LEDGER_TABLE,
        [row],
        "portfolio_id,ledger_date",
    )

    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("ledger_date", f"eq.{row['ledger_date']}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Performance ledger write verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.5.0",
        "",
        "## Production Paper Daily Orchestrator + Persistent Performance Ledger",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Orchestrator Status: **{result['status']}**",
        "",
        "### Daily Runtime",
        "",
        f"- Ledger Date: `{result['ledger_date']}`",
        f"- Cycle Status: **{result['cycle_status']}**",
        f"- Canonical Runtime State: **{result['canonical_runtime_state']}**",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Latest Market Date: `{result['latest_market_date']}`",
        "",
        "### Portfolio",
        "",
        f"- Cash: **{result['cash']:.2f}**",
        f"- Market Value: **{result['market_value']:.2f}**",
        f"- NAV: **{result['nav']:.2f}**",
        f"- Realized P&L: **{result['realized_pnl']:.2f}**",
        f"- Unrealized P&L: **{result['unrealized_pnl']:.2f}**",
        f"- Open Positions: **{result['open_positions']}**",
        "",
        "### Persistent Performance Ledger",
        "",
        "- Ledger Written: **YES**",
        f"- Previous NAV: **{result['previous_nav'] if result['previous_nav'] is not None else 'NONE'}**",
        f"- Initial NAV: **{result['initial_nav']:.2f}**",
        f"- Daily Return: **{result['daily_return']:.6%}**",
        f"- Cumulative Return: **{result['cumulative_return']:.6%}**",
        f"- High Water Mark: **{result['high_water_mark']:.2f}**",
        f"- Drawdown: **{result['drawdown']:.6%}**",
        f"- Eligible Signals: **{result['eligible_signals']}**",
        f"- Fills Applied: **{result['fills_applied']}**",
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

    (OUT / "phase350_daily_orchestrator.md").write_text(
        text,
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")

    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE350_APPROVER", "rchu9246"),
    )

    args = parser.parse_args()
    approver = args.approver.strip()

    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    upstream_exit, upstream = run_upstream(approver)
    validate_safety(upstream)

    ledger_row = build_ledger(upstream)
    persisted = persist_ledger(ledger_row)

    result = {
        "version": "3.5.0",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "upstream_process_exit_code": upstream_exit,
        "ledger_id": persisted["ledger_id"],
        "ledger_date": str(persisted["ledger_date"]),
        "cycle_status": persisted["cycle_status"],
        "canonical_runtime_state": persisted["canonical_runtime_state"],
        "market_data_source": persisted.get("market_data_source"),
        "latest_market_date": str(persisted.get("latest_market_date") or ""),
        "cash": float(persisted["cash"]),
        "market_value": float(persisted["market_value"]),
        "nav": float(persisted["nav"]),
        "realized_pnl": float(persisted["realized_pnl"]),
        "unrealized_pnl": float(persisted["unrealized_pnl"]),
        "previous_nav": (
            float(persisted["previous_nav"])
            if persisted.get("previous_nav") is not None
            else None
        ),
        "initial_nav": float(persisted["initial_nav"]),
        "daily_return": float(persisted["daily_return"]),
        "cumulative_return": float(persisted["cumulative_return"]),
        "high_water_mark": float(persisted["high_water_mark"]),
        "drawdown": float(persisted["drawdown"]),
        "open_positions": int(persisted["open_positions"]),
        "eligible_signals": int(persisted["eligible_signals"]),
        "fills_applied": int(persisted["fills_applied"]),
        "ledger_written": True,
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

    if result["cycle_status"] != "COMPLETED":
        raise RuntimeError("Performance ledger cycle_status must be COMPLETED")

    if result["nav"] < 0 or result["cash"] < 0:
        raise RuntimeError("Invalid negative portfolio state")

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE350 PASS: daily production-paper orchestrator + persistent performance ledger complete. "
        f"date={result['ledger_date']}, nav={result['nav']:.2f}, "
        f"daily_return={result['daily_return']:.8f}, "
        f"cumulative_return={result['cumulative_return']:.8f}, "
        f"drawdown={result['drawdown']:.8f}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.5.0 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.5.0 - Production Paper Daily Orchestrator Persistent Performance Ledger

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
    - cron: "50 8 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase350-production-paper-daily-orchestrator
  cancel-in-progress: false

jobs:
  production-paper-daily-orchestrator:
    runs-on: ubuntu-latest
    timeout-minutes: 55

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      FINMIND_TOKEN: ${{ secrets.FINMIND_TOKEN }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE350_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE349_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

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

      - name: Validate Phase 3.5.0 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py
          test -f automation/v92/paper_trading_phase349_production_paper_portfolio_lifecycle_daily_mark_to_market_engine.py
          test -f supabase/PHASE350_PRODUCTION_PAPER_PERFORMANCE_LEDGER.sql

          grep -q 'PHASE350_PRODUCTION_PAPER_DAILY_ORCHESTRATOR_PERSISTENT_PERFORMANCE_LEDGER' \
            automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py

          grep -q '"synthetic_market_data": False' \
            automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py

          grep -q '"synthetic_signals": False' \
            automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py

          grep -q '"fake_prices_allowed": False' \
            automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py

          echo "Phase 3.5.0 safety contract: PASS"

      - name: Execute Phase 3.5.0 daily orchestrator
        shell: bash
        run: |
          set -euo pipefail

          APPROVER="${{ inputs.approver }}"
          if [ -z "${APPROVER}" ]; then
            APPROVER="github-actions"
          fi

          python automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py \
            --approver "${APPROVER}"

      - name: Validate Phase 3.5.0 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase350_output/phase350_daily_orchestrator.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase350_output/phase350_daily_orchestrator.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.5.0", data
          assert data["status"] == "PASS", data
          assert data["ledger_written"] is True, data
          assert data["cycle_status"] == "COMPLETED", data
          assert data["portfolio_id"], data
          assert data["ledger_date"], data
          assert data["nav"] >= 0, data
          assert data["cash"] >= 0, data
          assert data["high_water_mark"] >= data["nav"] or abs(data["high_water_mark"] - data["nav"]) < 1e-6, data
          assert data["drawdown"] <= 1e-12, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          print("Phase 3.5.0 output validation: PASS")
          PY

      - name: Upload Phase 3.5.0 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase350-production-paper-daily-orchestrator-${{ github.run_id }}
          path: |
            phase21_output/
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
            phase345_output/
            phase3451_output/
            phase346_output/
            phase348_output/
            phase348451_output/
            phase348453_output/
            phase34846_output/
            phase349_output/
            phase350_output/
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
    'PHASE350_PRODUCTION_PAPER_DAILY_ORCHESTRATOR_PERSISTENT_PERFORMANCE_LEDGER',
    'paper_performance_ledger_v92',
    'daily_return',
    'cumulative_return',
    'high_water_mark',
    'drawdown',
    'ledger_written',
    '"synthetic_market_data": False',
    '"synthetic_signals": False',
    '"fake_prices_allowed": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.5.0 token missing: $needle"
    }
}

Write-Host "Phase 3.5.0 orchestrator/performance-ledger contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $sqlTarget $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $sqlTarget"
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Phase 3.5.0 daily master cycle:" -ForegroundColor Cyan
Write-Host "  Phase 3.4.8.4.6 daily paper runtime"
Write-Host "      -> Phase 3.4.9 portfolio lifecycle / MTM"
Write-Host "      -> Persistent daily performance ledger"
Write-Host "      -> Daily return / cumulative return / drawdown"
Write-Host ""

Write-Host "Supabase SQL required before first Action run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE350_PRODUCTION_PAPER_PERFORMANCE_LEDGER.sql"
Write-Host ""

Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 50 8 * * 1-5"
Write-Host "  (08:50 UTC = 16:50 Taiwan time, weekdays)"
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
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run Supabase SQL: PHASE350_PRODUCTION_PAPER_PERFORMANCE_LEDGER.sql"
Write-Host "  2) Review GitHub Desktop changes."
Write-Host "  3) Commit and Push origin."
Write-Host "  4) GitHub Actions -> GPT Quant Phase 3.5.0."
Write-Host "  5) Run once manually with defaults."
Write-Host "  6) Confirm Ledger Written = YES and Daily Cycle Status = COMPLETED."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
