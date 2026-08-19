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
OUT = ROOT / "phase3482_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
SCORE_THRESHOLD = float(os.getenv("PHASE3482_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE3482_MAX_CANDIDATES", "3"))

PHASE346 = ROOT / "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py"
PHASE348 = ROOT / "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"
P348_JSON = ROOT / "phase348_output/phase348_execution.json"

CANONICAL_SIGNAL_FILE = OUT / "canonical_signals.persisted.json"
CANONICAL_MARKET_FILE = OUT / "canonical_market_prices.persisted.json"
RESULT_FILE = OUT / "phase3482_runtime_adapter.json"

SIGNAL_STORE = "paper_canonical_signals_v92"
MARKET_STORE = "paper_canonical_market_prices_v92"
BATCH_STORE = "paper_canonical_runtime_batches_v92"

CONTRACT = "PHASE3482_CANONICAL_SIGNAL_PERSISTENCE_RUNTIME_SOURCE_ADAPTER"
SAFETY_CONTRACT = "PERSISTED_REAL_EVIDENCE_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY"

SIGNAL_TABLE_HINTS = [
    "signals",
    "stock_signals",
    "trading_signals",
    "signal_history",
    "signals_v91",
    "strategy_signals",
]

MARKET_TABLE_HINTS = [
    "market_data",
    "stock_prices",
    "daily_prices",
    "market_daily",
    "market_data_daily",
    "ohlcv_daily",
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


def supabase_config() -> tuple[str, dict[str, str]]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not base:
        raise RuntimeError("SUPABASE_URL is missing")
    if not service_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is required for canonical persistence"
        )

    return base, {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(
    table: str,
    params: list[tuple[str, str]],
) -> tuple[list[dict[str, Any]], str | None]:
    base, headers = supabase_config()
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        return [], f"{table}: request error: {exc}"

    if response.status_code >= 400:
        return [], f"{table}: HTTP {response.status_code}"

    try:
        data = response.json()
    except ValueError:
        return [], f"{table}: invalid JSON"

    if not isinstance(data, list):
        return [], f"{table}: response is not a row list"

    return [x for x in data if isinstance(x, dict)], None


def rest_insert(
    table: str,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    base, headers = supabase_config()
    headers = dict(headers)
    headers["Prefer"] = "return=minimal,resolution=ignore-duplicates"
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    try:
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(rows, ensure_ascii=False),
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"{table}: persistence request error: {exc}")

    if response.status_code >= 400:
        body = response.text[:800]
        if response.status_code in {404, 400} and (
            "Could not find the table" in body
            or "relation" in body.lower()
            or "schema cache" in body.lower()
        ):
            raise RuntimeError(
                "CANONICAL_RUNTIME_STORE_MISSING: apply "
                "supabase/PHASE3482_CANONICAL_RUNTIME_STORE.sql in Supabase SQL Editor first. "
                f"Underlying error: {table} HTTP {response.status_code}: {body}"
            )
        raise RuntimeError(
            f"{table}: persistence HTTP {response.status_code}: {body}"
        )


def run_script(script: Path, args: list[str], env: dict[str, str]) -> None:
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
        raise RuntimeError(
            f"{script.name} failed with exit code {proc.returncode}"
        )


def run_gate(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    run_script(
        PHASE346,
        [
            "--approver",
            approver,
            "--note",
            "Phase 3.4.8.2 canonical persistence runtime gate reconstruction",
        ],
        env,
    )

    if not GATE_JSON.exists():
        raise RuntimeError("Phase 3.4.6 gate output missing")

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
        raise RuntimeError(
            "Runtime gate validation failed: " + "; ".join(errors)
        )

    return gate


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

    signal = str(
        row.get("signal")
        or row.get("action")
        or row.get("recommendation")
        or ""
    ).strip().upper()

    if signal not in {"BUY", "LONG"}:
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

    trade_date = str(
        row.get("trade_date")
        or row.get("market_date")
        or row.get("date")
        or ""
    ).strip()

    if not trade_date:
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
    symbol = str(
        row.get("symbol")
        or row.get("stock_id")
        or row.get("ticker")
        or row.get("stock_symbol")
        or ""
    ).strip()

    if not symbol:
        return None

    price = None
    for key in (
        "close",
        "price",
        "last_price",
        "market_price",
        "close_price",
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

    trade_date = str(
        row.get("trade_date")
        or row.get("market_date")
        or row.get("date")
        or ""
    ).strip()

    if not trade_date:
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


def discover_signals() -> tuple[list[dict[str, Any]], str | None, list[str]]:
    diagnostics: list[str] = []

    for table in SIGNAL_TABLE_HINTS:
        rows, error = rest_get(
            table,
            [
                ("select", "*"),
                ("order", "trade_date.desc"),
                ("limit", "100"),
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
            continue

        latest_date = max(x["trade_date"] for x in normalized)
        normalized = [x for x in normalized if x["trade_date"] == latest_date]
        normalized.sort(key=lambda x: (-float(x["total_score"]), x["symbol"]))

        return normalized[:MAX_CANDIDATES], table, diagnostics

    return [], None, diagnostics


def discover_market(
    signals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    diagnostics: list[str] = []
    symbols = {x["symbol"] for x in signals}

    for table in MARKET_TABLE_HINTS:
        rows, error = rest_get(
            table,
            [
                ("select", "*"),
                ("order", "trade_date.desc"),
                ("limit", "1000"),
            ],
        )

        if error:
            diagnostics.append(error)
            continue

        normalized = [
            item
            for row in rows
            if (item := normalize_market(row, table)) is not None
            and item["symbol"] in symbols
        ]

        if not normalized:
            continue

        latest_by_symbol: dict[str, dict[str, Any]] = {}

        for row in normalized:
            existing = latest_by_symbol.get(row["symbol"])
            if existing is None or row["trade_date"] > existing["trade_date"]:
                latest_by_symbol[row["symbol"]] = row

        return list(latest_by_symbol.values()), table, diagnostics

    return [], None, diagnostics


def persist_canonical(
    gate: dict[str, Any],
    signals: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
    signal_source: str | None,
    market_source: str | None,
) -> str:
    latest_dates = [x["trade_date"] for x in signals]
    batch_trade_date = max(latest_dates) if latest_dates else None

    seed = {
        "strategy_version": STRATEGY,
        "trade_date": batch_trade_date,
        "signal_hashes": sorted(x["source_row_hash"] for x in signals),
        "market_hashes": sorted(x["source_row_hash"] for x in market_rows),
        "gate_evidence": gate.get("evidence_sha256"),
    }
    batch_id = "P3482-" + stable_hash(seed)[:24]

    signal_rows = [
        {
            **x,
            "canonical_batch_id": batch_id,
        }
        for x in signals
    ]

    market_rows_for_store = [
        {
            **x,
            "canonical_batch_id": batch_id,
        }
        for x in market_rows
    ]

    rest_insert(SIGNAL_STORE, signal_rows)
    rest_insert(MARKET_STORE, market_rows_for_store)

    if not signals:
        status = "NO_SIGNAL"
    elif not market_rows:
        status = "NO_REAL_PRICE"
    else:
        status = "PERSISTED"

    batch_row = {
        "canonical_batch_id": batch_id,
        "strategy_version": STRATEGY,
        "trade_date": batch_trade_date,
        "signal_source_table": signal_source,
        "market_source_table": market_source,
        "canonical_signals": len(signals),
        "canonical_prices": len(market_rows),
        "status": status,
        "runtime_execution_gate": gate["runtime_execution_gate"],
        "synthetic_fallback_allowed": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "evidence_sha256": stable_hash(
            {
                "signals": signal_rows,
                "market": market_rows_for_store,
            }
        ),
    }

    rest_insert(BATCH_STORE, [batch_row])
    return batch_id


def read_persisted_batch(
    batch_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signal_rows, signal_error = rest_get(
        SIGNAL_STORE,
        [
            ("select", "*"),
            ("canonical_batch_id", f"eq.{batch_id}"),
            ("order", "total_score.desc"),
        ],
    )

    if signal_error:
        raise RuntimeError(signal_error)

    market_rows, market_error = rest_get(
        MARKET_STORE,
        [
            ("select", "*"),
            ("canonical_batch_id", f"eq.{batch_id}"),
        ],
    )

    if market_error:
        raise RuntimeError(market_error)

    return signal_rows, market_rows


def build_phase348_files(
    signals: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    phase348_signals = [
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

    phase348_market = [
        {
            "symbol": row["symbol"],
            "market_date": row["trade_date"],
            "close": float(row["close"]),
            "canonical_batch_id": row["canonical_batch_id"],
            "source": f"supabase:{MARKET_STORE}",
            "synthetic_evidence": False,
        }
        for row in market_rows
    ]

    dump_json(CANONICAL_SIGNAL_FILE, {"signals": phase348_signals})
    dump_json(CANONICAL_MARKET_FILE, {"data": phase348_market})

    return phase348_signals, phase348_market


def run_phase348(
    approver: str,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE348_SIGNAL_JSON"] = str(CANONICAL_SIGNAL_FILE)
    env["PHASE348_MARKET_JSON"] = str(CANONICAL_MARKET_FILE)
    env["PHASE348_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE348_MAX_CANDIDATES"] = str(MAX_CANDIDATES)

    run_script(PHASE348, ["--approver", approver], env)

    if not P348_JSON.exists():
        raise RuntimeError("Phase 3.4.8 output missing")

    result = load_json(P348_JSON)

    if result.get("status") != "PASS":
        raise RuntimeError("Phase 3.4.8 did not PASS")

    if result.get("synthetic_fallback_allowed") is not False:
        raise RuntimeError("Synthetic fallback safety violation")

    if result.get("synthetic_evidence_present") is not False:
        raise RuntimeError("Synthetic evidence safety violation")

    return result


def write_summary(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = stable_hash(result)
    dump_json(RESULT_FILE, result)

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.2",
        "",
        "## Canonical Signal Persistence + Runtime Source Adapter",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Adapter Contract: **{result['adapter_contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        "",
        "### Canonical Persistence",
        "",
        f"- Canonical Batch ID: `{result['canonical_batch_id'] or 'NONE'}`",
        f"- Discovered Signal Source: `{result['discovered_signal_source'] or 'NONE'}`",
        f"- Discovered Market Source: `{result['discovered_market_source'] or 'NONE'}`",
        f"- Signals Persisted: **{result['signals_persisted']}**",
        f"- Market Prices Persisted: **{result['market_prices_persisted']}**",
        f"- Runtime Signal Source: `{result['runtime_signal_source']}`",
        f"- Runtime Market Source: `{result['runtime_market_source']}`",
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
        lines.extend(["", "### Source Diagnostics", ""])
        lines.extend(f"- {x}" for x in result["diagnostics"][:24])

    text = "\n".join(lines) + "\n"
    (OUT / "phase3482_runtime_adapter.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE3482_APPROVER", "rchu9246"),
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

    signals, signal_source, signal_diag = discover_signals()
    diagnostics = list(signal_diag)

    market_rows: list[dict[str, Any]] = []
    market_source: str | None = None

    if signals:
        market_rows, market_source, market_diag = discover_market(signals)
        diagnostics.extend(market_diag)

    batch_id = persist_canonical(
        gate,
        signals,
        market_rows,
        signal_source,
        market_source,
    )

    persisted_signals, persisted_market = read_persisted_batch(batch_id)

    # Persistence round-trip is the source of truth from here onward.
    phase348_signals, phase348_market = build_phase348_files(
        persisted_signals,
        persisted_market,
    )

    phase348 = run_phase348(approver)

    result = {
        "version": "3.4.8.2",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "adapter_contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": gate["runtime_execution_gate"],
        "canonical_batch_id": batch_id,
        "discovered_signal_source": signal_source,
        "discovered_market_source": market_source,
        "signals_persisted": len(persisted_signals),
        "market_prices_persisted": len(persisted_market),
        "runtime_signal_source": f"supabase:{SIGNAL_STORE}",
        "runtime_market_source": f"supabase:{MARKET_STORE}",
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

    if result["paper_orders_created"] > 0:
        if result["signals_persisted"] <= 0 or result["market_prices_persisted"] <= 0:
            raise RuntimeError(
                "Safety violation: paper orders exist without persisted canonical evidence"
            )
        if result["phase348_execution_state"] != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError(
                "Unexpected Phase 3.4.8 execution state for non-zero orders"
            )

    for order in phase348.get("orders", []):
        if order.get("synthetic_evidence") is not False:
            raise RuntimeError("Synthetic order evidence detected")
        if order.get("broker_submitted") is not False:
            raise RuntimeError("Broker submission safety violation")
        if order.get("real_money") is not False:
            raise RuntimeError("Real-money safety violation")

    write_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE3482 PASS: canonical persistence round-trip complete. "
        f"signals={len(persisted_signals)}, prices={len(persisted_market)}, "
        f"orders={result['paper_orders_created']}, fills={result['simulated_fills']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
