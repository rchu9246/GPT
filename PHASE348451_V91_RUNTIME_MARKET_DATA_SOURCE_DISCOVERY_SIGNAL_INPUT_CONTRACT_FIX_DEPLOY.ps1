#requires -Version 5.1
<#
PHASE348451_V91_RUNTIME_MARKET_DATA_SOURCE_DISCOVERY_SIGNAL_INPUT_CONTRACT_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.4.5.1 — V9.1 Runtime Market Data Source Discovery + Signal Input Contract Fix

Purpose
-------
Phase 3.4.8.4.5 proved the downstream paper execution is behaving safely:
no canonical signal => zero orders.

This patch moves one layer upstream and makes the market-data discovery /
signal-input contract explicit and diagnosable.

It does all of the following in ONE GitHub Actions runner:
  1) discovers readable Supabase market-data tables;
  2) profiles each table's actual column schema and usable OHLCV coverage;
  3) selects the strongest real market-data source;
  4) normalizes symbol/date/OHLCV aliases into one canonical market snapshot;
  5) discovers the real active-stock universe when available;
  6) exports multiple Phase 2.1 input aliases;
  7) executes the real V9.1 signal engine;
  8) captures the signal engine's real runtime payload;
  9) reports market rows, history depth, latest date, stocks scanned,
     top symbol/score, and signals_eligible;
 10) persists real eligible V9.1 signals + matching real prices;
 11) runs Phase 3.4.8 only from real canonical evidence.

Safety
------
- Synthetic market data: DISABLED
- Synthetic signals: DISABLED
- Fake prices: DISABLED
- Broker API: NO
- Broker credentials: NO
- Broker order submission: DISABLED
- Real-money trading: DISABLED
- Live-money release: NO
- No real evidence => zero orders / fail-closed

Created/overwritten
-------------------
  automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase348451-v91-runtime-market-data-source-discovery-signal-input-contract-fix.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 106) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 106) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.4.8.4.5.1 Market Source Discovery + Signal Input Contract Fix"

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

$pythonTarget = "automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase348451-v91-runtime-market-data-source-discovery-signal-input-contract-fix.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase348451-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.4.5.1 Python source-discovery fix"

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
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase348451_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
SCORE_THRESHOLD = float(os.getenv("PHASE348451_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE348451_MAX_CANDIDATES", "3"))
MAX_ROWS_PER_TABLE = int(os.getenv("PHASE348451_MAX_ROWS_PER_TABLE", "5000"))

SIGNAL_ENGINE = ROOT / "automation/v92/paper_trading_phase21_signal_engine.py"
PHASE346 = ROOT / "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py"
PHASE348 = ROOT / "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"
P348_JSON = ROOT / "phase348_output/phase348_execution.json"

SIGNAL_STORE = "paper_canonical_signals_v92"
MARKET_STORE = "paper_canonical_market_prices_v92"
BATCH_STORE = "paper_canonical_runtime_batches_v92"

SOURCE_PROFILE_JSON = OUT / "market_source_profiles.json"
CANONICAL_MARKET_INPUT = OUT / "canonical_market_input.json"
SIGNAL_STDOUT = OUT / "signal_engine.stdout.txt"
SIGNAL_STDERR = OUT / "signal_engine.stderr.txt"
SIGNAL_CAPTURE = OUT / "signal_engine_input_contract_capture.json"
CANONICAL_SIGNALS = OUT / "canonical_signals.runtime.json"
CANONICAL_MARKET = OUT / "canonical_market_prices.runtime.json"
RESULT_JSON = OUT / "phase348451_signal_input_contract_fix.json"

CONTRACT = "PHASE348451_V91_RUNTIME_MARKET_DATA_SOURCE_DISCOVERY_SIGNAL_INPUT_CONTRACT_FIX"
SAFETY_CONTRACT = "REAL_MARKET_SOURCE_DISCOVERY_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY"

MARKET_TABLES = [
    "market_data",
    "daily_market_data",
    "market_data_daily",
    "stock_prices",
    "daily_prices",
    "ohlcv_daily",
    "market_daily",
    "prices",
    "tw_stock_daily",
    "stock_daily_prices",
]

ACTIVE_STOCK_TABLES = [
    "stocks",
    "stock_master",
    "stock_universe",
    "active_stocks",
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


def first_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if mapping.get(key) is not None:
            return mapping[key]
    return None


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
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=25,
        )
    except requests.RequestException as exc:
        return [], f"{table}: request error: {exc}"

    if response.status_code >= 400:
        return [], f"{table}: HTTP {response.status_code}: {response.text[:360]}"

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
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: insert HTTP {response.status_code}: {response.text[:900]}"
        )


def run_python(
    script: Path,
    args: list[str],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )


def emit_process(proc: subprocess.CompletedProcess[str]) -> None:
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(
            proc.stderr,
            file=sys.stderr,
            end="" if proc.stderr.endswith("\n") else "\n",
        )


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
            "Phase 3.4.8.4.5.1 market-source discovery signal-input contract",
        ],
        env,
    )
    emit_process(proc)

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
        f"{key}={gate.get(key)!r}, expected={value!r}"
        for key, value in expected.items()
        if gate.get(key) != value
    ]

    if errors:
        raise RuntimeError("Runtime gate validation failed: " + "; ".join(errors))

    return gate


def normalize_market_row(
    row: dict[str, Any],
    source: str,
) -> dict[str, Any] | None:
    symbol = str(
        first_value(
            row,
            (
                "symbol",
                "stock_id",
                "ticker",
                "stock_symbol",
                "code",
                "security_id",
                "stock_no",
            ),
        )
        or ""
    ).strip()

    trade_date = str(
        first_value(
            row,
            (
                "trade_date",
                "market_date",
                "date",
                "trading_date",
            ),
        )
        or ""
    ).strip()[:10]

    close_raw = first_value(
        row,
        (
            "close",
            "close_price",
            "closing_price",
            "price",
            "last_price",
            "market_price",
            "reference_price",
        ),
    )

    if not symbol or not trade_date or close_raw is None:
        return None

    try:
        close = float(close_raw)
    except (TypeError, ValueError):
        return None

    if close <= 0:
        return None

    item: dict[str, Any] = {
        "symbol": symbol,
        "trade_date": trade_date,
        "close": close,
        "source_table": source,
        "synthetic_evidence": False,
    }

    optional_fields = {
        "open": ("open", "open_price", "opening_price"),
        "high": ("high", "high_price"),
        "low": ("low", "low_price"),
        "volume": ("volume", "trade_volume", "trading_volume", "shares"),
    }

    for target, aliases in optional_fields.items():
        raw = first_value(row, aliases)
        if raw is None:
            continue
        try:
            item[target] = float(raw)
        except (TypeError, ValueError):
            pass

    item["source_row_hash"] = stable_hash(item)
    return item


def profile_market_table(
    table: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows, error = rest_get(
        table,
        [
            ("select", "*"),
            ("limit", str(MAX_ROWS_PER_TABLE)),
        ],
    )

    profile: dict[str, Any] = {
        "table": table,
        "readable": error is None,
        "error": error,
        "raw_rows": len(rows),
        "usable_rows": 0,
        "symbols": 0,
        "latest_market_date": None,
        "oldest_market_date": None,
        "has_open": False,
        "has_high": False,
        "has_low": False,
        "has_volume": False,
        "score": -1,
    }

    if error:
        return profile, []

    normalized = [
        item
        for row in rows
        if (item := normalize_market_row(row, table)) is not None
    ]

    if not normalized:
        return profile, []

    symbols = {x["symbol"] for x in normalized}
    dates = [x["trade_date"] for x in normalized]

    profile["usable_rows"] = len(normalized)
    profile["symbols"] = len(symbols)
    profile["latest_market_date"] = max(dates)
    profile["oldest_market_date"] = min(dates)
    profile["has_open"] = any("open" in x for x in normalized)
    profile["has_high"] = any("high" in x for x in normalized)
    profile["has_low"] = any("low" in x for x in normalized)
    profile["has_volume"] = any("volume" in x for x in normalized)

    # Prefer deeper history, more symbols, latest data, and fuller OHLCV.
    profile["score"] = (
        min(profile["usable_rows"], 5000)
        + profile["symbols"] * 200
        + (100 if profile["has_open"] else 0)
        + (100 if profile["has_high"] else 0)
        + (100 if profile["has_low"] else 0)
        + (200 if profile["has_volume"] else 0)
    )

    return profile, normalized


def discover_best_market_source() -> tuple[
    list[dict[str, Any]],
    str | None,
    list[dict[str, Any]],
]:
    profiles: list[dict[str, Any]] = []
    normalized_by_table: dict[str, list[dict[str, Any]]] = {}

    for table in MARKET_TABLES:
        profile, normalized = profile_market_table(table)
        profiles.append(profile)
        normalized_by_table[table] = normalized

    dump_json(SOURCE_PROFILE_JSON, profiles)

    usable = [
        p
        for p in profiles
        if p["readable"] and p["usable_rows"] > 0
    ]

    if not usable:
        return [], None, profiles

    usable.sort(
        key=lambda p: (
            p["score"],
            p["latest_market_date"] or "",
            p["usable_rows"],
        ),
        reverse=True,
    )

    best = usable[0]
    return normalized_by_table[best["table"]], best["table"], profiles


def discover_active_symbols(
    market_rows: list[dict[str, Any]],
) -> tuple[list[str], str]:
    for table in ACTIVE_STOCK_TABLES:
        rows, error = rest_get(
            table,
            [
                ("select", "*"),
                ("limit", "1000"),
            ],
        )

        if error:
            continue

        symbols: list[str] = []

        for row in rows:
            active_raw = first_value(
                row,
                ("active", "is_active", "enabled"),
            )

            if active_raw is not None:
                if isinstance(active_raw, bool) and not active_raw:
                    continue
                if isinstance(active_raw, (int, float)) and not bool(active_raw):
                    continue
                if isinstance(active_raw, str) and active_raw.strip().lower() in {
                    "false",
                    "0",
                    "no",
                    "inactive",
                    "disabled",
                }:
                    continue

            symbol = str(
                first_value(
                    row,
                    (
                        "symbol",
                        "stock_id",
                        "ticker",
                        "stock_symbol",
                        "code",
                        "stock_no",
                    ),
                )
                or ""
            ).strip()

            if symbol:
                symbols.append(symbol)

        if symbols:
            return sorted(set(symbols)), table

    return sorted({x["symbol"] for x in market_rows}), "derived_from_market_source"


def build_market_snapshot(
    market_rows: list[dict[str, Any]],
    market_source: str,
    active_symbols: list[str],
) -> dict[str, Any]:
    active = set(active_symbols)

    filtered = [
        row
        for row in market_rows
        if not active or row["symbol"] in active
    ]

    filtered.sort(key=lambda x: (x["symbol"], x["trade_date"]))

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in filtered:
        by_symbol[row["symbol"]].append(row)

    latest_market_date = max(
        (x["trade_date"] for x in filtered),
        default=None,
    )

    per_symbol: list[dict[str, Any]] = []

    for symbol, rows in sorted(by_symbol.items()):
        rows = sorted(rows, key=lambda x: x["trade_date"])

        per_symbol.append(
            {
                "symbol": symbol,
                "history_rows": len(rows),
                "oldest_market_date": rows[0]["trade_date"],
                "latest_market_date": rows[-1]["trade_date"],
                "latest_close": rows[-1]["close"],
            }
        )

    payload = {
        "version": "3.4.8.4.5.1",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "market_data_source": market_source,
        "synthetic_market_data": False,
        "active_symbols": active_symbols,
        "active_stocks": len(active_symbols),
        "stocks_with_history": len(by_symbol),
        "rows_scanned": len(filtered),
        "latest_market_date": latest_market_date,
        "per_symbol": per_symbol,
        "market_data": filtered,
        "rows": filtered,
        "data": filtered,
    }

    dump_json(CANONICAL_MARKET_INPUT, payload)
    return payload


def json_objects_from_text(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    seen: set[tuple[int, int]] = set()

    for idx, char in enumerate(text):
        if char not in "[{":
            continue

        try:
            obj, end = decoder.raw_decode(text[idx:])
        except Exception:
            continue

        marker = (idx, idx + end)

        if marker in seen:
            continue

        seen.add(marker)
        objects.append(obj)

    return objects


def recursive_values(obj: Any, keys: set[str]) -> list[Any]:
    values: list[Any] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys:
                values.append(value)
            values.extend(recursive_values(value, keys))

    elif isinstance(obj, list):
        for item in obj:
            values.extend(recursive_values(item, keys))

    return values


def recursive_candidate_rows(
    obj: Any,
    fallback_date: str | None = None,
    fallback_strategy: str | None = None,
) -> list[tuple[dict[str, Any], str | None, str | None]]:
    found: list[tuple[dict[str, Any], str | None, str | None]] = []

    if isinstance(obj, dict):
        current_date = fallback_date
        current_strategy = fallback_strategy

        date_value = first_value(
            obj,
            ("run_date", "trade_date", "market_date", "date"),
        )
        if date_value:
            current_date = str(date_value)[:10]

        strategy_value = first_value(
            obj,
            ("strategy_version", "strategy"),
        )
        if strategy_value:
            current_strategy = str(strategy_value)

        if set(obj).intersection(
            {
                "symbol",
                "stock_id",
                "ticker",
                "stock_symbol",
                "code",
                "total_score",
                "score",
                "signal",
                "action",
                "recommendation",
            }
        ):
            found.append(
                (obj, current_date, current_strategy)
            )

        for value in obj.values():
            found.extend(
                recursive_candidate_rows(
                    value,
                    current_date,
                    current_strategy,
                )
            )

    elif isinstance(obj, list):
        for item in obj:
            found.extend(
                recursive_candidate_rows(
                    item,
                    fallback_date,
                    fallback_strategy,
                )
            )

    return found


def normalize_signal_candidate(
    row: dict[str, Any],
    fallback_date: str | None,
    fallback_strategy: str | None,
    source: str,
) -> dict[str, Any] | None:
    symbol = str(
        first_value(
            row,
            (
                "symbol",
                "stock_id",
                "ticker",
                "stock_symbol",
                "code",
            ),
        )
        or ""
    ).strip()

    if not symbol:
        return None

    score_raw = first_value(
        row,
        (
            "total_score",
            "score",
            "signal_score",
            "final_score",
            "composite_score",
            "ranking_score",
        ),
    )

    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        return None

    if score < SCORE_THRESHOLD:
        return None

    strategy = str(
        first_value(row, ("strategy_version", "strategy"))
        or fallback_strategy
        or STRATEGY
    ).strip()

    if strategy.upper() != STRATEGY.upper():
        return None

    explicit_signal = first_value(
        row,
        (
            "signal",
            "action",
            "recommendation",
            "side",
        ),
    )

    if explicit_signal is not None:
        signal = str(explicit_signal).strip().upper()
        if signal not in {"BUY", "LONG"}:
            return None
    else:
        signal = "BUY"

    trade_date = str(
        first_value(
            row,
            ("trade_date", "market_date", "date"),
        )
        or fallback_date
        or ""
    ).strip()[:10]

    if not trade_date:
        return None

    item = {
        "strategy_version": STRATEGY,
        "trade_date": trade_date,
        "symbol": symbol,
        "signal": signal,
        "total_score": round(score, 4),
        "source_table": source,
        "synthetic_evidence": False,
    }
    item["source_row_hash"] = stable_hash(item)
    return item


def execute_signal_engine(
    market_snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    env = os.environ.copy()

    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    # Multiple explicit aliases for legacy/alternate Phase 2.1 input contracts.
    snapshot_path = str(CANONICAL_MARKET_INPUT)

    for key in (
        "PHASE21_MARKET_DATA_JSON",
        "PHASE21_MARKET_JSON",
        "MARKET_DATA_JSON",
        "CANONICAL_MARKET_DATA_JSON",
        "SIGNAL_ENGINE_MARKET_DATA_JSON",
        "PAPER_MARKET_DATA_JSON",
    ):
        env[key] = snapshot_path

    env["PHASE21_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)

    proc = run_python(
        SIGNAL_ENGINE,
        [],
        env,
    )
    emit_process(proc)

    SIGNAL_STDOUT.write_text(
        proc.stdout or "",
        encoding="utf-8",
    )

    SIGNAL_STDERR.write_text(
        proc.stderr or "",
        encoding="utf-8",
    )

    objects = json_objects_from_text(proc.stdout or "")

    stocks_scanned = max(
        [
            int(x)
            for x in recursive_values(objects, {"stocks_scanned"})
            if isinstance(x, (int, float)) and not isinstance(x, bool)
        ]
        or [0]
    )

    reported_eligible = max(
        [
            int(x)
            for x in recursive_values(
                objects,
                {
                    "signals_eligible",
                    "eligible_count",
                    "eligible_signals_count",
                },
            )
            if isinstance(x, (int, float)) and not isinstance(x, bool)
        ]
        or [0]
    )

    top_symbol_values = recursive_values(
        objects,
        {"top_symbol"},
    )

    top_score_values = recursive_values(
        objects,
        {"top_score"},
    )

    normalized: list[dict[str, Any]] = []

    for index, obj in enumerate(objects):
        source = f"signal-engine-stdout:{index}"

        for row, fallback_date, fallback_strategy in recursive_candidate_rows(obj):
            item = normalize_signal_candidate(
                row,
                fallback_date,
                fallback_strategy,
                source,
            )

            if item:
                normalized.append(item)

    best: dict[tuple[str, str], dict[str, Any]] = {}

    for item in normalized:
        key = (item["trade_date"], item["symbol"])
        previous = best.get(key)

        if previous is None or float(item["total_score"]) > float(previous["total_score"]):
            best[key] = item

    normalized = list(best.values())

    if normalized:
        latest = max(x["trade_date"] for x in normalized)
        normalized = [
            x
            for x in normalized
            if x["trade_date"] == latest
        ]
        normalized.sort(
            key=lambda x: (-float(x["total_score"]), x["symbol"])
        )
        normalized = normalized[:MAX_CANDIDATES]

    capture = {
        "signal_engine": str(SIGNAL_ENGINE.relative_to(ROOT)),
        "signal_engine_exit_code": proc.returncode,
        "market_input_path": str(CANONICAL_MARKET_INPUT.relative_to(ROOT)),
        "market_data_source": market_snapshot["market_data_source"],
        "market_input_active_stocks": market_snapshot["active_stocks"],
        "market_input_stocks_with_history": market_snapshot["stocks_with_history"],
        "market_input_rows_scanned": market_snapshot["rows_scanned"],
        "market_input_latest_market_date": market_snapshot["latest_market_date"],
        "stdout_json_objects": len(objects),
        "signal_engine_stocks_scanned": stocks_scanned,
        "reported_signals_eligible": reported_eligible,
        "adapted_signals_eligible": len(normalized),
        "top_symbol": (
            str(top_symbol_values[0])
            if top_symbol_values
            else None
        ),
        "top_score": (
            float(top_score_values[0])
            if top_score_values
            and isinstance(top_score_values[0], (int, float))
            else None
        ),
        "score_threshold": SCORE_THRESHOLD,
        "signals": normalized,
        "synthetic_market_data": False,
        "synthetic_evidence_present": False,
    }

    dump_json(SIGNAL_CAPTURE, capture)

    if proc.returncode != 0:
        raise RuntimeError(
            f"Signal engine failed with exit code {proc.returncode}"
        )

    if market_snapshot["stocks_with_history"] > 0 and stocks_scanned == 0:
        raise RuntimeError(
            "SIGNAL_INPUT_CONTRACT_MISMATCH: canonical market history exists "
            "but the signal engine scanned zero stocks."
        )

    if reported_eligible > 0 and not normalized:
        raise RuntimeError(
            "SIGNAL_OUTPUT_CONTRACT_MISMATCH: signal engine reports eligible signals "
            "but no candidate rows could be normalized."
        )

    return normalized, capture


def latest_prices_for_signals(
    market_rows: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    wanted = {x["symbol"] for x in signals}
    by_symbol: dict[str, dict[str, Any]] = {}

    for row in market_rows:
        if row["symbol"] not in wanted:
            continue

        previous = by_symbol.get(row["symbol"])

        if previous is None or row["trade_date"] > previous["trade_date"]:
            by_symbol[row["symbol"]] = row

    return list(by_symbol.values())


def persist_canonical(
    gate: dict[str, Any],
    signals: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    market_source: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    seed = {
        "strategy": STRATEGY,
        "signals": [x["source_row_hash"] for x in signals],
        "prices": [x["source_row_hash"] for x in prices],
        "gate": gate.get("evidence_sha256"),
    }

    batch_id = "P348451-" + stable_hash(seed)[:24]

    signal_rows = [
        {
            **x,
            "canonical_batch_id": batch_id,
        }
        for x in signals
    ]

    price_rows = [
        {
            **x,
            "canonical_batch_id": batch_id,
        }
        for x in prices
    ]

    rest_insert(SIGNAL_STORE, signal_rows)
    rest_insert(MARKET_STORE, price_rows)

    status = (
        "NO_SIGNAL"
        if not signals
        else ("NO_REAL_PRICE" if not prices else "PERSISTED")
    )

    trade_date = max(
        (x["trade_date"] for x in signals),
        default=None,
    )

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
            "evidence_sha256": stable_hash(
                {
                    "signals": signal_rows,
                    "prices": price_rows,
                }
            ),
        }],
    )

    persisted_signals, sig_error = rest_get(
        SIGNAL_STORE,
        [
            ("select", "*"),
            ("canonical_batch_id", f"eq.{batch_id}"),
        ],
    )

    if sig_error:
        raise RuntimeError(sig_error)

    persisted_prices, price_error = rest_get(
        MARKET_STORE,
        [
            ("select", "*"),
            ("canonical_batch_id", f"eq.{batch_id}"),
        ],
    )

    if price_error:
        raise RuntimeError(price_error)

    return batch_id, persisted_signals, persisted_prices


def write_phase348_adapters(
    signals: list[dict[str, Any]],
    prices: list[dict[str, Any]],
) -> None:
    dump_json(
        CANONICAL_SIGNALS,
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
        CANONICAL_MARKET,
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


def run_phase348(
    approver: str,
) -> dict[str, Any]:
    env = os.environ.copy()

    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE348_SIGNAL_JSON"] = str(CANONICAL_SIGNALS)
    env["PHASE348_MARKET_JSON"] = str(CANONICAL_MARKET)
    env["PHASE348_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE348_MAX_CANDIDATES"] = str(MAX_CANDIDATES)

    proc = run_python(
        PHASE348,
        ["--approver", approver],
        env,
    )
    emit_process(proc)

    # Phase 3.4.8 may intentionally return non-zero on a safe zero-order state.
    # Use its evidence JSON as the source of truth instead of treating that alone as unsafe.
    if not P348_JSON.exists():
        raise RuntimeError(
            f"Phase 3.4.8 evidence missing; process exit code={proc.returncode}"
        )

    result = load_json(P348_JSON)

    if result.get("synthetic_fallback_allowed") is not False:
        raise RuntimeError("Synthetic fallback violation")

    if result.get("synthetic_evidence_present") is not False:
        raise RuntimeError("Synthetic evidence violation")

    execution_state = result.get("execution_state")

    safe_states = {
        "REAL_CANONICAL_EVIDENCE_EXECUTED",
        "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
        "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
        "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
    }

    if execution_state not in safe_states:
        raise RuntimeError(
            f"Unexpected Phase 3.4.8 execution state: {execution_state!r}"
        )

    return result


def write_summary(
    result: dict[str, Any],
) -> None:
    result["evidence_sha256"] = stable_hash(result)
    dump_json(RESULT_JSON, result)

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.5.1",
        "",
        "## V9.1 Runtime Market Data Source Discovery + Signal Input Contract Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        "",
        "### Market Source Discovery",
        "",
        f"- Selected Market Data Source: `{result['market_data_source']}`",
        f"- Active Stock Source: `{result['active_stock_source']}`",
        f"- Active Stocks: **{result['active_stocks']}**",
        f"- Stocks With History: **{result['stocks_with_history']}**",
        f"- Rows Scanned: **{result['rows_scanned']}**",
        f"- Latest Market Date: `{result['latest_market_date'] or 'NONE'}`",
        "",
        "### Signal Input Contract",
        "",
        f"- Signal Engine: `{result['signal_engine']}`",
        f"- Signal Engine Exit Code: **{result['signal_engine_exit_code']}**",
        f"- Signal Engine Stocks Scanned: **{result['signal_engine_stocks_scanned']}**",
        f"- Score Threshold: **{result['score_threshold']}**",
        f"- Reported signals_eligible: **{result['reported_signals_eligible']}**",
        f"- Adapted Eligible V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- Top Symbol: `{result['top_symbol'] or 'NONE'}`",
        f"- Top Score: **{result['top_score'] if result['top_score'] is not None else 'NONE'}**",
        "",
        "### Canonical Persistence",
        "",
        f"- Canonical Batch ID: `{result['canonical_batch_id']}`",
        f"- Signals Persisted: **{result['signals_persisted']}**",
        f"- Prices Persisted: **{result['prices_persisted']}**",
        "",
        "### Phase 3.4.8 Execution",
        "",
        f"- Execution State: **{result['execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
        "",
        "### Per-symbol Market History",
        "",
    ]

    for row in result["per_symbol_market_history"][:25]:
        lines.append(
            f"- `{row['symbol']}`: history={row['history_rows']}, "
            f"latest={row['latest_market_date']}, close={row['latest_close']}"
        )

    lines.extend(
        [
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

    (OUT / "phase348451_signal_input_contract_fix.md").write_text(
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
        default=os.getenv(
            "PHASE348451_APPROVER",
            "rchu9246",
        ),
    )

    args = parser.parse_args()
    approver = args.approver.strip()

    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety violation: mode must remain SHADOW_ONLY_NO_BROKER"
        )

    gate = run_gate(approver)

    market_rows, market_source, profiles = discover_best_market_source()

    if not market_rows or not market_source:
        raise RuntimeError(
            "NO_REAL_MARKET_DATA_SOURCE: no readable market table exposed usable real rows."
        )

    active_symbols, active_source = discover_active_symbols(
        market_rows
    )

    market_snapshot = build_market_snapshot(
        market_rows,
        market_source,
        active_symbols,
    )

    signals, capture = execute_signal_engine(
        market_snapshot
    )

    prices = latest_prices_for_signals(
        market_rows,
        signals,
    )

    batch_id, persisted_signals, persisted_prices = persist_canonical(
        gate,
        signals,
        prices,
        market_source,
    )

    write_phase348_adapters(
        persisted_signals,
        persisted_prices,
    )

    phase348 = run_phase348(
        approver
    )

    result = {
        "version": "3.4.8.4.5.1",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": gate["runtime_execution_gate"],
        "market_data_source": market_source,
        "active_stock_source": active_source,
        "active_stocks": market_snapshot["active_stocks"],
        "stocks_with_history": market_snapshot["stocks_with_history"],
        "rows_scanned": market_snapshot["rows_scanned"],
        "latest_market_date": market_snapshot["latest_market_date"],
        "per_symbol_market_history": market_snapshot["per_symbol"],
        "signal_engine": str(SIGNAL_ENGINE.relative_to(ROOT)),
        "signal_engine_exit_code": capture["signal_engine_exit_code"],
        "signal_engine_stocks_scanned": capture["signal_engine_stocks_scanned"],
        "score_threshold": SCORE_THRESHOLD,
        "reported_signals_eligible": capture["reported_signals_eligible"],
        "eligible_v91_signals": len(signals),
        "top_symbol": capture["top_symbol"],
        "top_score": capture["top_score"],
        "canonical_batch_id": batch_id,
        "signals_persisted": len(persisted_signals),
        "prices_persisted": len(persisted_prices),
        "execution_state": phase348.get("execution_state"),
        "paper_orders_created": phase348.get("paper_orders_created", 0),
        "simulated_fills": phase348.get("simulated_fills", 0),
        "open_positions": phase348.get("open_positions", 0),
        "market_source_profiles": profiles,
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

    # Strong postconditions.
    if result["stocks_with_history"] > 0 and result["signal_engine_stocks_scanned"] == 0:
        raise RuntimeError(
            "SIGNAL_INPUT_CONTRACT_MISMATCH: market history exists but signal engine scanned zero stocks."
        )

    if result["reported_signals_eligible"] > 0 and result["eligible_v91_signals"] == 0:
        raise RuntimeError(
            "SIGNAL_OUTPUT_CONTRACT_MISMATCH: engine reported eligible signals "
            "but no candidate rows were adapted."
        )

    if result["eligible_v91_signals"] > 0 and result["signals_persisted"] == 0:
        raise RuntimeError(
            "Canonical signal persistence failed."
        )

    if result["paper_orders_created"] > 0:
        if result["signals_persisted"] <= 0:
            raise RuntimeError("Orders exist without persisted real signals")
        if result["prices_persisted"] <= 0:
            raise RuntimeError("Orders exist without persisted real prices")
        if result["execution_state"] != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError(
                "Orders exist without REAL_CANONICAL_EVIDENCE_EXECUTED"
            )
        if result["simulated_fills"] != result["paper_orders_created"]:
            raise RuntimeError(
                "Paper order/fill mismatch"
            )

    if result["eligible_v91_signals"] == 0 and result["paper_orders_created"] != 0:
        raise RuntimeError(
            "Safety violation: paper orders created without real eligible signals."
        )

    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    print(
        "PHASE348451 PASS: market source discovery -> canonical input -> "
        "signal engine -> canonical persistence -> Phase 3.4.8 complete. "
        f"source={market_source}, "
        f"active={result['active_stocks']}, "
        f"history={result['stocks_with_history']}, "
        f"rows={result['rows_scanned']}, "
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

Section "Writing Phase 3.4.8.4.5.1 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.4.5.1 - V9.1 Runtime Market Data Source Discovery Signal Input Contract Fix

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
  group: gpt-quant-phase348451-market-source-discovery-signal-input
  cancel-in-progress: false

jobs:
  market-source-discovery-signal-input:
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

      - name: Validate Phase 3.4.8.4.5.1 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py
          test -f automation/v92/paper_trading_phase21_signal_engine.py
          test -f automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          grep -q 'REAL_MARKET_SOURCE_DISCOVERY_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY' \
            automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py

          grep -q '"synthetic_market_data": False' \
            automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py

          grep -q '"fake_prices_allowed": False' \
            automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py

          echo "Phase 3.4.8.4.5.1 safety contract: PASS"

      - name: Execute Phase 3.4.8.4.5.1 market source discovery
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8.4.5.1 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase348451_output/phase348451_signal_input_contract_fix.json
          test -f phase348451_output/market_source_profiles.json
          test -f phase348451_output/canonical_market_input.json
          test -f phase348451_output/signal_engine_input_contract_capture.json
          test -f phase348451_output/canonical_signals.runtime.json
          test -f phase348451_output/canonical_market_prices.runtime.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase348451_output/phase348451_signal_input_contract_fix.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8.4.5.1", data
          assert data["status"] == "PASS", data
          assert data["runtime_execution_gate"] == "OPEN", data

          assert data["market_data_source"], data
          assert data["rows_scanned"] > 0, data
          assert data["stocks_with_history"] > 0, data

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

          if data["stocks_with_history"] > 0:
              assert data["signal_engine_stocks_scanned"] > 0, data

          if data["reported_signals_eligible"] > 0:
              assert data["eligible_v91_signals"] > 0, data
              assert data["signals_persisted"] > 0, data

          if data["paper_orders_created"] > 0:
              assert data["signals_persisted"] > 0, data
              assert data["prices_persisted"] > 0, data
              assert data["execution_state"] == "REAL_CANONICAL_EVIDENCE_EXECUTED", data
              assert data["simulated_fills"] == data["paper_orders_created"], data

          print("Phase 3.4.8.4.5.1 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.4.5.1 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase348451-market-source-discovery-${{ github.run_id }}
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
    'PHASE348451_V91_RUNTIME_MARKET_DATA_SOURCE_DISCOVERY_SIGNAL_INPUT_CONTRACT_FIX',
    'REAL_MARKET_SOURCE_DISCOVERY_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY',
    'market_source_profiles.json',
    'discover_best_market_source',
    'SIGNAL_INPUT_CONTRACT_MISMATCH',
    'PHASE21_MARKET_DATA_JSON',
    'SIGNAL_ENGINE_MARKET_DATA_JSON',
    'signal_engine_stocks_scanned',
    'reported_signals_eligible',
    'paper_canonical_signals_v92',
    'paper_canonical_market_prices_v92',
    '"synthetic_market_data": False',
    '"fake_prices_allowed": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False',
    'REAL_CANONICAL_EVIDENCE_EXECUTED'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.4.5.1 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.4.5.1 semantic source-discovery contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Phase 3.4.8.4.5.1 focus:" -ForegroundColor Cyan
Write-Host "  Profile real Supabase market tables"
Write-Host "      -> choose strongest usable source"
Write-Host "      -> normalize symbol/date/OHLCV aliases"
Write-Host "      -> build canonical Phase 2.1 market input"
Write-Host "      -> execute real V9.1 signal engine"
Write-Host "      -> verify stocks scanned > 0"
Write-Host "      -> capture signals_eligible / top symbol / top score"
Write-Host "      -> persist real canonical signals/prices"
Write-Host "      -> Phase 3.4.8 paper execution"
Write-Host ""

Write-Host "Desired diagnostics:" -ForegroundColor Cyan
Write-Host "  Selected Market Data Source: <real Supabase table>"
Write-Host "  Active Stocks: > 0"
Write-Host "  Stocks With History: > 0"
Write-Host "  Rows Scanned: > 0"
Write-Host "  Latest Market Date: <date>"
Write-Host "  Signal Engine Stocks Scanned: > 0"
Write-Host "  Reported signals_eligible: 0 or >0"
Write-Host "  Top Symbol / Top Score when present"
Write-Host ""

Write-Host "Important new fail-closed rule:" -ForegroundColor Yellow
Write-Host "  If market history exists but signal engine scans 0 stocks => SIGNAL_INPUT_CONTRACT_MISMATCH"
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
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.4.5.1."
Write-Host "  4) Run with defaults."
Write-Host "  5) Inspect selected source / history / signal-engine stocks scanned / eligible count."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
