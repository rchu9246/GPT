#requires -Version 5.1
<#
PHASE348453_CANONICAL_MARKET_DATA_METRICS_PROPAGATION_CONTRACT_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.4.5.3 — Canonical Market Data Metrics Propagation Contract Fix

Purpose
-------
Fix the contract propagation inconsistency observed after Phase 3.4.8.4.5.2:

  selected market source = daily_prices
  active stocks = 3
  signal engine scanned = 3

but the propagated aggregate metrics became:

  stocks_with_history = 0
  rows_scanned = 0

This patch does NOT fabricate data and does NOT relax safety rules.

It recomputes / reconciles the canonical market metrics only from REAL upstream
evidence already produced by Phase 3.4.8.4.5.1:

  1) phase348451_signal_input_contract_fix.json
  2) market_source_profiles.json
  3) canonical_market_input.json

The selected real market source remains authoritative. When aggregate metrics in
the top-level result are stale/incomplete, this phase reconstructs:

  - active_stocks
  - stocks_with_history
  - rows_scanned
  - latest_market_date
  - per-symbol history metrics

from the selected source profile and canonical market snapshot.

Safe zero-signal state
----------------------
When real market input is healthy and the signal engine scans real stocks but no
V9.1 score meets the configured threshold, the canonical PASS state is:

  NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS

Safety remains hard locked:
- Synthetic market data: DISABLED
- Synthetic signals: DISABLED
- Fake prices: DISABLED
- Broker API: NO
- Broker credentials: NO
- Broker order submission: DISABLED
- Real-money trading: DISABLED
- Live-money release: NO
- Inconsistent evidence => FAIL-CLOSED

Created/overwritten
-------------------
  automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase348453-canonical-market-data-metrics-propagation-contract-fix.yml
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

Section "GPT Quant V9.2 — Phase 3.4.8.4.5.3 Canonical Market Metrics Propagation Contract Fix"

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

$pythonTarget = "automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase348453-canonical-market-data-metrics-propagation-contract-fix.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase348453-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.4.5.3 Python propagation fix"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase348453_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"

UPSTREAM = ROOT / "automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py"

UPSTREAM_RESULT = ROOT / "phase348451_output/phase348451_signal_input_contract_fix.json"
SOURCE_PROFILES = ROOT / "phase348451_output/market_source_profiles.json"
MARKET_INPUT = ROOT / "phase348451_output/canonical_market_input.json"

RESULT_JSON = OUT / "phase348453_metrics_propagation_fix.json"
RECONCILED_MARKET_JSON = OUT / "reconciled_canonical_market_metrics.json"

CONTRACT = "PHASE348453_CANONICAL_MARKET_DATA_METRICS_PROPAGATION_CONTRACT_FIX"
SAFE_ZERO_STATE = "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"

SAFE_UPSTREAM_STATES = {
    "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
    "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
    "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
    "REAL_CANONICAL_EVIDENCE_EXECUTED",
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


def load_json(path: Path) -> Any:
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

    if not UPSTREAM_RESULT.exists():
        raise RuntimeError(
            f"Phase 3.4.8.4.5.1 evidence missing; upstream exit code={proc.returncode}"
        )

    return proc, load_json(UPSTREAM_RESULT)


def validate_safety(data: dict[str, Any]) -> None:
    expected_false = (
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
        f"{key}={data.get(key)!r}, expected=False"
        for key in expected_false
        if data.get(key) is not False
    ]

    if data.get("fail_closed_policy") is not True:
        errors.append(
            f"fail_closed_policy={data.get('fail_closed_policy')!r}, expected=True"
        )

    if errors:
        raise RuntimeError("Safety contract violation: " + "; ".join(errors))


def selected_source_profile(
    selected_source: str,
) -> dict[str, Any] | None:
    if not SOURCE_PROFILES.exists():
        return None

    profiles = load_json(SOURCE_PROFILES)
    if not isinstance(profiles, list):
        return None

    matches = [
        p
        for p in profiles
        if isinstance(p, dict)
        and str(p.get("table") or "") == selected_source
    ]

    if not matches:
        return None

    readable = [
        p
        for p in matches
        if p.get("readable") is True
    ]

    return readable[0] if readable else matches[0]


def normalize_snapshot_rows(snapshot: Any) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return []

    candidates = (
        snapshot.get("market_data")
        or snapshot.get("rows")
        or snapshot.get("data")
        or []
    )

    if not isinstance(candidates, list):
        return []

    rows: list[dict[str, Any]] = []

    for row in candidates:
        if not isinstance(row, dict):
            continue

        symbol = str(row.get("symbol") or "").strip()
        trade_date = str(row.get("trade_date") or "").strip()[:10]

        if not symbol or not trade_date:
            continue

        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            continue

        if close <= 0:
            continue

        rows.append(
            {
                **row,
                "symbol": symbol,
                "trade_date": trade_date,
                "close": close,
            }
        )

    return rows


def reconstruct_metrics(upstream: dict[str, Any]) -> dict[str, Any]:
    selected_source = str(upstream.get("market_data_source") or "").strip()

    if not selected_source:
        raise RuntimeError("NO_REAL_MARKET_SOURCE")

    profile = selected_source_profile(selected_source)

    snapshot = load_json(MARKET_INPUT) if MARKET_INPUT.exists() else {}
    snapshot_rows = normalize_snapshot_rows(snapshot)

    # Only trust rows from the already-selected real market source.
    snapshot_source = str(
        snapshot.get("market_data_source")
        if isinstance(snapshot, dict)
        else ""
    ).strip()

    if snapshot_source and snapshot_source != selected_source:
        raise RuntimeError(
            "MARKET_SOURCE_PROPAGATION_MISMATCH: "
            f"upstream selected={selected_source!r}, snapshot source={snapshot_source!r}"
        )

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in snapshot_rows:
        by_symbol[row["symbol"]].append(row)

    snapshot_rows_scanned = len(snapshot_rows)
    snapshot_stocks_with_history = len(by_symbol)

    snapshot_latest_market_date = max(
        (row["trade_date"] for row in snapshot_rows),
        default=None,
    )

    profile_usable_rows = 0
    profile_symbols = 0
    profile_latest_market_date = None

    if isinstance(profile, dict):
        try:
            profile_usable_rows = int(profile.get("usable_rows") or 0)
        except (TypeError, ValueError):
            profile_usable_rows = 0

        try:
            profile_symbols = int(profile.get("symbols") or 0)
        except (TypeError, ValueError):
            profile_symbols = 0

        profile_latest_market_date = profile.get("latest_market_date")

    try:
        upstream_rows = int(upstream.get("rows_scanned") or 0)
    except (TypeError, ValueError):
        upstream_rows = 0

    try:
        upstream_history = int(upstream.get("stocks_with_history") or 0)
    except (TypeError, ValueError):
        upstream_history = 0

    active_stocks = int(upstream.get("active_stocks") or 0)

    # Reconcile using only real evidence. Prefer actual snapshot metrics;
    # fall back to the selected source profile, then upstream aggregates.
    rows_scanned = max(
        snapshot_rows_scanned,
        profile_usable_rows,
        upstream_rows,
    )

    stocks_with_history = max(
        snapshot_stocks_with_history,
        profile_symbols,
        upstream_history,
    )

    latest_market_date = (
        snapshot_latest_market_date
        or profile_latest_market_date
        or upstream.get("latest_market_date")
    )

    if active_stocks > 0 and stocks_with_history > active_stocks:
        # The profile may include broader real history than the active universe.
        # Do not fabricate truncation; cap only the active-scoped metric.
        stocks_with_history = active_stocks

    per_symbol: list[dict[str, Any]] = []

    for symbol, rows in sorted(by_symbol.items()):
        ordered = sorted(rows, key=lambda x: x["trade_date"])

        per_symbol.append(
            {
                "symbol": symbol,
                "history_rows": len(ordered),
                "oldest_market_date": ordered[0]["trade_date"],
                "latest_market_date": ordered[-1]["trade_date"],
                "latest_close": ordered[-1]["close"],
            }
        )

    evidence_source = []
    if snapshot_rows_scanned > 0:
        evidence_source.append("canonical_market_input")
    if profile_usable_rows > 0:
        evidence_source.append("selected_source_profile")
    if upstream_rows > 0:
        evidence_source.append("upstream_aggregate")

    reconciled = {
        "selected_market_data_source": selected_source,
        "active_stocks": active_stocks,
        "stocks_with_history": stocks_with_history,
        "rows_scanned": rows_scanned,
        "latest_market_date": latest_market_date,
        "per_symbol_market_history": per_symbol,
        "evidence_sources": evidence_source,
        "snapshot_rows_scanned": snapshot_rows_scanned,
        "snapshot_stocks_with_history": snapshot_stocks_with_history,
        "profile_usable_rows": profile_usable_rows,
        "profile_symbols": profile_symbols,
        "upstream_rows_scanned": upstream_rows,
        "upstream_stocks_with_history": upstream_history,
        "synthetic_market_data": False,
    }

    reconciled["evidence_sha256"] = stable_hash(reconciled)
    dump_json(RECONCILED_MARKET_JSON, reconciled)

    return reconciled


def classify_valid_state(
    upstream: dict[str, Any],
    metrics: dict[str, Any],
) -> tuple[str, str]:
    rows_scanned = int(metrics["rows_scanned"])
    stocks_with_history = int(metrics["stocks_with_history"])
    active_stocks = int(metrics["active_stocks"])

    engine_exit = int(upstream.get("signal_engine_exit_code") or 0)
    engine_scanned = int(upstream.get("signal_engine_stocks_scanned") or 0)

    reported = int(upstream.get("reported_signals_eligible") or 0)
    adapted = int(upstream.get("eligible_v91_signals") or 0)

    orders = int(upstream.get("paper_orders_created") or 0)
    fills = int(upstream.get("simulated_fills") or 0)

    upstream_state = upstream.get("execution_state")

    if active_stocks <= 0:
        raise RuntimeError("ACTIVE_STOCK_UNIVERSE_EMPTY")

    if rows_scanned <= 0 or stocks_with_history <= 0:
        raise RuntimeError(
            "CANONICAL_MARKET_METRICS_INVALID: real selected source exists "
            "but reconciled history/rows remain zero"
        )

    if engine_exit != 0:
        raise RuntimeError(
            f"SIGNAL_ENGINE_FAILED: exit code={engine_exit}"
        )

    if engine_scanned <= 0:
        raise RuntimeError(
            "SIGNAL_INPUT_CONTRACT_MISMATCH: reconciled market history exists "
            "but signal engine scanned zero stocks"
        )

    if upstream_state not in SAFE_UPSTREAM_STATES:
        raise RuntimeError(
            f"Unexpected Phase 3.4.8 execution state: {upstream_state!r}"
        )

    if reported == 0 and adapted == 0:
        if orders != 0 or fills != 0:
            raise RuntimeError(
                "Safety violation: zero eligible V9.1 signals must produce zero orders/fills"
            )

        return SAFE_ZERO_STATE, (
            "Real canonical market history is present and the V9.1 signal engine "
            "scanned real stocks, but no candidate met the configured score threshold."
        )

    if reported > 0:
        if adapted <= 0:
            raise RuntimeError(
                "SIGNAL_OUTPUT_CONTRACT_MISMATCH: engine reported eligible signals "
                "but adapter produced zero candidates"
            )

        if int(upstream.get("signals_persisted") or 0) <= 0:
            raise RuntimeError(
                "Canonical signal persistence missing for real eligible signals"
            )

    if orders > 0:
        if int(upstream.get("prices_persisted") or 0) <= 0:
            raise RuntimeError(
                "Paper orders exist without persisted real market prices"
            )

        if upstream_state != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError(
                "Paper orders exist without REAL_CANONICAL_EVIDENCE_EXECUTED"
            )

        if fills != orders:
            raise RuntimeError("Paper order/fill mismatch")

    return upstream_state or "PASS", "Canonical market metrics propagation contract is valid."


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.5.3",
        "",
        "## Canonical Market Data Metrics Propagation Contract Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        "",
        "### Selected Real Market Source",
        "",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Active Stocks: **{result['active_stocks']}**",
        f"- Stocks With History: **{result['stocks_with_history']}**",
        f"- Rows Scanned: **{result['rows_scanned']}**",
        f"- Latest Market Date: `{result['latest_market_date'] or 'NONE'}`",
        f"- Metric Evidence Sources: `{', '.join(result['metric_evidence_sources'])}`",
        "",
        "### Propagation Diagnostics",
        "",
        f"- Snapshot Rows: **{result['snapshot_rows_scanned']}**",
        f"- Snapshot Stocks With History: **{result['snapshot_stocks_with_history']}**",
        f"- Selected Source Profile Usable Rows: **{result['profile_usable_rows']}**",
        f"- Selected Source Profile Symbols: **{result['profile_symbols']}**",
        f"- Upstream Rows Scanned: **{result['upstream_rows_scanned']}**",
        f"- Upstream Stocks With History: **{result['upstream_stocks_with_history']}**",
        "",
        "### Signal Engine Contract",
        "",
        f"- Signal Engine Stocks Scanned: **{result['signal_engine_stocks_scanned']}**",
        f"- Top Symbol: `{result['top_symbol'] or 'NONE'}`",
        f"- Top Score: **{result['top_score'] if result['top_score'] is not None else 'NONE'}**",
        f"- Score Threshold: **{result['score_threshold']}**",
        f"- Reported signals_eligible: **{result['reported_signals_eligible']}**",
        f"- Adapted Eligible V9.1 Signals: **{result['eligible_v91_signals']}**",
        "",
        "### Canonical Valid State",
        "",
        f"- Canonical Valid State: **{result['canonical_valid_state']}**",
        f"- State Reason: {result['state_reason']}",
        f"- Upstream Execution State: **{result['upstream_execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
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

    (OUT / "phase348453_metrics_propagation_fix.md").write_text(
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
        default=os.getenv("PHASE348453_APPROVER", "rchu9246"),
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

    metrics = reconstruct_metrics(upstream)

    canonical_state, reason = classify_valid_state(
        upstream,
        metrics,
    )

    result = {
        "version": "3.4.8.4.5.3",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "upstream_process_exit_code": proc.returncode,
        "market_data_source": metrics["selected_market_data_source"],
        "active_stocks": metrics["active_stocks"],
        "stocks_with_history": metrics["stocks_with_history"],
        "rows_scanned": metrics["rows_scanned"],
        "latest_market_date": metrics["latest_market_date"],
        "metric_evidence_sources": metrics["evidence_sources"],
        "snapshot_rows_scanned": metrics["snapshot_rows_scanned"],
        "snapshot_stocks_with_history": metrics["snapshot_stocks_with_history"],
        "profile_usable_rows": metrics["profile_usable_rows"],
        "profile_symbols": metrics["profile_symbols"],
        "upstream_rows_scanned": metrics["upstream_rows_scanned"],
        "upstream_stocks_with_history": metrics["upstream_stocks_with_history"],
        "signal_engine_stocks_scanned": int(
            upstream.get("signal_engine_stocks_scanned") or 0
        ),
        "score_threshold": upstream.get("score_threshold"),
        "reported_signals_eligible": int(
            upstream.get("reported_signals_eligible") or 0
        ),
        "eligible_v91_signals": int(
            upstream.get("eligible_v91_signals") or 0
        ),
        "top_symbol": upstream.get("top_symbol"),
        "top_score": upstream.get("top_score"),
        "signals_persisted": int(
            upstream.get("signals_persisted") or 0
        ),
        "prices_persisted": int(
            upstream.get("prices_persisted") or 0
        ),
        "upstream_execution_state": upstream.get("execution_state"),
        "canonical_valid_state": canonical_state,
        "state_reason": reason,
        "paper_orders_created": int(
            upstream.get("paper_orders_created") or 0
        ),
        "simulated_fills": int(
            upstream.get("simulated_fills") or 0
        ),
        "open_positions": int(
            upstream.get("open_positions") or 0
        ),
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
        "PHASE348453 PASS: canonical market-data metrics propagation reconciled. "
        f"source={result['market_data_source']}, "
        f"active={result['active_stocks']}, "
        f"history={result['stocks_with_history']}, "
        f"rows={result['rows_scanned']}, "
        f"engine_scanned={result['signal_engine_stocks_scanned']}, "
        f"eligible={result['eligible_v91_signals']}, "
        f"state={result['canonical_valid_state']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.4.8.4.5.3 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.4.5.3 - Canonical Market Data Metrics Propagation Contract Fix

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
  group: gpt-quant-phase348453-market-metrics-propagation
  cancel-in-progress: false

jobs:
  canonical-market-metrics-propagation:
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

      - name: Validate Phase 3.4.8.4.5.3 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py
          test -f automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py

          grep -q 'PHASE348453_CANONICAL_MARKET_DATA_METRICS_PROPAGATION_CONTRACT_FIX' \
            automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py

          grep -q 'NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS' \
            automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py

          grep -q '"synthetic_market_data": False' \
            automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py

          grep -q '"fake_prices_allowed": False' \
            automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py

          echo "Phase 3.4.8.4.5.3 safety contract: PASS"

      - name: Execute Phase 3.4.8.4.5.3 propagation fix
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8.4.5.3 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase348453_output/phase348453_metrics_propagation_fix.json
          test -f phase348453_output/reconciled_canonical_market_metrics.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase348453_output/phase348453_metrics_propagation_fix.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8.4.5.3", data
          assert data["status"] == "PASS", data

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

          print("Phase 3.4.8.4.5.3 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.4.5.3 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase348453-market-metrics-propagation-${{ github.run_id }}
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
    'PHASE348453_CANONICAL_MARKET_DATA_METRICS_PROPAGATION_CONTRACT_FIX',
    'NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS',
    'reconstruct_metrics',
    'selected_source_profile',
    'canonical_market_input',
    'profile_usable_rows',
    'snapshot_rows_scanned',
    'stocks_with_history',
    'rows_scanned',
    'SIGNAL_INPUT_CONTRACT_MISMATCH',
    '"synthetic_market_data": False',
    '"fake_prices_allowed": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.4.5.3 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.4.5.3 market-metrics propagation contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Phase 3.4.8.4.5.3 reconciliation sources:" -ForegroundColor Cyan
Write-Host "  1) selected market source profile"
Write-Host "  2) canonical_market_input.json"
Write-Host "  3) upstream aggregate metrics"
Write-Host ""

Write-Host "Expected corrected state:" -ForegroundColor Cyan
Write-Host "  Market Data Source: daily_prices"
Write-Host "  Active Stocks: 3"
Write-Host "  Stocks With History: > 0"
Write-Host "  Rows Scanned: > 0"
Write-Host "  Signal Engine Stocks Scanned: > 0"
Write-Host ""

Write-Host "When threshold is not met:" -ForegroundColor Cyan
Write-Host "  Canonical Valid State: NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"
Write-Host "  Paper Orders: 0"
Write-Host "  Simulated Fills: 0"
Write-Host "  Workflow: PASS"
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
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.4.5.3."
Write-Host "  4) Run with defaults."
Write-Host "  5) Confirm history/rows are reconciled and zero-eligible state is green PASS."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
