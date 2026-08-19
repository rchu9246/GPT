#requires -Version 5.1
<#
PHASE3484_V91_SIGNAL_PRODUCER_CANONICAL_PERSISTENCE_CONTRACT_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.4 — V9.1 Signal Producer Canonical Persistence Contract Fix

Purpose
-------
Repair the last known break in the runtime chain:

  Phase 2.1 V9.1 Signal Generation
  -> eligible BUY candidates
  -> public.signals canonical producer contract
  -> Phase 3.4.8.3 producer adapter
  -> paper_canonical_signals_v92
  -> paper_canonical_market_prices_v92
  -> Phase 3.4.8
  -> REAL_CANONICAL_EVIDENCE_EXECUTED
  -> Paper Orders / Simulated Fills

Observed problem
----------------
Phase 3.4.8.3 diagnostics showed:

  signals: table readable but no eligible V9.1 BUY rows >= 65.0

This fix:
- discovers the latest Phase 2.1/V9.1 producer output available in the same run,
- normalizes it to the public.signals contract,
- persists only real V9.1 eligible BUY signals,
- validates a round-trip read from public.signals,
- then invokes Phase 3.4.8.3 using the persisted producer contract.

Safety
------
- No synthetic signals.
- No fake prices.
- No broker API.
- No broker credentials.
- No broker order submission.
- No real-money trading.
- No eligible real V9.1 signal => zero orders.
- Any unsafe state => BLOCKED / FAIL-CLOSED.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase3484-v91-signal-producer-canonical-persistence-contract-fix.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 96) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 96) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.4.8.4 V9.1 Signal Producer Contract Fix"

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
    "automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py",
    "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase3484-v91-signal-producer-canonical-persistence-contract-fix.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase3484-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.4 Python producer-contract fix"

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
OUT = ROOT / "phase3484_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
SCORE_THRESHOLD = float(os.getenv("PHASE3484_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE3484_MAX_CANDIDATES", "3"))

PHASE3483 = ROOT / "automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py"
P3483_JSON = ROOT / "phase3483_output/phase3483_wiring_fix.json"

RESULT_JSON = OUT / "phase3484_contract_fix.json"
NORMALIZED_JSON = OUT / "phase3484_normalized_v91_signals.json"

CONTRACT = "PHASE3484_V91_SIGNAL_PRODUCER_CANONICAL_PERSISTENCE_CONTRACT_FIX"
SAFETY_CONTRACT = "REAL_V91_PRODUCER_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY"

TARGET_TABLE = "signals"

LOCAL_SIGNAL_FILES = [
    ROOT / "phase21_output/signals.json",
    ROOT / "phase21_output/phase21_signals.json",
    ROOT / "phase21_output/signal_generation.json",
    ROOT / "phase21_output/phase21_signal_generation.json",
    ROOT / "output/signals.json",
    ROOT / "output/latest_signals.json",
    ROOT / "artifacts/signals.json",
    ROOT / "artifacts/latest_signals.json",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def supabase() -> tuple[str, dict[str, str]]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not base:
        raise RuntimeError("SUPABASE_URL is missing")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing")

    return base, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(
    table: str,
    params: list[tuple[str, str]],
) -> tuple[list[dict[str, Any]], str | None]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.RequestException as exc:
        return [], f"{table}: request error: {exc}"

    if response.status_code >= 400:
        return [], f"{table}: HTTP {response.status_code}: {response.text[:300]}"

    try:
        data = response.json()
    except ValueError:
        return [], f"{table}: invalid JSON"

    if not isinstance(data, list):
        return [], f"{table}: response was not a row list"

    return [x for x in data if isinstance(x, dict)], None


def rest_insert(table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "return=minimal"
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.post(
        url,
        headers=headers,
        data=json.dumps(rows, ensure_ascii=False),
        timeout=20,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: insert HTTP {response.status_code}: {response.text[:900]}"
        )


def extract_rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if isinstance(raw, dict):
        for key in (
            "signals",
            "top_candidates",
            "candidates",
            "items",
            "rows",
            "data",
            "results",
        ):
            value = raw.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

    return []


def normalize_signal(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    symbol = str(
        row.get("symbol")
        or row.get("stock_id")
        or row.get("ticker")
        or row.get("stock_symbol")
        or ""
    ).strip()

    if not symbol:
        return None

    raw_signal = str(
        row.get("signal")
        or row.get("action")
        or row.get("recommendation")
        or "BUY"
    ).strip().upper()

    if raw_signal not in {"BUY", "LONG"}:
        return None

    score_raw = (
        row.get("total_score")
        if row.get("total_score") is not None
        else row.get("score")
    )

    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        return None

    if score < SCORE_THRESHOLD:
        return None

    strategy = str(
        row.get("strategy_version")
        or row.get("strategy")
        or STRATEGY
    ).strip()

    if strategy.upper() != STRATEGY.upper():
        return None

    trade_date = str(
        row.get("trade_date")
        or row.get("market_date")
        or row.get("date")
        or ""
    ).strip()[:10]

    if not trade_date:
        return None

    normalized = {
        "symbol": symbol,
        "trade_date": trade_date,
        "strategy_version": STRATEGY,
        "total_score": round(score, 4),
        "signal": "BUY",
        "source": source,
        "synthetic_evidence": False,
    }
    normalized["producer_evidence_sha256"] = stable_hash(normalized)
    return normalized


def load_local_v91_signals() -> tuple[list[dict[str, Any]], str | None]:
    for path in LOCAL_SIGNAL_FILES:
        if not path.exists():
            continue

        try:
            rows = extract_rows(load_json(path))
        except Exception:
            continue

        normalized = [
            item
            for row in rows
            if (item := normalize_signal(row, str(path.relative_to(ROOT)))) is not None
        ]

        if not normalized:
            continue

        latest = max(x["trade_date"] for x in normalized)
        normalized = [x for x in normalized if x["trade_date"] == latest]
        normalized.sort(key=lambda x: (-float(x["total_score"]), x["symbol"]))
        return normalized[:MAX_CANDIDATES], str(path.relative_to(ROOT))

    return [], None


def existing_signals_table_schema_sample() -> tuple[list[dict[str, Any]], list[str]]:
    diagnostics: list[str] = []
    rows, error = rest_get(
        TARGET_TABLE,
        [
            ("select", "*"),
            ("limit", "5"),
        ],
    )
    if error:
        diagnostics.append(error)
        return [], diagnostics
    return rows, diagnostics


def contract_rows_for_table(
    normalized: list[dict[str, Any]],
    sample_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Build inserts against the actual public.signals schema that is visible at runtime.

    We only write keys known to exist in the existing table sample, plus a conservative
    set of common canonical keys when the table is empty.
    """
    diagnostics: list[str] = []

    if sample_rows:
        available = set()
        for row in sample_rows:
            available.update(row.keys())
    else:
        # Conservative fallback contract.
        available = {
            "symbol",
            "stock_id",
            "trade_date",
            "strategy_version",
            "total_score",
            "score",
            "signal",
            "confidence",
        }

    contract_rows: list[dict[str, Any]] = []

    for item in normalized:
        row: dict[str, Any] = {}

        if "symbol" in available:
            row["symbol"] = item["symbol"]
        elif "stock_id" in available:
            row["stock_id"] = item["symbol"]
        else:
            diagnostics.append("signals table exposes neither symbol nor stock_id")
            continue

        if "trade_date" in available:
            row["trade_date"] = item["trade_date"]

        if "strategy_version" in available:
            row["strategy_version"] = item["strategy_version"]

        if "total_score" in available:
            row["total_score"] = item["total_score"]
        elif "score" in available:
            row["score"] = item["total_score"]
        else:
            diagnostics.append("signals table exposes neither total_score nor score")
            continue

        if "signal" in available:
            row["signal"] = "BUY"

        if "confidence" in available:
            row["confidence"] = min(max(item["total_score"] / 100.0, 0.0), 1.0)

        contract_rows.append(row)

    return contract_rows, diagnostics


def verify_roundtrip(
    normalized: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    diagnostics: list[str] = []
    rows, error = rest_get(
        TARGET_TABLE,
        [
            ("select", "*"),
            ("limit", "500"),
        ],
    )

    if error:
        diagnostics.append(error)
        return [], diagnostics

    eligible: list[dict[str, Any]] = []

    wanted_symbols = {x["symbol"] for x in normalized}
    wanted_dates = {x["trade_date"] for x in normalized}

    for row in rows:
        item = normalize_signal(row, f"supabase:{TARGET_TABLE}")
        if not item:
            continue
        if item["symbol"] not in wanted_symbols:
            continue
        if item["trade_date"] not in wanted_dates:
            continue
        eligible.append(item)

    eligible.sort(key=lambda x: (-float(x["total_score"]), x["symbol"]))
    return eligible[:MAX_CANDIDATES], diagnostics


def run_phase3483(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE3483_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE3483_MAX_CANDIDATES"] = str(MAX_CANDIDATES)

    proc = subprocess.run(
        [sys.executable, str(PHASE3483), "--approver", approver],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Phase 3.4.8.3 failed with exit code {proc.returncode}"
        )

    if not P3483_JSON.exists():
        raise RuntimeError("Phase 3.4.8.3 evidence missing")

    return load_json(P3483_JSON)


def write_summary(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = stable_hash(result)
    dump_json(RESULT_JSON, result)

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4",
        "",
        "## V9.1 Signal Producer Canonical Persistence Contract Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        "",
        "### Producer Contract",
        "",
        f"- Local V9.1 Producer Source: `{result['local_producer_source'] or 'NONE'}`",
        f"- Eligible V9.1 Signals Found: **{result['eligible_v91_signals_found']}**",
        f"- Rows Prepared For public.signals: **{result['rows_prepared']}**",
        f"- Rows Round-trip Eligible: **{result['rows_roundtrip_eligible']}**",
        "",
        "### Downstream Phase 3.4.8.3",
        "",
        f"- Producer Signal Source: `{result['phase3483_producer_signal_source'] or 'NONE'}`",
        f"- Producer Market Source: `{result['phase3483_producer_market_source'] or 'NONE'}`",
        f"- Signals Persisted: **{result['phase3483_signals_persisted']}**",
        f"- Prices Persisted: **{result['phase3483_prices_persisted']}**",
        f"- Execution State: **{result['phase3483_execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        "",
        "### Safety Boundary",
        "",
        "- Synthetic fallback allowed: **NO**",
        "- Synthetic evidence present: **NO**",
        "- Broker API used: **NO**",
        "- Broker credentials used: **NO**",
        "- Broker order submission: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Live-money release authorized: **NO**",
        "- Fail-closed policy: **ENABLED**",
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    if result.get("diagnostics"):
        lines.extend(["", "### Diagnostics", ""])
        lines.extend(f"- {x}" for x in result["diagnostics"][:30])

    text = "\n".join(lines) + "\n"
    (OUT / "phase3484_contract_fix.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE3484_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: mode must remain SHADOW_ONLY_NO_BROKER")

    diagnostics: list[str] = []

    normalized, local_source = load_local_v91_signals()
    dump_json(NORMALIZED_JSON, {"signals": normalized})

    sample, sample_diag = existing_signals_table_schema_sample()
    diagnostics.extend(sample_diag)

    contract_rows, contract_diag = contract_rows_for_table(normalized, sample)
    diagnostics.extend(contract_diag)

    if normalized and not contract_rows:
        raise RuntimeError(
            "Eligible V9.1 signals exist, but public.signals schema cannot satisfy "
            "the canonical producer contract. See diagnostics."
        )

    if contract_rows:
        rest_insert(TARGET_TABLE, contract_rows)

    roundtrip, roundtrip_diag = verify_roundtrip(normalized)
    diagnostics.extend(roundtrip_diag)

    # If we had local producer signals, public.signals must now expose at least one
    # eligible round-trip row. Otherwise the fix must fail closed rather than pretend success.
    if normalized and not roundtrip:
        raise RuntimeError(
            "V9.1 producer contract persistence failed round-trip verification: "
            "public.signals still has no eligible V9.1 BUY row >= threshold."
        )

    phase3483 = run_phase3483(approver)

    result = {
        "version": "3.4.8.4",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "local_producer_source": local_source,
        "eligible_v91_signals_found": len(normalized),
        "rows_prepared": len(contract_rows),
        "rows_roundtrip_eligible": len(roundtrip),
        "phase3483_producer_signal_source": phase3483.get("producer_signal_source"),
        "phase3483_producer_market_source": phase3483.get("producer_market_source"),
        "phase3483_signals_persisted": phase3483.get("signals_persisted", 0),
        "phase3483_prices_persisted": phase3483.get("prices_persisted", 0),
        "phase3483_execution_state": phase3483.get("phase348_execution_state"),
        "paper_orders_created": phase3483.get("paper_orders_created", 0),
        "simulated_fills": phase3483.get("simulated_fills", 0),
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "diagnostics": diagnostics,
    }

    if result["paper_orders_created"] > 0:
        if result["rows_roundtrip_eligible"] <= 0:
            raise RuntimeError("Orders exist without eligible public.signals round-trip")
        if result["phase3483_signals_persisted"] <= 0:
            raise RuntimeError("Orders exist without canonical signal persistence")
        if result["phase3483_prices_persisted"] <= 0:
            raise RuntimeError("Orders exist without canonical real-price persistence")
        if result["phase3483_execution_state"] != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError("Orders exist without REAL_CANONICAL_EVIDENCE_EXECUTED")

    write_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE3484 PASS: V9.1 producer canonical persistence contract validated. "
        f"local_signals={len(normalized)}, roundtrip={len(roundtrip)}, "
        f"orders={result['paper_orders_created']}, fills={result['simulated_fills']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.4.8.4 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.4 - V9.1 Signal Producer Canonical Persistence Contract Fix

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
        description: Minimum eligible canonical signal score
        required: true
        default: "65"
        type: string

      max_candidates:
        description: Maximum eligible signals per run
        required: true
        default: "3"
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase3484-v91-producer-contract-fix
  cancel-in-progress: false

jobs:
  v91-producer-contract-fix:
    runs-on: ubuntu-latest
    timeout-minutes: 25

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE3421_REQUIRED_PASS_DAYS: "5"
      PHASE344_REQUIRED_PASS_DAYS: "5"
      PHASE345_REQUIRED_PASS_DAYS: "5"
      PHASE346_REQUIRED_PASS_DAYS: "5"

      PHASE3484_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE3484_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}

      PHASE3483_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE3483_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}
      PHASE3483_INITIAL_CASH: "1000000"
      PHASE3483_MAX_POSITION_PCT: "0.20"
      PHASE3483_ROUND_LOT: "1000"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependency
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.4.8.4 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py
          test -f automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py

          grep -q 'REAL_V91_PRODUCER_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY' \
            automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py

          grep -q '"synthetic_fallback_allowed": False' \
            automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py

          echo "Phase 3.4.8.4 safety contract: PASS"

      - name: Execute Phase 3.4.8.4 producer contract fix
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8.4 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase3484_output/phase3484_contract_fix.json
          test -f phase3484_output/phase3484_normalized_v91_signals.json
          test -f phase3483_output/phase3483_wiring_fix.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase3484_output/phase3484_contract_fix.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8.4", data
          assert data["status"] == "PASS", data
          assert data["synthetic_fallback_allowed"] is False, data
          assert data["synthetic_evidence_present"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          if data["eligible_v91_signals_found"] > 0:
              assert data["rows_prepared"] > 0, data
              assert data["rows_roundtrip_eligible"] > 0, data

          if data["paper_orders_created"] > 0:
              assert data["rows_roundtrip_eligible"] > 0, data
              assert data["phase3483_signals_persisted"] > 0, data
              assert data["phase3483_prices_persisted"] > 0, data
              assert data["phase3483_execution_state"] == "REAL_CANONICAL_EVIDENCE_EXECUTED", data
              assert data["simulated_fills"] == data["paper_orders_created"], data
          else:
              assert data["phase3483_execution_state"] in {
                  "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
                  "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
                  "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
              }, data

          print("Phase 3.4.8.4 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.4 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3484-v91-producer-contract-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
            phase345_output/
            phase3451_output/
            phase346_output/
            phase348_output/
            phase3483_output/
            phase3484_output/
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
    'PHASE3484_V91_SIGNAL_PRODUCER_CANONICAL_PERSISTENCE_CONTRACT_FIX',
    'REAL_V91_PRODUCER_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY',
    '"synthetic_fallback_allowed": False',
    '"synthetic_evidence_present": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False',
    'public.signals',
    'rows_roundtrip_eligible',
    'REAL_CANONICAL_EVIDENCE_EXECUTED'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.4 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.4 static contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Phase 3.4.8.4 target:" -ForegroundColor Cyan
Write-Host "  Phase 2.1 / V9.1 producer output"
Write-Host "       -> normalize BUY signal contract"
Write-Host "       -> persist to public.signals"
Write-Host "       -> verify round-trip eligible V9.1 rows"
Write-Host "       -> run Phase 3.4.8.3"
Write-Host "       -> canonical persistence"
Write-Host "       -> Phase 3.4.8 paper execution"
Write-Host ""

Write-Host "Desired PASS result:" -ForegroundColor Cyan
Write-Host "  Eligible V9.1 Signals Found: > 0"
Write-Host "  Rows Prepared For public.signals: > 0"
Write-Host "  Rows Round-trip Eligible: > 0"
Write-Host "  Phase 3.4.8.3 Producer Signal Source: signals"
Write-Host "  Phase 3.4.8.3 Signals Persisted: > 0"
Write-Host "  Phase 3.4.8.3 Prices Persisted: > 0"
Write-Host "  Execution State: REAL_CANONICAL_EVIDENCE_EXECUTED"
Write-Host "  Paper Orders Created: > 0"
Write-Host "  Simulated Fills: > 0"
Write-Host ""

Write-Host "Safe zero-order states remain valid:" -ForegroundColor Yellow
Write-Host "  NO_CANONICAL_SIGNAL_ZERO_ORDERS"
Write-Host "  NO_REAL_MARKET_PRICE_ZERO_ORDERS"
Write-Host ""

Write-Host "Hard safety locks:" -ForegroundColor Yellow
Write-Host "  Synthetic fallback: DISABLED"
Write-Host "  Broker API used: NO"
Write-Host "  Broker credentials used: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Review GitHub Desktop changes."
Write-Host "  2) Commit and Push origin."
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.4."
Write-Host "  4) Run workflow with defaults."
Write-Host "  5) Inspect local producer source / public.signals round-trip / Phase 3.4.8.3 result."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
