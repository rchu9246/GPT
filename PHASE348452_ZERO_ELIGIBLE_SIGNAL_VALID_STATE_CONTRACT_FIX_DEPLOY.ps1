#requires -Version 5.1
<#
PHASE348452_ZERO_ELIGIBLE_SIGNAL_VALID_STATE_CONTRACT_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.4.5.2 — Zero Eligible Signal Valid-State Contract Fix

Purpose
-------
Phase 3.4.8.4.5.1 successfully proved the real runtime chain is wired:

  selected market source = daily_prices
  active stocks = 3
  stocks with history = 3
  rows scanned = 471
  signal engine stocks scanned = 3
  signal engine exit code = 0

The remaining issue is contract semantics:
when the V9.1 signal engine legitimately reports zero eligible signals because
all scores are below the configured threshold, the workflow should PASS in a
safe zero-order state instead of failing final validation.

This patch makes that state canonical:

  NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS

Valid safe PASS conditions
--------------------------
- Real market source discovered
- Market history exists
- Signal engine scanned > 0 stocks
- Signal engine exit code = 0
- reported_signals_eligible = 0
- adapted eligible signals = 0
- paper orders = 0
- simulated fills = 0
- all synthetic/broker/real-money locks remain disabled

Unsafe states still FAIL CLOSED.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase348452-zero-eligible-signal-valid-state-contract-fix.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 104) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 104) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.4.8.4.5.2 Zero Eligible Signal Valid-State Contract Fix"

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
    "automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py",
    ".github/workflows/gpt-quant-v92-paper-trading-phase348451-v91-runtime-market-data-source-discovery-signal-input-contract-fix.yml"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required Phase 3.4.8.4.5.1 upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase348452-zero-eligible-signal-valid-state-contract-fix.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase348452-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.4.5.2 Python valid-state contract fix"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase348452_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"

UPSTREAM = ROOT / "automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py"
UPSTREAM_JSON = ROOT / "phase348451_output/phase348451_signal_input_contract_fix.json"

RESULT_JSON = OUT / "phase348452_zero_eligible_valid_state.json"

CONTRACT = "PHASE348452_ZERO_ELIGIBLE_SIGNAL_VALID_STATE_CONTRACT_FIX"
SAFE_ZERO_STATE = "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"

ALLOWED_UPSTREAM_EXECUTION_STATES = {
    "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
    "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
    "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
    "REAL_CANONICAL_EVIDENCE_EXECUTED",
}


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_upstream(approver: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

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
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if not UPSTREAM_JSON.exists():
        raise RuntimeError(
            f"Phase 3.4.8.4.5.1 evidence missing; exit code={proc.returncode}"
        )

    return proc, load_json(UPSTREAM_JSON)


def validate_safety(data: dict[str, Any]) -> None:
    expected_false = {
        "synthetic_market_data": False,
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }

    errors = [
        f"{key}={data.get(key)!r}, expected=False"
        for key, expected in expected_false.items()
        if data.get(key) is not expected
    ]

    if data.get("fail_closed_policy") is not True:
        errors.append(
            f"fail_closed_policy={data.get('fail_closed_policy')!r}, expected=True"
        )

    if errors:
        raise RuntimeError("Safety contract violation: " + "; ".join(errors))


def classify(data: dict[str, Any]) -> tuple[str, str]:
    market_source = data.get("market_data_source")
    stocks_with_history = int(data.get("stocks_with_history") or 0)
    rows_scanned = int(data.get("rows_scanned") or 0)
    engine_exit = int(data.get("signal_engine_exit_code") or 0)
    engine_scanned = int(data.get("signal_engine_stocks_scanned") or 0)
    reported = int(data.get("reported_signals_eligible") or 0)
    adapted = int(data.get("eligible_v91_signals") or 0)
    orders = int(data.get("paper_orders_created") or 0)
    fills = int(data.get("simulated_fills") or 0)
    execution_state = data.get("execution_state")

    if not market_source:
        raise RuntimeError("NO_REAL_MARKET_SOURCE")

    if stocks_with_history <= 0 or rows_scanned <= 0:
        raise RuntimeError(
            "MARKET_INPUT_INVALID: real source exists but usable market history is empty"
        )

    if engine_exit != 0:
        raise RuntimeError(
            f"SIGNAL_ENGINE_FAILED: exit code={engine_exit}"
        )

    if engine_scanned <= 0:
        raise RuntimeError(
            "SIGNAL_INPUT_CONTRACT_MISMATCH: market history exists but signal engine scanned zero stocks"
        )

    if execution_state not in ALLOWED_UPSTREAM_EXECUTION_STATES:
        raise RuntimeError(
            f"Unexpected upstream execution_state={execution_state!r}"
        )

    # This is the exact valid state this patch introduces.
    if reported == 0 and adapted == 0:
        if orders != 0 or fills != 0:
            raise RuntimeError(
                "Safety violation: zero eligible V9.1 signals must produce zero orders/fills"
            )

        return SAFE_ZERO_STATE, (
            "Real market data and signal-engine input are healthy; "
            "no V9.1 candidates met the configured eligibility threshold."
        )

    # If the engine says signals exist, adapter and persistence must agree.
    if reported > 0:
        if adapted <= 0:
            raise RuntimeError(
                "SIGNAL_OUTPUT_CONTRACT_MISMATCH: reported eligible > 0 but adapted signals = 0"
            )

        if int(data.get("signals_persisted") or 0) <= 0:
            raise RuntimeError(
                "Canonical signal persistence missing for real eligible signals"
            )

    if orders > 0:
        if int(data.get("prices_persisted") or 0) <= 0:
            raise RuntimeError(
                "Paper orders exist without persisted real market prices"
            )
        if execution_state != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError(
                "Paper orders exist without REAL_CANONICAL_EVIDENCE_EXECUTED"
            )
        if fills != orders:
            raise RuntimeError(
                "Paper order/fill mismatch"
            )

    return execution_state or "PASS", "Upstream canonical execution contract is valid."


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.5.2",
        "",
        "## Zero Eligible Signal Valid-State Contract Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        "",
        "### Runtime Market + Signal Input",
        "",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Active Stocks: **{result['active_stocks']}**",
        f"- Stocks With History: **{result['stocks_with_history']}**",
        f"- Rows Scanned: **{result['rows_scanned']}**",
        f"- Latest Market Date: `{result['latest_market_date']}`",
        f"- Signal Engine Stocks Scanned: **{result['signal_engine_stocks_scanned']}**",
        f"- Top Symbol: `{result['top_symbol'] or 'NONE'}`",
        f"- Top Score: **{result['top_score'] if result['top_score'] is not None else 'NONE'}**",
        f"- Score Threshold: **{result['score_threshold']}**",
        "",
        "### Eligibility Contract",
        "",
        f"- Reported signals_eligible: **{result['reported_signals_eligible']}**",
        f"- Adapted Eligible V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- Canonical Valid State: **{result['canonical_valid_state']}**",
        f"- State Reason: {result['state_reason']}",
        "",
        "### Paper Execution",
        "",
        f"- Upstream Execution State: **{result['upstream_execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
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
    ]

    text = "\n".join(lines) + "\n"

    (OUT / "phase348452_zero_eligible_valid_state.md").write_text(
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
        default=os.getenv("PHASE348452_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety violation: mode must remain SHADOW_ONLY_NO_BROKER"
        )

    proc, upstream = run_upstream(approver)
    validate_safety(upstream)

    canonical_state, reason = classify(upstream)

    result = {
        "version": "3.4.8.4.5.2",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "upstream_process_exit_code": proc.returncode,
        "market_data_source": upstream.get("market_data_source"),
        "active_stocks": upstream.get("active_stocks"),
        "stocks_with_history": upstream.get("stocks_with_history"),
        "rows_scanned": upstream.get("rows_scanned"),
        "latest_market_date": upstream.get("latest_market_date"),
        "signal_engine_stocks_scanned": upstream.get("signal_engine_stocks_scanned"),
        "score_threshold": upstream.get("score_threshold"),
        "reported_signals_eligible": upstream.get("reported_signals_eligible"),
        "eligible_v91_signals": upstream.get("eligible_v91_signals"),
        "top_symbol": upstream.get("top_symbol"),
        "top_score": upstream.get("top_score"),
        "signals_persisted": upstream.get("signals_persisted"),
        "prices_persisted": upstream.get("prices_persisted"),
        "upstream_execution_state": upstream.get("execution_state"),
        "canonical_valid_state": canonical_state,
        "state_reason": reason,
        "paper_orders_created": upstream.get("paper_orders_created", 0),
        "simulated_fills": upstream.get("simulated_fills", 0),
        "open_positions": upstream.get("open_positions", 0),
        "synthetic_market_data": False,
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
    }

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    print(
        "PHASE348452 PASS: zero-eligible valid-state contract accepted. "
        f"state={canonical_state}, "
        f"market={result['market_data_source']}, "
        f"engine_scanned={result['signal_engine_stocks_scanned']}, "
        f"eligible={result['eligible_v91_signals']}, "
        f"orders={result['paper_orders_created']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.4.8.4.5.2 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.4.5.2 - Zero Eligible Signal Valid-State Contract Fix

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

      score_threshold:
        description: Minimum eligible V9.1 signal score
        required: true
        default: "65"
        type: string

      max_candidates:
        description: Maximum eligible V9.1 signals per run
        required: true
        default: "3"
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase348452-zero-eligible-valid-state
  cancel-in-progress: false

jobs:
  zero-eligible-valid-state:
    runs-on: ubuntu-latest
    timeout-minutes: 45

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      FINMIND_TOKEN: ${{ secrets.FINMIND_TOKEN }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE3421_REQUIRED_PASS_DAYS: "5"
      PHASE344_REQUIRED_PASS_DAYS: "5"
      PHASE345_REQUIRED_PASS_DAYS: "5"
      PHASE346_REQUIRED_PASS_DAYS: "5"

      PHASE348451_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE348451_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}
      PHASE348451_MAX_ROWS_PER_TABLE: "5000"

      PHASE348_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE348_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}
      PHASE348_INITIAL_CASH: "1000000"
      PHASE348_MAX_POSITION_PCT: "0.20"
      PHASE348_ROUND_LOT: "1000"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependencies
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.4.8.4.5.2 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py
          test -f automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py

          grep -q 'NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS' \
            automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py

          grep -q '"synthetic_market_data": False' \
            automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py

          grep -q '"fake_prices_allowed": False' \
            automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py

          echo "Phase 3.4.8.4.5.2 safety contract: PASS"

      - name: Execute Phase 3.4.8.4.5.2 zero-eligible valid-state contract
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase348452_zero_eligible_signal_valid_state_contract_fix.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8.4.5.2 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase348452_output/phase348452_zero_eligible_valid_state.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase348452_output/phase348452_zero_eligible_valid_state.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8.4.5.2", data
          assert data["status"] == "PASS", data

          assert data["market_data_source"], data
          assert data["stocks_with_history"] > 0, data
          assert data["rows_scanned"] > 0, data
          assert data["signal_engine_stocks_scanned"] > 0, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_fallback_allowed"] is False, data
          assert data["synthetic_evidence_present"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          if data["reported_signals_eligible"] == 0:
              assert data["eligible_v91_signals"] == 0, data
              assert data["canonical_valid_state"] == "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS", data
              assert data["paper_orders_created"] == 0, data
              assert data["simulated_fills"] == 0, data

          if data["paper_orders_created"] > 0:
              assert data["signals_persisted"] > 0, data
              assert data["prices_persisted"] > 0, data
              assert data["upstream_execution_state"] == "REAL_CANONICAL_EVIDENCE_EXECUTED", data
              assert data["simulated_fills"] == data["paper_orders_created"], data

          print("Phase 3.4.8.4.5.2 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.4.5.2 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase348452-zero-eligible-valid-state-${{ github.run_id }}
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
            phase348452_output/
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
    'PHASE348452_ZERO_ELIGIBLE_SIGNAL_VALID_STATE_CONTRACT_FIX',
    'NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS',
    'SIGNAL_INPUT_CONTRACT_MISMATCH',
    'reported_signals_eligible',
    'paper_orders_created',
    '"synthetic_market_data": False',
    '"fake_prices_allowed": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.4.5.2 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.4.5.2 zero-eligible valid-state contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "New canonical safe state:" -ForegroundColor Cyan
Write-Host "  NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"
Write-Host ""

Write-Host "This state is valid only when:" -ForegroundColor Cyan
Write-Host "  Real market source exists"
Write-Host "  Stocks with history > 0"
Write-Host "  Signal engine stocks scanned > 0"
Write-Host "  Signal engine exit code = 0"
Write-Host "  reported_signals_eligible = 0"
Write-Host "  adapted eligible signals = 0"
Write-Host "  paper orders = 0"
Write-Host "  simulated fills = 0"
Write-Host ""

Write-Host "Unsafe conditions still fail closed." -ForegroundColor Yellow
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
Write-Host "  1) Review GitHub Desktop changes."
Write-Host "  2) Commit and Push origin."
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.4.5.2."
Write-Host "  4) Run with defaults."
Write-Host "  5) Confirm Canonical Valid State = NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS when threshold is not met."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
