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
