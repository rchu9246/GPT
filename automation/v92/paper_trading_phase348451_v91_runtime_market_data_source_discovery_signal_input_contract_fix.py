#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation
import subprocess
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
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


# Versioned, content-addressed sizing authority. No database writes in these helpers.
AUTHORITY_SCHEMA_VERSION = 1
AUTHORITY_REPOSITORY = "rchu9246/GPT"
AUTHORITY_WORKFLOW = ".github/workflows/gpt-quant-v92-paper-trading-phase348451-v91-runtime-market-data-source-discovery-signal-input-contract-fix.yml"
AUTHORITY_STATES = {"REAL_CANONICAL_EVIDENCE_EXECUTED", "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS"}
SIGNAL_ADAPTER_PATH = "phase348451_output/canonical_signals.runtime.json"
PRICE_ADAPTER_PATH = "phase348451_output/canonical_market_prices.runtime.json"
PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False


def normalized_symbol(value: Any) -> str:
    symbol = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    if not symbol:
        raise RuntimeError("AUTHORITY_EMPTY_SYMBOL")
    return symbol


def finite_number(value: Any, positive: bool = False) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RuntimeError("AUTHORITY_INVALID_NUMBER") from None
    if not number.is_finite() or (positive and number <= 0):
        raise RuntimeError("AUTHORITY_INVALID_NUMBER")
    return str(number.normalize())


def unique_symbols(rows: list[dict[str, Any]], batch_id: str) -> None:
    groups: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        groups[normalized_symbol(row.get("symbol"))].append(row.get("id"))
    duplicates = {symbol: ids for symbol, ids in groups.items() if len(ids) != 1}
    if duplicates:
        raise RuntimeError(f"DUPLICATE_NORMALIZED_SYMBOL batch={batch_id} symbols/row_ids={duplicates}")


def canonical_rows(rows: list[dict[str, Any]], kind: str, batch_id: str, trade_date: str) -> list[dict[str, Any]]:
    unique_symbols(rows, batch_id)
    result = []
    for row in rows:
        if (row.get("canonical_batch_id") != batch_id or row.get("trade_date") != trade_date
                or row.get("synthetic_evidence") is not False):
            raise RuntimeError(f"INVALID_SAME_BATCH_{kind.upper()} batch={batch_id} row={row.get('id')}")
        if not row.get("source_table") or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("source_row_hash", ""))):
            raise RuntimeError(f"MISSING_ROW_PROVENANCE batch={batch_id}")
        item = {key: row[key] for key in ("canonical_batch_id", "trade_date", "source_table", "source_row_hash", "synthetic_evidence")}
        item["symbol"] = normalized_symbol(row.get("symbol"))
        if kind == "signal":
            if row.get("strategy_version") != "V9.1":
                raise RuntimeError("AUTHORITY_WRONG_STRATEGY")
            item.update(strategy_version="V9.1", signal=str(row.get("signal", "")).strip().upper(),
                        total_score=finite_number(row.get("total_score")))
            if item["signal"] not in {"BUY", "LONG"}:
                raise RuntimeError("AUTHORITY_INVALID_SIGNAL_SIDE")
        else:
            item["close"] = finite_number(row.get("close"), positive=True)
        result.append(item)
    return sorted(result, key=lambda row: row["symbol"])


def read_canonical_batch(table: str, batch_id: str) -> list[dict[str, Any]]:
    rows, pages = [], set()
    while True:
        page, error = rest_get(table, [("select", "*"), ("canonical_batch_id", f"eq.{batch_id}"),
                                       ("order", "id.asc"), ("limit", "500"), ("offset", str(len(rows)))])
        if error:
            raise RuntimeError(error)
        if not page:
            return rows
        digest = stable_hash(page)
        if digest in pages:
            raise RuntimeError(f"INCOMPLETE_CANONICAL_BATCH_READ batch={batch_id}")
        pages.add(digest)
        rows.extend(page)


def adapter_payloads(signals: list[dict[str, Any]], prices: list[dict[str, Any]]) -> tuple[dict, dict]:
    return (
        {"signals": [{"symbol": normalized_symbol(r["symbol"]), "trade_date": r["trade_date"],
                      "strategy_version": r["strategy_version"], "total_score": float(r["total_score"]),
                      "signal": r["signal"], "canonical_batch_id": r["canonical_batch_id"],
                      "source": f"supabase:{SIGNAL_STORE}", "synthetic_evidence": False} for r in signals]},
        {"data": [{"symbol": normalized_symbol(r["symbol"]), "market_date": r["trade_date"],
                   "close": float(r["close"]), "canonical_batch_id": r["canonical_batch_id"],
                   "source": f"supabase:{MARKET_STORE}", "synthetic_evidence": False} for r in prices]},
    )


def validate_bridge_provenance(bridge: dict, signals: list[dict], prices: list[dict]) -> None:
    if (bridge.get("execution_state") not in AUTHORITY_STATES or bridge.get("status") != "PASS"
            or bridge.get("strategy_version") != "V9.1" or bridge.get("runtime_execution_gate") != "OPEN"
            or bridge.get("canonical_signal_source") != SIGNAL_ADAPTER_PATH):
        raise RuntimeError("BRIDGE_AUTHORITY_NOT_PROVEN")
    for flag in ("synthetic_fallback_allowed", "synthetic_evidence_present", "broker_api_used",
                 "broker_credentials_used", "broker_order_submission_enabled", "real_money_trading_enabled",
                 "live_money_release_authorized", "fail_closed_triggered"):
        if bridge.get(flag) is not False:
            raise RuntimeError(f"BRIDGE_SAFETY_VIOLATION {flag}")
    if bridge.get("fail_closed_policy") is not True or bridge.get("errors"):
        raise RuntimeError("BRIDGE_FAIL_CLOSED")
    unsigned = {k: v for k, v in bridge.items() if k != "evidence_sha256"}
    if bridge.get("evidence_sha256") != stable_hash(unsigned):
        raise RuntimeError("INVALID_BRIDGE_EVIDENCE_HASH")
    candidates = bridge.get("canonical_candidates", [])
    unique_symbols(candidates, signals[0]["canonical_batch_id"])
    if (len(candidates) != len(signals) or bridge.get("canonical_signals_found") != len(signals)
            or bridge.get("signals_with_real_market_price") != len(signals)):
        raise RuntimeError("BRIDGE_CANDIDATE_COUNT_MISMATCH")
    sigs = {r["symbol"]: r for r in signals}
    px = {r["symbol"]: r for r in prices}
    for candidate in candidates:
        symbol = normalized_symbol(candidate.get("symbol"))
        signal = sigs.get(symbol)
        if (signal is None or candidate.get("signal_source") != SIGNAL_ADAPTER_PATH
                or candidate.get("market_price_source") != PRICE_ADAPTER_PATH
                or candidate.get("trade_date") != signal["trade_date"]
                or candidate.get("strategy_version") != "V9.1" or candidate.get("signal") != "BUY"
                or candidate.get("synthetic_evidence") is not False
                or finite_number(candidate.get("score")) != signal["total_score"]
                or finite_number(candidate.get("market_price"), True) != px[symbol]["close"]):
            raise RuntimeError(f"BRIDGE_FALLBACK_OR_PROVENANCE_MISMATCH symbol={symbol}")


def build_authority(batch_id: str, trade_date: str, signals: list[dict], prices: list[dict],
                    signal_adapter: dict, price_adapter: dict, bridge: dict, context: dict) -> tuple[dict, dict]:
    if not batch_id or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
        raise RuntimeError("AUTHORITY_MISSING_BATCH_OR_DATE")
    sigs = canonical_rows(signals, "signal", batch_id, trade_date)
    px = canonical_rows(prices, "price", batch_id, trade_date)
    if not sigs or [r["symbol"] for r in sigs] != [r["symbol"] for r in px]:
        raise RuntimeError("AUTHORITY_REQUIRES_EXACTLY_ONE_PRICE_PER_SIGNAL")
    expected_signals, expected_prices = adapter_payloads(signals, prices)
    if signal_adapter != expected_signals or price_adapter != expected_prices:
        raise RuntimeError("CANONICAL_ADAPTER_MISMATCH")
    validate_bridge_provenance(bridge, sigs, px)
    if (context.get("repository") != AUTHORITY_REPOSITORY or context.get("workflow") != AUTHORITY_WORKFLOW
            or not all(re.fullmatch(r"[1-9][0-9]*", str(context.get(k, ""))) for k in ("producer_run_id", "producer_run_attempt"))):
        raise RuntimeError("AUTHORITY_REQUIRES_EXPLICIT_PRODUCER_IDENTITY")
    authority = {
        **context, "authority_schema_version": AUTHORITY_SCHEMA_VERSION,
        "canonical_batch_id": batch_id, "trade_date": trade_date, "strategy_version": "V9.1",
        "producer_version": "3.4.8.4.5.1", "bridge_execution_state": bridge["execution_state"],
        "bridge_evidence_hash": stable_hash(bridge), "signal_adapter_hash": stable_hash(signal_adapter),
        "price_adapter_hash": stable_hash(price_adapter), "validated_symbol_set": [r["symbol"] for r in sigs],
        "signal_count": len(sigs), "price_count": len(px),
        "signal_rows_hash": stable_hash(sigs), "price_rows_hash": stable_hash(px),
        "paper_only": True, "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False, "historical_rewrite_allowed": False,
    }
    authority["authority_hash"] = stable_hash(authority)
    evidence = {"signals": signals, "prices": prices, "signal_adapter": signal_adapter,
                "price_adapter": price_adapter, "bridge": bridge}
    return authority, evidence


def validate_authority(authority: dict, evidence: dict, run_id: str, attempt: str, commit_sha: str) -> None:
    context = {k: authority.get(k) for k in ("repository", "workflow", "producer_run_id", "producer_run_attempt", "producer_commit_sha")}
    if (context["producer_run_id"] != run_id or context["producer_run_attempt"] != attempt
            or context["producer_commit_sha"] != commit_sha):
        raise RuntimeError("AUTHORITY_RUN_ATTEMPT_OR_COMMIT_MISMATCH")
    rebuilt, _ = build_authority(authority.get("canonical_batch_id", ""), authority.get("trade_date", ""),
                                 evidence["signals"], evidence["prices"], evidence["signal_adapter"],
                                 evidence["price_adapter"], evidence["bridge"], context)
    if authority != rebuilt:
        raise RuntimeError("INVALID_AUTHORITY_SCHEMA_HASH_OR_PROVENANCE")


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


def daily_price_symbols(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Resolve only daily_prices foreign keys through the authoritative stocks table."""
    ids = set()
    for row in rows:
        stock_id = str(row.get("stock_id", ""))
        if not stock_id.isascii() or not stock_id.isdigit():
            raise RuntimeError(f"DAILY_PRICE_STOCK_MAPPING_INVALID_ID: {stock_id!r}")
        ids.add(stock_id)

    symbols: dict[str, str] = {}
    ordered_ids = sorted(ids)
    for offset in range(0, len(ordered_ids), 100):
        batch = ordered_ids[offset:offset + 100]
        stocks, error = rest_get("stocks", [
            ("select", "id,symbol"),
            ("id", "in.(" + ",".join(batch) + ")"),
            ("order", "id.asc"),
            ("limit", "100"),
        ])
        if error:
            raise RuntimeError(f"DAILY_PRICE_STOCK_MAPPING_QUERY_FAILED: {error}")
        for stock in stocks:
            stock_id = str(stock.get("id", ""))
            symbol = stock.get("symbol")
            if stock_id not in batch or not isinstance(symbol, str) or not symbol.strip():
                raise RuntimeError("DAILY_PRICE_STOCK_MAPPING_INVALID_ROW")
            if stock_id in symbols and symbols[stock_id] != symbol.strip():
                raise RuntimeError(f"DAILY_PRICE_STOCK_MAPPING_AMBIGUOUS: {stock_id}")
            symbols[stock_id] = symbol.strip()
        missing = set(batch) - symbols.keys()
        if missing:
            raise RuntimeError(f"DAILY_PRICE_STOCK_MAPPING_MISSING: {sorted(missing)}")
    return symbols


def normalize_market_row(
    row: dict[str, Any],
    source: str,
    stock_symbols: dict[str, str] | None = None,
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

    if source == "daily_prices":
        stock_id = str(row.get("stock_id", ""))
        if stock_symbols is None or stock_id not in stock_symbols:
            raise RuntimeError(f"DAILY_PRICE_STOCK_MAPPING_MISSING: {stock_id}")
        symbol = stock_symbols[stock_id]

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

    if source == "daily_prices":
        # Validate without replacing the source's date or price with derived values.
        trade_date = row.get("trade_date")
        close_raw = row.get("close")
        try:
            date.fromisoformat(trade_date)
            exact_close = Decimal(str(close_raw))
        except (TypeError, ValueError, InvalidOperation):
            return None
        if not exact_close.is_finite() or exact_close <= 0:
            return None
        close = close_raw
    elif close <= 0:
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

    stock_symbols = daily_price_symbols(rows) if table == "daily_prices" else None
    normalized = [
        item
        for row in rows
        if (item := normalize_market_row(row, table, stock_symbols)) is not None
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
            "symbol": x["symbol"],
            "trade_date": x["trade_date"],
            "close": x["close"],
            "source_table": x["source_table"],
            "source_row_hash": x["source_row_hash"],
            "synthetic_evidence": x["synthetic_evidence"],
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

    persisted_signals = read_canonical_batch(SIGNAL_STORE, batch_id)
    persisted_prices = read_canonical_batch(MARKET_STORE, batch_id)
    if signals:
        day = signals[0]["trade_date"]
        for kind, expected, actual in (("signal", signal_rows, persisted_signals), ("price", price_rows, persisted_prices)):
            if canonical_rows(expected, kind, batch_id, day) != canonical_rows(actual, kind, batch_id, day):
                raise RuntimeError(f"PERSISTED_BATCH_DIFFERS_FROM_PRODUCER_INPUT batch={batch_id} kind={kind}")

    return batch_id, persisted_signals, persisted_prices


def write_phase348_adapters(
    signals: list[dict[str, Any]],
    prices: list[dict[str, Any]],
) -> None:
    if signals:
        batch, day = signals[0]["canonical_batch_id"], signals[0]["trade_date"]
        canonical_rows(signals, "signal", batch, day)
        canonical_rows(prices, "price", batch, day)
    signal_payload, price_payload = adapter_payloads(signals, prices)
    dump_json(CANONICAL_SIGNALS, signal_payload)
    dump_json(CANONICAL_MARKET, price_payload)


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

    # Stale output or changed adapters must never authorize a new run.
    P348_JSON.unlink(missing_ok=True)
    adapter_hashes = (stable_hash(load_json(CANONICAL_SIGNALS)), stable_hash(load_json(CANONICAL_MARKET)))
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
    if adapter_hashes != (stable_hash(load_json(CANONICAL_SIGNALS)), stable_hash(load_json(CANONICAL_MARKET))):
        raise RuntimeError("BRIDGE_ADAPTER_CHANGED_DURING_EXECUTION")

    if result.get("synthetic_fallback_allowed") is not False:
        raise RuntimeError("Synthetic fallback violation")

    if result.get("synthetic_evidence_present") is not False:
        raise RuntimeError("Synthetic evidence violation")

    execution_state = result.get("execution_state")
    if execution_state in AUTHORITY_STATES and proc.returncode != 0:
        raise RuntimeError("BRIDGE_EXECUTION_FAILED_NO_AUTHORITY")

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

    # Authority is optional for legacy safe-zero states, mandatory for sizing.
    # Never infer authority from a PASS status alone.
    try:
        if STRATEGY != "V9.1":
            raise RuntimeError("AUTHORITY_WRONG_STRATEGY")
        context = {
            "repository": os.getenv("GITHUB_REPOSITORY", ""),
            "workflow": os.getenv("GITHUB_WORKFLOW_REF", "").split("@", 1)[0].removeprefix(AUTHORITY_REPOSITORY + "/"),
            "producer_run_id": os.getenv("GITHUB_RUN_ID", ""),
            "producer_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
            "producer_commit_sha": os.getenv("GITHUB_SHA", ""),
        }
        result["canonical_authority"], result["canonical_authority_evidence"] = build_authority(
            batch_id, signals[0]["trade_date"] if signals else "", persisted_signals, persisted_prices,
            load_json(CANONICAL_SIGNALS), load_json(CANONICAL_MARKET), phase348, context,
        )
    except RuntimeError as exc:
        result["authority_unavailable_reason"] = str(exc)

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
