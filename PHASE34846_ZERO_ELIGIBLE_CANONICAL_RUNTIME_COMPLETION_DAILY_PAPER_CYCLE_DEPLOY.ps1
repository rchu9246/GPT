#requires -Version 5.1
<#
PHASE34846_ZERO_ELIGIBLE_CANONICAL_RUNTIME_COMPLETION_DAILY_PAPER_CYCLE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.4.6 — Zero-Eligible Canonical Runtime Completion + Daily Production Paper Cycle

Purpose
-------
Turn the now-valid real market/signal chain into a production-paper DAILY cycle
that treats zero eligible V9.1 signals as a normal completed runtime state.

Canonical daily outcomes:
  A) NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS
     - real market data present
     - signal engine scanned > 0 stocks
     - no score >= threshold
     - 0 paper orders
     - cycle COMPLETED

  B) REAL_CANONICAL_EVIDENCE_EXECUTED
     - real eligible signals persisted
     - real prices persisted
     - paper orders/fills simulated only
     - cycle COMPLETED

Hard safety:
- Synthetic market data: DISABLED
- Synthetic signals: DISABLED
- Fake prices: DISABLED
- Broker API: NO
- Broker credentials: NO
- Broker order submission: DISABLED
- Real-money trading: DISABLED
- Live-money release: NO
- Any inconsistent evidence => FAIL-CLOSED

Created/overwritten
-------------------
  automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py
  .github/workflows/gpt-quant-v92-paper-trading-phase34846-zero-eligible-canonical-runtime-completion-daily-paper-cycle.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 108) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 108) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.4.8.4.6 Daily Production Paper Cycle"

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
    "automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase34846-zero-eligible-canonical-runtime-completion-daily-paper-cycle.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase34846-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.4.6 Python daily cycle"

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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase34846_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
UPSTREAM = ROOT / "automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py"
UPSTREAM_JSON = ROOT / "phase348453_output/phase348453_metrics_propagation_fix.json"

RESULT_JSON = OUT / "phase34846_daily_paper_cycle.json"

CONTRACT = "PHASE34846_ZERO_ELIGIBLE_CANONICAL_RUNTIME_COMPLETION_DAILY_PAPER_CYCLE"

ZERO_ELIGIBLE = "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"
EXECUTED = "REAL_CANONICAL_EVIDENCE_EXECUTED"

ALLOWED_CANONICAL_STATES = {
    ZERO_ELIGIBLE,
    EXECUTED,
    "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
    "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
}


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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
            f"Phase 3.4.8.4.5.3 evidence missing; exit code={proc.returncode}"
        )

    return proc, load_json(UPSTREAM_JSON)


def validate_safety(data: dict[str, Any]) -> None:
    false_keys = (
        "synthetic_market_data",
        "synthetic_fallback_allowed",
        "synthetic_evidence_present",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    )

    errors = [
        f"{k}={data.get(k)!r}, expected=False"
        for k in false_keys
        if data.get(k) is not False
    ]

    if data.get("fail_closed_policy") is not True:
        errors.append("fail_closed_policy must be True")

    if errors:
        raise RuntimeError("Safety contract violation: " + "; ".join(errors))


def classify_cycle(data: dict[str, Any]) -> tuple[str, str]:
    canonical = data.get("canonical_valid_state")
    upstream_execution = data.get("upstream_execution_state")

    active = int(data.get("active_stocks") or 0)
    history = int(data.get("stocks_with_history") or 0)
    rows = int(data.get("rows_scanned") or 0)
    scanned = int(data.get("signal_engine_stocks_scanned") or 0)

    reported = int(data.get("reported_signals_eligible") or 0)
    adapted = int(data.get("eligible_v91_signals") or 0)

    signals_persisted = int(data.get("signals_persisted") or 0)
    prices_persisted = int(data.get("prices_persisted") or 0)

    orders = int(data.get("paper_orders_created") or 0)
    fills = int(data.get("simulated_fills") or 0)

    if active <= 0 or history <= 0 or rows <= 0 or scanned <= 0:
        raise RuntimeError(
            "DAILY_CYCLE_INPUT_INVALID: market/signal runtime is not healthy"
        )

    if canonical not in ALLOWED_CANONICAL_STATES:
        raise RuntimeError(
            f"Unsupported canonical runtime state: {canonical!r}"
        )

    if canonical == ZERO_ELIGIBLE:
        if reported != 0 or adapted != 0:
            raise RuntimeError(
                "ZERO_ELIGIBLE_CONTRACT_MISMATCH: zero-eligible state with non-zero eligible counts"
            )
        if orders != 0 or fills != 0:
            raise RuntimeError(
                "ZERO_ELIGIBLE_ORDER_VIOLATION: zero-eligible state must create no paper orders/fills"
            )

        return "COMPLETED", "Daily paper cycle completed safely with no eligible V9.1 signal."

    if canonical == EXECUTED or upstream_execution == EXECUTED:
        if adapted <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without eligible signals"
            )
        if signals_persisted <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without persisted signals"
            )
        if prices_persisted <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without persisted real prices"
            )
        if orders <= 0 or fills <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without paper orders/fills"
            )
        if orders != fills:
            raise RuntimeError("Paper order/fill mismatch")

        return "COMPLETED", "Daily paper cycle completed with real canonical paper execution."

    # Other safe no-order runtime states are still a completed daily cycle.
    if orders != 0 or fills != 0:
        raise RuntimeError(
            "SAFE_ZERO_STATE_VIOLATION: safe zero-order state created orders/fills"
        )

    return "COMPLETED", f"Daily paper cycle completed in safe state {canonical}."


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.6",
        "",
        "## Zero-Eligible Canonical Runtime Completion + Daily Production Paper Cycle",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Daily Cycle Status: **{result['daily_cycle_status']}**",
        f"- Canonical Runtime State: **{result['canonical_runtime_state']}**",
        f"- Completion Reason: {result['completion_reason']}",
        "",
        "### Real Runtime Inputs",
        "",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Active Stocks: **{result['active_stocks']}**",
        f"- Stocks With History: **{result['stocks_with_history']}**",
        f"- Rows Scanned: **{result['rows_scanned']}**",
        f"- Latest Market Date: `{result['latest_market_date']}`",
        f"- Signal Engine Stocks Scanned: **{result['signal_engine_stocks_scanned']}**",
        f"- Score Threshold: **{result['score_threshold']}**",
        f"- Top Symbol: `{result['top_symbol'] or 'NONE'}`",
        f"- Top Score: **{result['top_score'] if result['top_score'] is not None else 'NONE'}**",
        "",
        "### Signal + Paper Execution",
        "",
        f"- Reported signals_eligible: **{result['reported_signals_eligible']}**",
        f"- Adapted Eligible V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- Signals Persisted: **{result['signals_persisted']}**",
        f"- Prices Persisted: **{result['prices_persisted']}**",
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
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    text = "\n".join(lines) + "\n"

    (OUT / "phase34846_daily_paper_cycle.md").write_text(
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
        default=os.getenv("PHASE34846_APPROVER", "rchu9246"),
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

    daily_status, reason = classify_cycle(upstream)

    result = {
        "version": "3.4.8.4.6",
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "upstream_process_exit_code": proc.returncode,
        "daily_cycle_status": daily_status,
        "canonical_runtime_state": upstream.get("canonical_valid_state"),
        "completion_reason": reason,
        "market_data_source": upstream.get("market_data_source"),
        "active_stocks": int(upstream.get("active_stocks") or 0),
        "stocks_with_history": int(upstream.get("stocks_with_history") or 0),
        "rows_scanned": int(upstream.get("rows_scanned") or 0),
        "latest_market_date": upstream.get("latest_market_date"),
        "signal_engine_stocks_scanned": int(upstream.get("signal_engine_stocks_scanned") or 0),
        "score_threshold": upstream.get("score_threshold"),
        "top_symbol": upstream.get("top_symbol"),
        "top_score": upstream.get("top_score"),
        "reported_signals_eligible": int(upstream.get("reported_signals_eligible") or 0),
        "eligible_v91_signals": int(upstream.get("eligible_v91_signals") or 0),
        "signals_persisted": int(upstream.get("signals_persisted") or 0),
        "prices_persisted": int(upstream.get("prices_persisted") or 0),
        "paper_orders_created": int(upstream.get("paper_orders_created") or 0),
        "simulated_fills": int(upstream.get("simulated_fills") or 0),
        "open_positions": int(upstream.get("open_positions") or 0),
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

    result["evidence_sha256"] = stable_hash(result)

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE34846 PASS: daily production-paper cycle completed. "
        f"state={result['canonical_runtime_state']}, "
        f"eligible={result['eligible_v91_signals']}, "
        f"orders={result['paper_orders_created']}, "
        f"fills={result['simulated_fills']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.4.8.4.6 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.4.6 - Zero Eligible Canonical Runtime Completion Daily Paper Cycle

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

  schedule:
    - cron: "20 8 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase34846-daily-paper-cycle
  cancel-in-progress: false

jobs:
  daily-production-paper-cycle:
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

      - name: Validate Phase 3.4.8.4.6 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py
          test -f automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py

          grep -q 'NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS' \
            automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py

          grep -q 'REAL_CANONICAL_EVIDENCE_EXECUTED' \
            automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py

          grep -q '"synthetic_market_data": False' \
            automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py

          grep -q '"fake_prices_allowed": False' \
            automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py

          echo "Phase 3.4.8.4.6 safety contract: PASS"

      - name: Execute Phase 3.4.8.4.6 daily production paper cycle
        shell: bash
        run: |
          set -euo pipefail

          APPROVER="${{ inputs.approver }}"
          if [ -z "${APPROVER}" ]; then
            APPROVER="github-actions"
          fi

          python automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py \
            --approver "${APPROVER}"

      - name: Validate Phase 3.4.8.4.6 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase34846_output/phase34846_daily_paper_cycle.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase34846_output/phase34846_daily_paper_cycle.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8.4.6", data
          assert data["status"] == "PASS", data
          assert data["daily_cycle_status"] == "COMPLETED", data

          assert data["market_data_source"], data
          assert data["active_stocks"] > 0, data
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

          if data["canonical_runtime_state"] == "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS":
              assert data["reported_signals_eligible"] == 0, data
              assert data["eligible_v91_signals"] == 0, data
              assert data["paper_orders_created"] == 0, data
              assert data["simulated_fills"] == 0, data

          if data["canonical_runtime_state"] == "REAL_CANONICAL_EVIDENCE_EXECUTED":
              assert data["eligible_v91_signals"] > 0, data
              assert data["signals_persisted"] > 0, data
              assert data["prices_persisted"] > 0, data
              assert data["paper_orders_created"] > 0, data
              assert data["simulated_fills"] == data["paper_orders_created"], data

          print("Phase 3.4.8.4.6 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.4.6 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase34846-daily-paper-cycle-${{ github.run_id }}
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
    'PHASE34846_ZERO_ELIGIBLE_CANONICAL_RUNTIME_COMPLETION_DAILY_PAPER_CYCLE',
    'NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS',
    'REAL_CANONICAL_EVIDENCE_EXECUTED',
    'daily_cycle_status',
    'COMPLETED',
    '"synthetic_market_data": False',
    '"fake_prices_allowed": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.4.6 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.4.6 daily-cycle contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Daily production-paper outcomes:" -ForegroundColor Cyan
Write-Host "  A) NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS -> COMPLETED / 0 orders"
Write-Host "  B) REAL_CANONICAL_EVIDENCE_EXECUTED -> COMPLETED / simulated paper orders+fills"
Write-Host ""

Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 20 8 * * 1-5"
Write-Host "  (08:20 UTC = 16:20 Taiwan time, weekdays)"
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
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.4.6."
Write-Host "  4) Run once manually with defaults."
Write-Host "  5) Confirm Daily Cycle Status = COMPLETED."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
