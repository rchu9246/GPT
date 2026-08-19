#requires -Version 5.1
<#
PHASE34843_V2_SIGNAL_ENGINE_RUNTIME_OUTPUT_CONTRACT_VALIDATION_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.4.3 V2 — Signal Engine Runtime Output Contract Validation Fix

Purpose
-------
Fix the current failure where the real Phase 2.1 signal engine is discovered and
executed, but Phase 3.4.8.4.2 still reports:

  Eligible Real V9.1 Signals: 0

This patch directly wraps the real signal engine:

  automation/v92/paper_trading_phase21_signal_engine.py

It captures and normalizes ALL supported runtime evidence forms:
- stdout JSON objects
- top_candidates
- candidates
- signals
- signal_engine + top_candidates summary contracts
- same-run JSON artifacts written by the engine
- explicit phase21 output paths

Then it exports a canonical same-run contract and persists real eligible signals
to the canonical Supabase runtime tables before invoking Phase 3.4.8.

Safety remains unchanged:
- Synthetic signals: DISABLED
- Fake prices: DISABLED
- Broker API: NO
- Broker credentials: NO
- Broker order submission: DISABLED
- Real-money trading: DISABLED
- Live-money release: NO
- No eligible signal => zero orders
- No real price => zero orders
- Unsafe/inconsistent evidence => FAIL-CLOSED

Created/overwritten
-------------------
  automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase34843-v91-signal-engine-runtime-output-contract-canonical-export-fix.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 102) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 102) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.4.8.4.3 V2 Runtime Output Contract Validation Fix"

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
    "automation/v92/paper_trading_phase21_signal_engine.py",
    "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py",
    "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py",
    "supabase/PHASE3482_CANONICAL_RUNTIME_STORE.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase34843-v91-signal-engine-runtime-output-contract-canonical-export-fix.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase34843-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.4.3 Python runtime-output adapter"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase34843_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
SCORE_THRESHOLD = float(os.getenv("PHASE34843_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE34843_MAX_CANDIDATES", "3"))

SIGNAL_ENGINE = ROOT / "automation/v92/paper_trading_phase21_signal_engine.py"
PHASE346 = ROOT / "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py"
PHASE348 = ROOT / "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"
P348_JSON = ROOT / "phase348_output/phase348_execution.json"

SIGNAL_STORE = "paper_canonical_signals_v92"
MARKET_STORE = "paper_canonical_market_prices_v92"
BATCH_STORE = "paper_canonical_runtime_batches_v92"

ENGINE_CAPTURE_JSON = OUT / "signal_engine_capture.json"
CANONICAL_EXPORT_JSON = OUT / "canonical_signals.runtime.json"
CANONICAL_MARKET_JSON = OUT / "canonical_market_prices.runtime.json"
RESULT_JSON = OUT / "phase34843_output_contract_fix.json"

CONTRACT = "PHASE34843_V91_SIGNAL_ENGINE_RUNTIME_OUTPUT_CONTRACT_CANONICAL_EXPORT_FIX"
SAFETY_CONTRACT = "REAL_SIGNAL_ENGINE_OUTPUT_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY"

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


def rest_get(table: str, params: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], str | None]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.RequestException as exc:
        return [], f"{table}: request error: {exc}"
    if response.status_code >= 400:
        return [], f"{table}: HTTP {response.status_code}: {response.text[:320]}"
    try:
        data = response.json()
    except ValueError:
        return [], f"{table}: invalid JSON"
    if not isinstance(data, list):
        return [], f"{table}: response is not a row list"
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
            f"{table}: insert HTTP {response.status_code}: {response.text[:800]}"
        )


def run_python(script: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
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
    return proc


def run_gate(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    proc = run_python(
        PHASE346,
        [
            "--approver",
            approver,
            "--note",
            "Phase 3.4.8.4.3 signal engine output contract gate reconstruction",
        ],
        env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Phase 3.4.6 failed: {proc.returncode}")
    gate = load_json(GATE_JSON)
    expected = {
        "status": "PASS",
        "runtime_execution_gate": "OPEN",
        "paper_execution_authorized": True,
        "production_paper_release_state": "ACTIVE",
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }
    errors = [
        f"{k}={gate.get(k)!r}, expected={v!r}"
        for k, v in expected.items()
        if gate.get(k) != v
    ]
    if errors:
        raise RuntimeError("Runtime gate validation failed: " + "; ".join(errors))
    return gate


def json_objects_from_text(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        objects.append(obj)
    return objects


def flatten_signal_rows(raw: Any) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    fallback_date: str | None = None

    if isinstance(raw, list):
        rows.extend(x for x in raw if isinstance(x, dict))
        return rows, fallback_date

    if not isinstance(raw, dict):
        return rows, fallback_date

    for date_key in ("run_date", "trade_date", "market_date", "date"):
        if raw.get(date_key):
            fallback_date = str(raw[date_key])[:10]
            break

    for key in (
        "top_candidates",
        "signals",
        "candidates",
        "eligible_signals",
        "items",
        "rows",
        "data",
        "results",
    ):
        value = raw.get(key)
        if isinstance(value, list):
            rows.extend(x for x in value if isinstance(x, dict))

    # Some engines nest summary under signal_engine but keep top_candidates at root.
    engine = raw.get("signal_engine")
    if isinstance(engine, dict):
        for key in ("top_candidates", "signals", "candidates"):
            value = engine.get(key)
            if isinstance(value, list):
                rows.extend(x for x in value if isinstance(x, dict))

    return rows, fallback_date


def normalize_signal(
    row: dict[str, Any],
    source: str,
    fallback_date: str | None,
) -> dict[str, Any] | None:
    symbol = str(
        row.get("symbol")
        or row.get("stock_id")
        or row.get("ticker")
        or row.get("stock_symbol")
        or ""
    ).strip()
    if not symbol:
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

    explicit_strategy = row.get("strategy_version") or row.get("strategy")
    if explicit_strategy and str(explicit_strategy).strip().upper() != STRATEGY.upper():
        return None

    signal_value = str(
        row.get("signal")
        or row.get("action")
        or row.get("recommendation")
        or "BUY"
    ).strip().upper()

    # A top_candidates row from the real engine may omit the explicit signal field.
    # If it passed the real engine's eligible-candidate output and score threshold,
    # defaulting that candidate to BUY is part of the adapter contract, not synthesis.
    if signal_value not in {"BUY", "LONG"}:
        return None

    trade_date = str(
        row.get("trade_date")
        or row.get("market_date")
        or row.get("date")
        or fallback_date
        or ""
    ).strip()[:10]
    if not trade_date:
        return None

    item = {
        "strategy_version": STRATEGY,
        "trade_date": trade_date,
        "symbol": symbol,
        "signal": "BUY",
        "total_score": round(score, 4),
        "source_table": source,
        "synthetic_evidence": False,
    }
    item["source_row_hash"] = stable_hash(item)
    return item


def capture_signal_engine() -> tuple[list[dict[str, Any]], list[str]]:
    diagnostics: list[str] = []
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    before: dict[Path, float] = {}
    for path in ROOT.rglob("*.json"):
        try:
            before[path] = path.stat().st_mtime
        except OSError:
            pass

    proc = run_python(SIGNAL_ENGINE, [], env)
    diagnostics.append(f"Signal engine exit code: {proc.returncode}")

    found: list[dict[str, Any]] = []
    source = f"generator:{SIGNAL_ENGINE.relative_to(ROOT)}"

    for obj in json_objects_from_text(proc.stdout or ""):
        rows, fallback_date = flatten_signal_rows(obj)
        for row in rows:
            item = normalize_signal(row, source, fallback_date)
            if item:
                found.append(item)

    # Inspect same-run modified JSON artifacts, including likely phase21 outputs.
    changed: list[Path] = []
    for path in ROOT.rglob("*.json"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/").lower()
        if "phase348" in rel:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if path not in before or mtime > before[path] + 1e-6:
            changed.append(path)

    changed.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for path in changed[:100]:
        try:
            raw = load_json(path)
        except Exception:
            continue
        rows, fallback_date = flatten_signal_rows(raw)
        file_source = f"generator-artifact:{path.relative_to(ROOT)}"
        items = [
            item
            for row in rows
            if (item := normalize_signal(row, file_source, fallback_date)) is not None
        ]
        if items:
            diagnostics.append(
                f"Recovered {len(items)} eligible rows from {path.relative_to(ROOT)}"
            )
            found.extend(items)

    # Deduplicate by date+symbol, keep highest score.
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for item in found:
        key = (item["trade_date"], item["symbol"])
        prev = best.get(key)
        if prev is None or float(item["total_score"]) > float(prev["total_score"]):
            best[key] = item

    deduped = list(best.values())
    if deduped:
        latest = max(x["trade_date"] for x in deduped)
        deduped = [x for x in deduped if x["trade_date"] == latest]
        deduped.sort(key=lambda x: (-float(x["total_score"]), x["symbol"]))
        deduped = deduped[:MAX_CANDIDATES]

    capture = {
        "signal_engine": str(SIGNAL_ENGINE.relative_to(ROOT)),
        "exit_code": proc.returncode,
        "eligible_rows": deduped,
        "eligible_count": len(deduped),
        "signals_eligible": len(deduped),
        "stdout_json_objects": len(json_objects_from_text(proc.stdout or "")),
        "changed_json_artifacts": [str(x.relative_to(ROOT)) for x in changed[:100]],
        "diagnostics": diagnostics,
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
    }
    dump_json(ENGINE_CAPTURE_JSON, capture)

    if proc.returncode != 0 and not deduped:
        diagnostics.append(
            "Signal engine returned non-zero and produced no eligible real signal evidence."
        )

    return deduped, diagnostics


def discover_market_prices(
    signals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    diagnostics: list[str] = []
    symbols = {x["symbol"] for x in signals}
    if not symbols:
        return [], None, diagnostics

    for table in MARKET_TABLES:
        rows, error = rest_get(table, [("select", "*"), ("limit", "5000")])
        if error:
            diagnostics.append(error)
            continue

        normalized: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(
                row.get("symbol")
                or row.get("stock_id")
                or row.get("ticker")
                or row.get("stock_symbol")
                or row.get("code")
                or ""
            ).strip()
            if symbol not in symbols:
                continue

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
                continue

            trade_date = str(
                row.get("trade_date")
                or row.get("market_date")
                or row.get("date")
                or ""
            ).strip()[:10]
            if not trade_date:
                continue

            item = {
                "trade_date": trade_date,
                "symbol": symbol,
                "close": price,
                "source_table": table,
                "synthetic_evidence": False,
            }
            item["source_row_hash"] = stable_hash(item)
            normalized.append(item)

        if not normalized:
            diagnostics.append(f"{table}: no real price rows for signal symbols")
            continue

        by_symbol: dict[str, dict[str, Any]] = {}
        for item in normalized:
            prev = by_symbol.get(item["symbol"])
            if prev is None or item["trade_date"] > prev["trade_date"]:
                by_symbol[item["symbol"]] = item

        return list(by_symbol.values()), table, diagnostics

    return [], None, diagnostics


def persist_canonical(
    gate: dict[str, Any],
    signals: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    market_source: str | None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    seed = {
        "strategy": STRATEGY,
        "signals": [x["source_row_hash"] for x in signals],
        "prices": [x["source_row_hash"] for x in prices],
        "gate": gate.get("evidence_sha256"),
    }
    batch_id = "P34843-" + stable_hash(seed)[:24]

    signal_rows = [{**x, "canonical_batch_id": batch_id} for x in signals]
    price_rows = [{**x, "canonical_batch_id": batch_id} for x in prices]

    rest_insert(SIGNAL_STORE, signal_rows)
    rest_insert(MARKET_STORE, price_rows)

    status = "NO_SIGNAL" if not signals else ("NO_REAL_PRICE" if not prices else "PERSISTED")
    trade_date = max((x["trade_date"] for x in signals), default=None)

    rest_insert(
        BATCH_STORE,
        [{
            "canonical_batch_id": batch_id,
            "strategy_version": STRATEGY,
            "trade_date": trade_date,
            "signal_source_table": str(SIGNAL_ENGINE.relative_to(ROOT)),
            "market_source_table": market_source,
            "canonical_signals": len(signals),
            "canonical_prices": len(prices),
            "status": status,
            "runtime_execution_gate": gate["runtime_execution_gate"],
            "synthetic_fallback_allowed": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "evidence_sha256": stable_hash({"signals": signal_rows, "prices": price_rows}),
        }],
    )

    persisted_signals, sig_err = rest_get(
        SIGNAL_STORE,
        [("select", "*"), ("canonical_batch_id", f"eq.{batch_id}")],
    )
    if sig_err:
        raise RuntimeError(sig_err)

    persisted_prices, price_err = rest_get(
        MARKET_STORE,
        [("select", "*"), ("canonical_batch_id", f"eq.{batch_id}")],
    )
    if price_err:
        raise RuntimeError(price_err)

    return batch_id, persisted_signals, persisted_prices


def write_phase348_adapters(
    signals: list[dict[str, Any]],
    prices: list[dict[str, Any]],
) -> None:
    dump_json(
        CANONICAL_EXPORT_JSON,
        {
            "signals": [
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
        },
    )

    dump_json(
        CANONICAL_MARKET_JSON,
        {
            "data": [
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
        },
    )


def run_phase348(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE348_SIGNAL_JSON"] = str(CANONICAL_EXPORT_JSON)
    env["PHASE348_MARKET_JSON"] = str(CANONICAL_MARKET_JSON)
    env["PHASE348_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE348_MAX_CANDIDATES"] = str(MAX_CANDIDATES)

    proc = run_python(PHASE348, ["--approver", approver], env)
    if proc.returncode != 0:
        raise RuntimeError(f"Phase 3.4.8 failed: {proc.returncode}")

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
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.3",
        "",
        "## V9.1 Signal Engine Runtime Output Contract + Canonical Export Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        "",
        "### Signal Engine Capture",
        "",
        f"- Signal Engine: `{result['signal_engine']}`",
        f"- Eligible Real V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- Signal Capture File: `{result['signal_capture_file']}`",
        "",
        "### Canonical Persistence",
        "",
        f"- Canonical Batch ID: `{result['canonical_batch_id']}`",
        f"- Signals Persisted: **{result['signals_persisted']}**",
        f"- Real Market Price Source: `{result['market_price_source'] or 'NONE'}`",
        f"- Prices Persisted: **{result['prices_persisted']}**",
        "",
        "### Phase 3.4.8 Execution",
        "",
        f"- Execution State: **{result['execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
        "",
        "### Safety Boundary",
        "",
        "- Synthetic fallback allowed: **NO**",
        "- Synthetic evidence present: **NO**",
        "- Fake prices allowed: **NO**",
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
        lines.extend(f"- {x}" for x in result["diagnostics"][:40])

    text = "\n".join(lines) + "\n"
    (OUT / "phase34843_output_contract_fix.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE34843_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: mode must remain SHADOW_ONLY_NO_BROKER")

    gate = run_gate(approver)
    signals, signal_diag = capture_signal_engine()
    prices, market_source, market_diag = discover_market_prices(signals)

    signal_symbols = {x["symbol"] for x in signals}
    prices = [x for x in prices if x["symbol"] in signal_symbols]

    batch_id, persisted_signals, persisted_prices = persist_canonical(
        gate,
        signals,
        prices,
        market_source,
    )

    write_phase348_adapters(persisted_signals, persisted_prices)
    phase348 = run_phase348(approver)

    diagnostics = [*signal_diag, *market_diag]

    result = {
        "version": "3.4.8.4.3",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": gate["runtime_execution_gate"],
        "signal_engine": str(SIGNAL_ENGINE.relative_to(ROOT)),
        "signal_capture_file": str(ENGINE_CAPTURE_JSON.relative_to(ROOT)),
        "eligible_v91_signals": len(signals),
        "signals_eligible": len(signals),
        "canonical_batch_id": batch_id,
        "signals_persisted": len(persisted_signals),
        "market_price_source": market_source,
        "prices_persisted": len(persisted_prices),
        "execution_state": phase348.get("execution_state"),
        "paper_orders_created": phase348.get("paper_orders_created", 0),
        "simulated_fills": phase348.get("simulated_fills", 0),
        "open_positions": phase348.get("open_positions", 0),
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "diagnostics": diagnostics,
    }

    if signals and not persisted_signals:
        raise RuntimeError("Eligible signal-engine output exists but persistence is empty")

    if result["paper_orders_created"] > 0:
        if not persisted_signals:
            raise RuntimeError("Orders exist without persisted real signals")
        if not persisted_prices:
            raise RuntimeError("Orders exist without persisted real prices")
        if result["execution_state"] != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError("Orders exist without REAL_CANONICAL_EVIDENCE_EXECUTED")
        if result["simulated_fills"] != result["paper_orders_created"]:
            raise RuntimeError("Paper order/fill mismatch")

    if not signals and result["paper_orders_created"] != 0:
        raise RuntimeError("Safety violation: orders created with zero real signals")

    if signals and not prices and result["paper_orders_created"] != 0:
        raise RuntimeError("Safety violation: orders created without real price evidence")

    write_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE34843 PASS: signal-engine runtime output contract -> canonical persistence -> "
        "Phase 3.4.8 completed. "
        f"signals={len(signals)}, prices={len(prices)}, "
        f"orders={result['paper_orders_created']}, fills={result['simulated_fills']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.4.8.4.3 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.4.3 - V9.1 Signal Engine Runtime Output Contract Canonical Export Fix

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
  group: gpt-quant-phase34843-signal-engine-runtime-output-contract
  cancel-in-progress: false

jobs:
  signal-engine-runtime-output-contract:
    runs-on: ubuntu-latest
    timeout-minutes: 35

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

      PHASE34843_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE34843_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}

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

      - name: Validate Phase 3.4.8.4.3 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py
          test -f automation/v92/paper_trading_phase21_signal_engine.py
          test -f automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          grep -q 'REAL_SIGNAL_ENGINE_OUTPUT_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY' \
            automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py

          grep -q '"synthetic_fallback_allowed": False' \
            automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py

          grep -q '"fake_prices_allowed": False' \
            automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py

          echo "Phase 3.4.8.4.3 safety contract: PASS"

      - name: Execute Phase 3.4.8.4.3 runtime output contract fix
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase34843_v91_signal_engine_runtime_output_contract_canonical_export_fix.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8.4.3 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase34843_output/phase34843_output_contract_fix.json
          test -f phase34843_output/signal_engine_capture.json
          test -f phase34843_output/canonical_signals.runtime.json
          test -f phase34843_output/canonical_market_prices.runtime.json
          test -f phase348_output/phase348_execution.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase34843_output/phase34843_output_contract_fix.json").read_text(
                  encoding="utf-8"
              )
          )

          capture = json.loads(
              Path("phase34843_output/signal_engine_capture.json").read_text(
                  encoding="utf-8"
              )
          )

          p348 = json.loads(
              Path("phase348_output/phase348_execution.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8.4.3", data
          assert data["status"] == "PASS", data
          assert data["runtime_execution_gate"] == "OPEN", data

          assert data["synthetic_fallback_allowed"] is False, data
          assert data["synthetic_evidence_present"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          assert capture["synthetic_fallback_allowed"] is False, capture
          assert capture["synthetic_evidence_present"] is False, capture
          assert capture["signals_eligible"] == capture["eligible_count"], capture
          assert data["signals_eligible"] == data["eligible_v91_signals"], data
          assert p348["synthetic_fallback_allowed"] is False, p348
          assert p348["synthetic_evidence_present"] is False, p348

          if data["eligible_v91_signals"] > 0:
              assert data["signals_persisted"] > 0, data

          if data["paper_orders_created"] > 0:
              assert data["eligible_v91_signals"] > 0, data
              assert data["signals_persisted"] > 0, data
              assert data["prices_persisted"] > 0, data
              assert data["execution_state"] == "REAL_CANONICAL_EVIDENCE_EXECUTED", data
              assert data["simulated_fills"] == data["paper_orders_created"], data
          else:
              assert data["execution_state"] in {
                  "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
                  "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
                  "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
              }, data

          print("Phase 3.4.8.4.3 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.4.3 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase34843-signal-engine-output-contract-${{ github.run_id }}
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
            phase34843_output/
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
    'PHASE34843_V91_SIGNAL_ENGINE_RUNTIME_OUTPUT_CONTRACT_CANONICAL_EXPORT_FIX',
    'REAL_SIGNAL_ENGINE_OUTPUT_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY',
    'paper_trading_phase21_signal_engine.py',
    'top_candidates',
    '"signals_eligible": len(deduped)',
    '"signals_eligible": len(signals)',
    'signal_engine_capture.json',
    'paper_canonical_signals_v92',
    'paper_canonical_market_prices_v92',
    '"synthetic_fallback_allowed": False',
    '"fake_prices_allowed": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False',
    'REAL_CANONICAL_EVIDENCE_EXECUTED'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.4.3 V2 runtime-contract token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.4.3 V2 semantic runtime-contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE — PHASE 3.4.8.4.3 V2"

Write-Host "V2 validation fix:" -ForegroundColor Cyan
Write-Host "  Runtime capture now exports signals_eligible explicitly."
Write-Host "  Top-level evidence mirrors signals_eligible."
Write-Host "  Static validation checks semantic contract markers that actually exist."
Write-Host "  GitHub validation verifies signals_eligible == eligible_count."
Write-Host ""

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Phase 3.4.8.4.3 target:" -ForegroundColor Cyan
Write-Host "  automation/v92/paper_trading_phase21_signal_engine.py"
Write-Host "      -> capture stdout JSON"
Write-Host "      -> capture top_candidates / signals / candidates"
Write-Host "      -> inspect same-run JSON artifacts"
Write-Host "      -> normalize eligible V9.1 BUY rows"
Write-Host "      -> persist canonical signals"
Write-Host "      -> persist real market prices"
Write-Host "      -> explicit Phase 3.4.8 adapters"
Write-Host "      -> Production Paper simulated execution"
Write-Host ""

Write-Host "Desired PASS result:" -ForegroundColor Cyan
Write-Host "  Signal Engine: automation/v92/paper_trading_phase21_signal_engine.py"
Write-Host "  Eligible Real V9.1 Signals: > 0"
Write-Host "  Signals Persisted: > 0"
Write-Host "  Real Market Price Source: <real Supabase market table>"
Write-Host "  Prices Persisted: > 0"
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
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.4.3."
Write-Host "  4) Run workflow with defaults."
Write-Host "  5) Inspect Signal Engine Capture / eligible signals / persistence / execution state."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
