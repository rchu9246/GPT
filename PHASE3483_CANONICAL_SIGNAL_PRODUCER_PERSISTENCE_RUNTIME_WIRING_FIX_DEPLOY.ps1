#requires -Version 5.1
<#
PHASE3483_CANONICAL_SIGNAL_PRODUCER_PERSISTENCE_RUNTIME_WIRING_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.3 — Canonical Signal Producer -> Persistence Runtime Wiring Fix

Purpose
-------
Repair the broken data wiring observed after Phase 3.4.8.2:

  Runtime gate = OPEN
  but Canonical Signal Source = NONE
  and Canonical Signals Found = 0

This patch does NOT weaken any safety boundary. It explicitly wires:

  existing V9.1 signal producer / Supabase signal tables
  -> canonical normalized signal persistence
  -> canonical normalized market-price persistence
  -> Phase 3.4.8 explicit runtime JSON adapters
  -> Production Paper simulated execution

The patch is deliberately fail-safe:
- no synthetic fallback
- no fake prices
- no broker API
- no broker credentials
- no real orders
- no real-money trading
- no signal => zero orders
- no real price => zero orders
- unsafe gate => BLOCKED / FAIL-CLOSED

Created/overwritten
-------------------
  automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase3483-canonical-signal-producer-persistence-runtime-wiring-fix.yml

Required existing objects
-------------------------
  public.paper_canonical_signals_v92
  public.paper_canonical_market_prices_v92
  public.paper_canonical_runtime_batches_v92

These were created by Phase 3.4.8.2.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 94) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 94) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.4.8.3 Canonical Signal Producer Wiring Fix"

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
    "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py",
    "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py",
    "automation/v92/paper_trading_phase3482_canonical_signal_persistence_runtime_source_adapter.py",
    "supabase/PHASE3482_CANONICAL_RUNTIME_STORE.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase3483-canonical-signal-producer-persistence-runtime-wiring-fix.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase3483-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.3 Python wiring fix"

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
OUT = ROOT / "phase3483_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"

SCORE_THRESHOLD = float(os.getenv("PHASE3483_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE3483_MAX_CANDIDATES", "3"))
INITIAL_CASH = float(os.getenv("PHASE3483_INITIAL_CASH", "1000000"))
MAX_POSITION_PCT = float(os.getenv("PHASE3483_MAX_POSITION_PCT", "0.20"))
ROUND_LOT = int(os.getenv("PHASE3483_ROUND_LOT", "1000"))

PHASE346 = ROOT / "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py"
PHASE348 = ROOT / "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"
P348_JSON = ROOT / "phase348_output/phase348_execution.json"

SIGNAL_ADAPTER_JSON = OUT / "canonical_signals.runtime.json"
MARKET_ADAPTER_JSON = OUT / "canonical_market_prices.runtime.json"
RESULT_JSON = OUT / "phase3483_wiring_fix.json"

SIGNAL_STORE = "paper_canonical_signals_v92"
MARKET_STORE = "paper_canonical_market_prices_v92"
BATCH_STORE = "paper_canonical_runtime_batches_v92"

CONTRACT = "PHASE3483_CANONICAL_SIGNAL_PRODUCER_PERSISTENCE_RUNTIME_WIRING_FIX"
SAFETY_CONTRACT = "REAL_SIGNAL_PRODUCER_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY"

# Priority includes likely V9.1 / Phase 2.1 producer stores.
SIGNAL_TABLES = [
    "signals",
    "stock_signals",
    "trading_signals",
    "signal_history",
    "signals_v91",
    "strategy_signals",
    "paper_signals",
    "production_signals",
    "daily_signals",
]

MARKET_TABLES = [
    "market_data",
    "stock_prices",
    "daily_prices",
    "market_daily",
    "market_data_daily",
    "ohlcv_daily",
    "daily_market_data",
    "prices",
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


def run_python(script: Path, args: list[str], env: dict[str, str]) -> None:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
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
        raise RuntimeError(f"{script.name} failed with exit code {proc.returncode}")


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
        return [], f"{table}: HTTP {response.status_code}: {response.text[:240]}"

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
    headers["Prefer"] = "return=minimal,resolution=ignore-duplicates"
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.post(
        url,
        headers=headers,
        data=json.dumps(rows, ensure_ascii=False),
        timeout=20,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: persistence HTTP {response.status_code}: {response.text[:700]}"
        )


def run_gate(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    run_python(
        PHASE346,
        [
            "--approver",
            approver,
            "--note",
            "Phase 3.4.8.3 producer persistence runtime wiring gate reconstruction",
        ],
        env,
    )

    gate = load_json(GATE_JSON)

    expected = {
        "status": "PASS",
        "runtime_execution_gate": "OPEN",
        "paper_execution_authorized": True,
        "production_paper_release_state": "ACTIVE",
        "broker_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }

    errors = [
        f"{key}={gate.get(key)!r}, expected {expected_value!r}"
        for key, expected_value in expected.items()
        if gate.get(key) != expected_value
    ]

    if errors:
        raise RuntimeError("Runtime gate unsafe: " + "; ".join(errors))

    return gate


def normalize_symbol(row: dict[str, Any]) -> str:
    return str(
        row.get("symbol")
        or row.get("stock_id")
        or row.get("ticker")
        or row.get("stock_symbol")
        or row.get("code")
        or ""
    ).strip()


def normalize_date(row: dict[str, Any]) -> str:
    return str(
        row.get("trade_date")
        or row.get("market_date")
        or row.get("date")
        or row.get("priced_at")
        or row.get("signal_date")
        or ""
    ).strip()[:10]


def normalize_signal(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    symbol = normalize_symbol(row)
    trade_date = normalize_date(row)

    if not symbol or not trade_date:
        return None

    raw_signal = str(
        row.get("signal")
        or row.get("action")
        or row.get("recommendation")
        or row.get("side")
        or ""
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

    normalized = {
        "strategy_version": STRATEGY,
        "trade_date": trade_date,
        "symbol": symbol,
        "signal": "BUY",
        "total_score": round(score, 4),
        "source_table": source,
        "synthetic_evidence": False,
    }
    normalized["source_row_hash"] = stable_hash(normalized)
    return normalized


def normalize_market(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    symbol = normalize_symbol(row)
    trade_date = normalize_date(row)

    if not symbol or not trade_date:
        return None

    price = None
    for key in (
        "close",
        "close_price",
        "price",
        "last_price",
        "market_price",
        "reference_price",
    ):
        if row.get(key) is None:
            continue
        try:
            value = float(row[key])
        except (TypeError, ValueError):
            continue
        if value > 0:
            price = value
            break

    if price is None:
        return None

    normalized = {
        "trade_date": trade_date,
        "symbol": symbol,
        "close": price,
        "source_table": source,
        "synthetic_evidence": False,
    }
    normalized["source_row_hash"] = stable_hash(normalized)
    return normalized


def discover_signal_producer() -> tuple[list[dict[str, Any]], str | None, list[str]]:
    diagnostics: list[str] = []

    for table in SIGNAL_TABLES:
        # Do not require a particular column in REST order. Query a bounded sample,
        # normalize locally, then choose the latest eligible trade_date.
        rows, error = rest_get(
            table,
            [
                ("select", "*"),
                ("limit", "500"),
            ],
        )

        if error:
            diagnostics.append(error)
            continue

        normalized = [
            item
            for row in rows
            if (item := normalize_signal(row, table)) is not None
        ]

        if not normalized:
            diagnostics.append(f"{table}: table readable but no eligible {STRATEGY} BUY rows >= {SCORE_THRESHOLD}")
            continue

        latest = max(x["trade_date"] for x in normalized)
        latest_rows = [x for x in normalized if x["trade_date"] == latest]
        latest_rows.sort(key=lambda x: (-float(x["total_score"]), x["symbol"]))

        return latest_rows[:MAX_CANDIDATES], table, diagnostics

    return [], None, diagnostics


def discover_real_market_prices(
    signals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    diagnostics: list[str] = []
    wanted = {x["symbol"] for x in signals}

    for table in MARKET_TABLES:
        rows, error = rest_get(
            table,
            [
                ("select", "*"),
                ("limit", "3000"),
            ],
        )

        if error:
            diagnostics.append(error)
            continue

        normalized = [
            item
            for row in rows
            if (item := normalize_market(row, table)) is not None
            and item["symbol"] in wanted
        ]

        if not normalized:
            diagnostics.append(f"{table}: readable but no price rows for canonical symbols")
            continue

        by_symbol: dict[str, dict[str, Any]] = {}

        for row in normalized:
            existing = by_symbol.get(row["symbol"])
            if existing is None or row["trade_date"] > existing["trade_date"]:
                by_symbol[row["symbol"]] = row

        return list(by_symbol.values()), table, diagnostics

    return [], None, diagnostics


def persist_roundtrip(
    gate: dict[str, Any],
    signals: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    signal_source: str | None,
    market_source: str | None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    seed = {
        "strategy": STRATEGY,
        "signals": [x["source_row_hash"] for x in signals],
        "prices": [x["source_row_hash"] for x in prices],
        "gate": gate.get("evidence_sha256"),
    }
    batch_id = "P3483-" + stable_hash(seed)[:24]

    signal_rows = [{**x, "canonical_batch_id": batch_id} for x in signals]
    price_rows = [{**x, "canonical_batch_id": batch_id} for x in prices]

    rest_insert(SIGNAL_STORE, signal_rows)
    rest_insert(MARKET_STORE, price_rows)

    if not signals:
        batch_status = "NO_SIGNAL"
    elif not prices:
        batch_status = "NO_REAL_PRICE"
    else:
        batch_status = "PERSISTED"

    batch_trade_date = max((x["trade_date"] for x in signals), default=None)

    rest_insert(
        BATCH_STORE,
        [{
            "canonical_batch_id": batch_id,
            "strategy_version": STRATEGY,
            "trade_date": batch_trade_date,
            "signal_source_table": signal_source,
            "market_source_table": market_source,
            "canonical_signals": len(signals),
            "canonical_prices": len(prices),
            "status": batch_status,
            "runtime_execution_gate": gate["runtime_execution_gate"],
            "synthetic_fallback_allowed": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "evidence_sha256": stable_hash({
                "signals": signal_rows,
                "prices": price_rows,
            }),
        }],
    )

    persisted_signals, signal_error = rest_get(
        SIGNAL_STORE,
        [
            ("select", "*"),
            ("canonical_batch_id", f"eq.{batch_id}"),
        ],
    )
    if signal_error:
        raise RuntimeError(signal_error)

    persisted_prices, market_error = rest_get(
        MARKET_STORE,
        [
            ("select", "*"),
            ("canonical_batch_id", f"eq.{batch_id}"),
        ],
    )
    if market_error:
        raise RuntimeError(market_error)

    return batch_id, persisted_signals, persisted_prices


def create_phase348_adapters(
    signals: list[dict[str, Any]],
    prices: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signal_payload = [
        {
            "symbol": row["symbol"],
            "trade_date": row["trade_date"],
            "strategy_version": row["strategy_version"],
            "total_score": float(row["total_score"]),
            "signal": row["signal"],
            "canonical_batch_id": row["canonical_batch_id"],
            "source": f"supabase:{SIGNAL_STORE}",
            "synthetic_evidence": False,
        }
        for row in signals
    ]

    market_payload = [
        {
            "symbol": row["symbol"],
            "market_date": row["trade_date"],
            "close": float(row["close"]),
            "canonical_batch_id": row["canonical_batch_id"],
            "source": f"supabase:{MARKET_STORE}",
            "synthetic_evidence": False,
        }
        for row in prices
    ]

    dump_json(SIGNAL_ADAPTER_JSON, {"signals": signal_payload})
    dump_json(MARKET_ADAPTER_JSON, {"data": market_payload})
    return signal_payload, market_payload


def run_phase348(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    env["PHASE348_SIGNAL_JSON"] = str(SIGNAL_ADAPTER_JSON)
    env["PHASE348_MARKET_JSON"] = str(MARKET_ADAPTER_JSON)

    env["PHASE348_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE348_MAX_CANDIDATES"] = str(MAX_CANDIDATES)
    env["PHASE348_INITIAL_CASH"] = str(INITIAL_CASH)
    env["PHASE348_MAX_POSITION_PCT"] = str(MAX_POSITION_PCT)
    env["PHASE348_ROUND_LOT"] = str(ROUND_LOT)

    run_python(PHASE348, ["--approver", approver], env)

    result = load_json(P348_JSON)

    if result.get("status") != "PASS":
        raise RuntimeError("Phase 3.4.8 did not PASS")

    if result.get("synthetic_fallback_allowed") is not False:
        raise RuntimeError("Synthetic fallback violation")

    if result.get("synthetic_evidence_present") is not False:
        raise RuntimeError("Synthetic evidence violation")

    return result


def write_summary(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = stable_hash(result)
    dump_json(RESULT_JSON, result)

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.3",
        "",
        "## Canonical Signal Producer -> Persistence Runtime Wiring Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Wiring Contract: **{result['wiring_contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        "",
        "### Producer Discovery",
        "",
        f"- Producer Signal Source: `{result['producer_signal_source'] or 'NONE'}`",
        f"- Producer Market Source: `{result['producer_market_source'] or 'NONE'}`",
        f"- Eligible Producer Signals: **{result['producer_signals_found']}**",
        f"- Real Prices Found: **{result['producer_prices_found']}**",
        "",
        "### Persistence Round-trip",
        "",
        f"- Canonical Batch ID: `{result['canonical_batch_id']}`",
        f"- Signals Persisted: **{result['signals_persisted']}**",
        f"- Prices Persisted: **{result['prices_persisted']}**",
        f"- Runtime Signal Source: `supabase:{SIGNAL_STORE}`",
        f"- Runtime Market Source: `supabase:{MARKET_STORE}`",
        "",
        "### Phase 3.4.8 Execution",
        "",
        f"- Execution State: **{result['phase348_execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
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
        (
            "- Fail-closed triggered: "
            f"**{'YES' if result['fail_closed_triggered'] else 'NO'}**"
        ),
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    if result.get("diagnostics"):
        lines.extend(["", "### Producer Diagnostics", ""])
        lines.extend(f"- {x}" for x in result["diagnostics"][:30])

    text = "\n".join(lines) + "\n"
    (OUT / "phase3483_wiring_fix.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE3483_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: mode must remain SHADOW_ONLY_NO_BROKER")

    gate = run_gate(approver)

    signals, signal_source, signal_diag = discover_signal_producer()
    diagnostics = list(signal_diag)

    prices: list[dict[str, Any]] = []
    market_source: str | None = None

    if signals:
        prices, market_source, market_diag = discover_real_market_prices(signals)
        diagnostics.extend(market_diag)

    # Important alignment: persist only market prices for canonical signal symbols.
    signal_symbols = {x["symbol"] for x in signals}
    prices = [x for x in prices if x["symbol"] in signal_symbols]

    batch_id, persisted_signals, persisted_prices = persist_roundtrip(
        gate,
        signals,
        prices,
        signal_source,
        market_source,
    )

    create_phase348_adapters(persisted_signals, persisted_prices)
    phase348 = run_phase348(approver)

    result = {
        "version": "3.4.8.3",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "wiring_contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": gate["runtime_execution_gate"],
        "producer_signal_source": signal_source,
        "producer_market_source": market_source,
        "producer_signals_found": len(signals),
        "producer_prices_found": len(prices),
        "canonical_batch_id": batch_id,
        "signals_persisted": len(persisted_signals),
        "prices_persisted": len(persisted_prices),
        "phase348_execution_state": phase348.get("execution_state"),
        "paper_orders_created": phase348.get("paper_orders_created", 0),
        "simulated_fills": phase348.get("simulated_fills", 0),
        "open_positions": phase348.get("open_positions", 0),
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": False,
        "diagnostics": diagnostics,
    }

    # Strong consistency guards.
    if result["paper_orders_created"] > 0:
        if result["signals_persisted"] <= 0:
            raise RuntimeError("Orders exist without persisted signals")
        if result["prices_persisted"] <= 0:
            raise RuntimeError("Orders exist without persisted real prices")
        if result["phase348_execution_state"] != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError("Non-zero orders without REAL_CANONICAL_EVIDENCE_EXECUTED")

    if result["producer_signals_found"] == 0:
        if result["paper_orders_created"] != 0:
            raise RuntimeError("Safety violation: orders created without producer signals")

    if result["producer_prices_found"] == 0:
        if result["paper_orders_created"] != 0:
            raise RuntimeError("Safety violation: orders created without real prices")

    for order in phase348.get("orders", []):
        if order.get("synthetic_evidence") is not False:
            raise RuntimeError("Synthetic order detected")
        if order.get("broker_submitted") is not False:
            raise RuntimeError("Broker submission detected")
        if order.get("real_money") is not False:
            raise RuntimeError("Real-money order detected")

    write_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE3483 PASS: producer->persistence->runtime wiring complete. "
        f"producer_signals={len(signals)}, producer_prices={len(prices)}, "
        f"persisted_signals={len(persisted_signals)}, persisted_prices={len(persisted_prices)}, "
        f"orders={result['paper_orders_created']}, fills={result['simulated_fills']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.4.8.3 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.3 - Canonical Signal Producer Persistence Runtime Wiring Fix

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
        description: Maximum canonical signals per run
        required: true
        default: "3"
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase3483-producer-persistence-runtime-wiring
  cancel-in-progress: false

jobs:
  producer-persistence-runtime-wiring:
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

      - name: Validate Phase 3.4.8.3 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py
          test -f automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py
          test -f supabase/PHASE3482_CANONICAL_RUNTIME_STORE.sql

          grep -q 'REAL_SIGNAL_PRODUCER_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY' \
            automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py

          grep -q '"synthetic_fallback_allowed": False' \
            automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py

          echo "Phase 3.4.8.3 safety contract: PASS"

      - name: Execute Phase 3.4.8.3 producer wiring fix
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase3483_canonical_signal_producer_persistence_runtime_wiring_fix.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8.3 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase3483_output/phase3483_wiring_fix.json
          test -f phase3483_output/canonical_signals.runtime.json
          test -f phase3483_output/canonical_market_prices.runtime.json
          test -f phase348_output/phase348_execution.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase3483_output/phase3483_wiring_fix.json").read_text(
                  encoding="utf-8"
              )
          )

          p348 = json.loads(
              Path("phase348_output/phase348_execution.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8.3", data
          assert data["status"] == "PASS", data
          assert data["runtime_execution_gate"] == "OPEN", data
          assert data["canonical_batch_id"], data

          assert data["synthetic_fallback_allowed"] is False, data
          assert data["synthetic_evidence_present"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data
          assert data["fail_closed_triggered"] is False, data

          assert p348["synthetic_fallback_allowed"] is False, p348
          assert p348["synthetic_evidence_present"] is False, p348

          if data["paper_orders_created"] > 0:
              assert data["producer_signals_found"] > 0, data
              assert data["producer_prices_found"] > 0, data
              assert data["signals_persisted"] > 0, data
              assert data["prices_persisted"] > 0, data
              assert data["phase348_execution_state"] == "REAL_CANONICAL_EVIDENCE_EXECUTED", data
              assert data["simulated_fills"] == data["paper_orders_created"], data
          else:
              assert data["phase348_execution_state"] in {
                  "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
                  "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
                  "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
              }, data

          for order in p348.get("orders", []):
              assert order["synthetic_evidence"] is False, order
              assert order["broker_submitted"] is False, order
              assert order["real_money"] is False, order

          print("Phase 3.4.8.3 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.3 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3483-producer-runtime-wiring-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
            phase345_output/
            phase3451_output/
            phase346_output/
            phase348_output/
            phase3482_output/
            phase3483_output/
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
    'PHASE3483_CANONICAL_SIGNAL_PRODUCER_PERSISTENCE_RUNTIME_WIRING_FIX',
    'REAL_SIGNAL_PRODUCER_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY',
    'paper_canonical_signals_v92',
    'paper_canonical_market_prices_v92',
    '"synthetic_fallback_allowed": False',
    '"synthetic_evidence_present": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False',
    'REAL_CANONICAL_EVIDENCE_EXECUTED',
    'NO_CANONICAL_SIGNAL_ZERO_ORDERS',
    'NO_REAL_MARKET_PRICE_ZERO_ORDERS'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.3 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.3 static contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Phase 3.4.8.3 wiring target:" -ForegroundColor Cyan
Write-Host "  V9.1 / Phase 2.1 producer tables"
Write-Host "       -> normalized real BUY signals"
Write-Host "       -> normalized real market prices"
Write-Host "       -> Supabase canonical persistence"
Write-Host "       -> persistence round-trip"
Write-Host "       -> Phase 3.4.8 explicit runtime adapters"
Write-Host "       -> Production Paper simulated execution"
Write-Host ""

Write-Host "Desired PASS result:" -ForegroundColor Cyan
Write-Host "  Producer Signal Source: <real Supabase table>"
Write-Host "  Producer Market Source: <real Supabase table>"
Write-Host "  Eligible Producer Signals: > 0"
Write-Host "  Real Prices Found: > 0"
Write-Host "  Signals Persisted: > 0"
Write-Host "  Prices Persisted: > 0"
Write-Host "  Execution State: REAL_CANONICAL_EVIDENCE_EXECUTED"
Write-Host "  Paper Orders Created: > 0"
Write-Host "  Simulated Fills: > 0"
Write-Host ""

Write-Host "Safe zero-order states are still valid:" -ForegroundColor Yellow
Write-Host "  NO_CANONICAL_SIGNAL_ZERO_ORDERS"
Write-Host "  NO_REAL_MARKET_PRICE_ZERO_ORDERS"
Write-Host ""

Write-Host "Hard safety locks:" -ForegroundColor Yellow
Write-Host "  Synthetic fallback: DISABLED"
Write-Host "  Synthetic evidence: DISABLED"
Write-Host "  Broker API used: NO"
Write-Host "  Broker credentials used: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Review GitHub Desktop changes."
Write-Host "  2) Commit and Push origin."
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.3."
Write-Host "  4) Run workflow with defaults."
Write-Host "  5) Inspect Producer Signal Source / Producer Market Source / execution state."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
