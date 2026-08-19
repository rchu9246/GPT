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
OUT = ROOT / "phase34844_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
SCORE_THRESHOLD = float(os.getenv("PHASE34844_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE34844_MAX_CANDIDATES", "3"))

SIGNAL_ENGINE = ROOT / "automation/v92/paper_trading_phase21_signal_engine.py"
PHASE346 = ROOT / "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py"
PHASE348 = ROOT / "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"
P348_JSON = ROOT / "phase348_output/phase348_execution.json"

SIGNAL_STORE = "paper_canonical_signals_v92"
MARKET_STORE = "paper_canonical_market_prices_v92"
BATCH_STORE = "paper_canonical_runtime_batches_v92"

RAW_STDOUT = OUT / "signal_engine.stdout.txt"
RAW_STDERR = OUT / "signal_engine.stderr.txt"
RAW_JSON_OBJECTS = OUT / "signal_engine.json_objects.json"
SCHEMA_CAPTURE = OUT / "signal_engine_schema_capture.json"
CANONICAL_SIGNALS = OUT / "canonical_signals.runtime.json"
CANONICAL_MARKET = OUT / "canonical_market_prices.runtime.json"
RESULT_JSON = OUT / "phase34844_schema_adapter_fix.json"

CONTRACT = "PHASE34844_V91_SIGNAL_ENGINE_RUNTIME_PAYLOAD_SCHEMA_ADAPTER_FIX"
SAFETY_CONTRACT = "REAL_SIGNAL_ENGINE_PAYLOAD_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY"

CANDIDATE_ARRAY_KEYS = {
    "top_candidates",
    "candidates",
    "signals",
    "eligible_signals",
    "signal_candidates",
    "qualified_signals",
    "ranked_candidates",
    "recommendations",
    "items",
    "results",
}

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
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")


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
            "Phase 3.4.8.4.4 runtime payload schema adapter gate reconstruction",
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


def json_objects_from_text(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    consumed: set[tuple[int, int]] = set()

    for idx, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            obj, end = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        marker = (idx, idx + end)
        if marker in consumed:
            continue
        consumed.add(marker)
        objects.append(obj)

    return objects


def first_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if mapping.get(key) is not None:
            return mapping[key]
    return None


def recursive_contexts(
    obj: Any,
    inherited_date: str | None = None,
    inherited_strategy: str | None = None,
    path: str = "$",
) -> list[tuple[dict[str, Any], str | None, str | None, str]]:
    found: list[tuple[dict[str, Any], str | None, str | None, str]] = []

    if isinstance(obj, dict):
        current_date = inherited_date
        current_strategy = inherited_strategy

        date_val = first_value(
            obj,
            ("run_date", "trade_date", "market_date", "signal_date", "date"),
        )
        if date_val:
            current_date = str(date_val)[:10]

        strategy_val = first_value(
            obj,
            ("strategy_version", "strategy", "version"),
        )
        if strategy_val:
            current_strategy = str(strategy_val)

        # Any dict that looks row-like is retained as a candidate context.
        rowish_keys = set(obj.keys())
        if rowish_keys.intersection(
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
            found.append((obj, current_date, current_strategy, path))

        for key, value in obj.items():
            child_path = f"{path}.{key}"

            if isinstance(value, list):
                if key in CANDIDATE_ARRAY_KEYS:
                    for index, item in enumerate(value):
                        if isinstance(item, dict):
                            found.append(
                                (item, current_date, current_strategy, f"{child_path}[{index}]")
                            )
                for index, item in enumerate(value):
                    found.extend(
                        recursive_contexts(
                            item,
                            current_date,
                            current_strategy,
                            f"{child_path}[{index}]",
                        )
                    )
            elif isinstance(value, dict):
                found.extend(
                    recursive_contexts(
                        value,
                        current_date,
                        current_strategy,
                        child_path,
                    )
                )

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            found.extend(
                recursive_contexts(
                    item,
                    inherited_date,
                    inherited_strategy,
                    f"{path}[{index}]",
                )
            )

    return found


def recursive_signals_eligible(obj: Any) -> list[int]:
    values: list[int] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {
                "signals_eligible",
                "eligible_signals_count",
                "eligible_count",
                "qualified_signals",
            }:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values.append(int(value))
            values.extend(recursive_signals_eligible(value))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(recursive_signals_eligible(item))

    return values


def normalize_candidate(
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
                "security_id",
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
            "composite_score",
            "final_score",
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
            "decision",
        ),
    )

    if explicit_signal is not None:
        signal = str(explicit_signal).strip().upper()
        if signal not in {"BUY", "LONG"}:
            return None
    else:
        # No signal field is accepted only because this row came from a real
        # candidate array / real engine payload and passed the V9.1 threshold.
        signal = "BUY"

    trade_date = str(
        first_value(
            row,
            (
                "trade_date",
                "market_date",
                "signal_date",
                "date",
            ),
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


def capture_and_adapt_signal_engine() -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[str],
]:
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
    emit_process(proc)

    RAW_STDOUT.write_text(proc.stdout or "", encoding="utf-8")
    RAW_STDERR.write_text(proc.stderr or "", encoding="utf-8")

    stdout_objects = json_objects_from_text(proc.stdout or "")
    dump_json(RAW_JSON_OBJECTS, stdout_objects)

    evidence_objects: list[tuple[Any, str]] = [
        (obj, f"stdout-json:{index}")
        for index, obj in enumerate(stdout_objects)
    ]

    changed_artifacts: list[Path] = []
    for path in ROOT.rglob("*.json"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/").lower()
        if "phase348" in rel:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if path not in before or mtime > before[path] + 1e-6:
            changed_artifacts.append(path)

    changed_artifacts.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in changed_artifacts[:100]:
        try:
            evidence_objects.append(
                (load_json(path), f"artifact:{path.relative_to(ROOT)}")
            )
        except Exception:
            continue

    raw_signal_counts: list[int] = []
    normalized: list[dict[str, Any]] = []
    schema_paths: list[str] = []

    for obj, source in evidence_objects:
        raw_signal_counts.extend(recursive_signals_eligible(obj))

        for row, fallback_date, fallback_strategy, path in recursive_contexts(obj):
            item = normalize_candidate(
                row,
                fallback_date,
                fallback_strategy,
                source,
            )
            if item:
                normalized.append(item)
                schema_paths.append(f"{source}:{path}")

    # Deduplicate by date+symbol, keep the strongest score.
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for item in normalized:
        key = (item["trade_date"], item["symbol"])
        previous = best.get(key)
        if previous is None or float(item["total_score"]) > float(previous["total_score"]):
            best[key] = item

    normalized = list(best.values())
    if normalized:
        latest = max(x["trade_date"] for x in normalized)
        normalized = [x for x in normalized if x["trade_date"] == latest]
        normalized.sort(key=lambda x: (-float(x["total_score"]), x["symbol"]))
        normalized = normalized[:MAX_CANDIDATES]

    reported_signals_eligible = max(raw_signal_counts, default=0)

    payload_schema_recognized = bool(
        stdout_objects
        or changed_artifacts
        or raw_signal_counts
        or normalized
    )

    schema_mismatch = (
        reported_signals_eligible > 0
        and len(normalized) == 0
    )

    capture = {
        "version": "3.4.8.4.4",
        "signal_engine": str(SIGNAL_ENGINE.relative_to(ROOT)),
        "signal_engine_exit_code": proc.returncode,
        "stdout_json_objects": len(stdout_objects),
        "changed_json_artifacts": [
            str(path.relative_to(ROOT))
            for path in changed_artifacts[:100]
        ],
        "payload_schema_recognized": payload_schema_recognized,
        "reported_signals_eligible": reported_signals_eligible,
        "raw_signals_eligible_values": raw_signal_counts,
        "candidate_schema_paths": schema_paths[:100],
        "eligible_real_v91_signals": len(normalized),
        "schema_mismatch": schema_mismatch,
        "signals": normalized,
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
    }
    dump_json(SCHEMA_CAPTURE, capture)

    diagnostics.append(f"Signal engine exit code: {proc.returncode}")
    diagnostics.append(f"stdout JSON objects: {len(stdout_objects)}")
    diagnostics.append(f"same-run JSON artifacts: {len(changed_artifacts)}")
    diagnostics.append(f"reported signals_eligible: {reported_signals_eligible}")
    diagnostics.append(f"adapted eligible candidates: {len(normalized)}")

    if schema_mismatch:
        diagnostics.append(
            "PAYLOAD_SCHEMA_MISMATCH: engine reported eligible signals but "
            "no candidate rows could be normalized."
        )

    if proc.returncode != 0 and not normalized:
        diagnostics.append(
            "Signal engine returned non-zero and no eligible real evidence was captured."
        )

    return normalized, capture, diagnostics


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
                first_value(
                    row,
                    ("trade_date", "market_date", "date"),
                )
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
            previous = by_symbol.get(item["symbol"])
            if previous is None or item["trade_date"] > previous["trade_date"]:
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
    batch_id = "P34844-" + stable_hash(seed)[:24]

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
        [("select", "*"), ("canonical_batch_id", f"eq.{batch_id}")],
    )
    if sig_error:
        raise RuntimeError(sig_error)

    persisted_prices, price_error = rest_get(
        MARKET_STORE,
        [("select", "*"), ("canonical_batch_id", f"eq.{batch_id}")],
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


def run_phase348(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE348_SIGNAL_JSON"] = str(CANONICAL_SIGNALS)
    env["PHASE348_MARKET_JSON"] = str(CANONICAL_MARKET)
    env["PHASE348_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE348_MAX_CANDIDATES"] = str(MAX_CANDIDATES)

    proc = run_python(PHASE348, ["--approver", approver], env)
    emit_process(proc)

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
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.4",
        "",
        "## V9.1 Signal Engine Runtime Payload Schema Adapter Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        "",
        "### Runtime Payload Schema",
        "",
        f"- Signal Engine: `{result['signal_engine']}`",
        f"- Signal Engine Exit Code: **{result['signal_engine_exit_code']}**",
        f"- Payload Schema Recognized: **{'YES' if result['payload_schema_recognized'] else 'NO'}**",
        f"- Reported signals_eligible: **{result['reported_signals_eligible']}**",
        f"- Adapted Eligible Real V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- Payload Schema Mismatch: **{'YES' if result['payload_schema_mismatch'] else 'NO'}**",
        f"- Schema Capture: `{result['schema_capture_file']}`",
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
        lines.extend(f"- {x}" for x in result["diagnostics"][:50])

    text = "\n".join(lines) + "\n"
    (OUT / "phase34844_schema_adapter_fix.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE34844_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: mode must remain SHADOW_ONLY_NO_BROKER")

    gate = run_gate(approver)

    signals, capture, signal_diagnostics = capture_and_adapt_signal_engine()

    # This is the core V4.4 fail-closed improvement.
    if capture["schema_mismatch"]:
        result = {
            "version": "3.4.8.4.4",
            "status": "BLOCKED",
            "strategy_version": STRATEGY,
            "trading_mode": MODE,
            "contract": CONTRACT,
            "safety_contract": SAFETY_CONTRACT,
            "runtime_execution_gate": gate["runtime_execution_gate"],
            "signal_engine": str(SIGNAL_ENGINE.relative_to(ROOT)),
            "signal_engine_exit_code": capture["signal_engine_exit_code"],
            "payload_schema_recognized": capture["payload_schema_recognized"],
            "reported_signals_eligible": capture["reported_signals_eligible"],
            "eligible_v91_signals": 0,
            "payload_schema_mismatch": True,
            "schema_capture_file": str(SCHEMA_CAPTURE.relative_to(ROOT)),
            "canonical_batch_id": "NONE",
            "signals_persisted": 0,
            "market_price_source": None,
            "prices_persisted": 0,
            "execution_state": "BLOCKED_PAYLOAD_SCHEMA_MISMATCH",
            "paper_orders_created": 0,
            "simulated_fills": 0,
            "open_positions": 0,
            "synthetic_fallback_allowed": False,
            "synthetic_evidence_present": False,
            "fake_prices_allowed": False,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "diagnostics": signal_diagnostics,
        }
        write_summary(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise RuntimeError(
            "PAYLOAD_SCHEMA_MISMATCH: signal engine reported eligible signals "
            "but no real candidate rows could be adapted. See schema capture artifact."
        )

    prices, market_source, market_diagnostics = discover_market_prices(signals)

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

    diagnostics = [*signal_diagnostics, *market_diagnostics]

    result = {
        "version": "3.4.8.4.4",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": gate["runtime_execution_gate"],
        "signal_engine": str(SIGNAL_ENGINE.relative_to(ROOT)),
        "signal_engine_exit_code": capture["signal_engine_exit_code"],
        "payload_schema_recognized": capture["payload_schema_recognized"],
        "reported_signals_eligible": capture["reported_signals_eligible"],
        "eligible_v91_signals": len(signals),
        "payload_schema_mismatch": False,
        "schema_capture_file": str(SCHEMA_CAPTURE.relative_to(ROOT)),
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
        raise RuntimeError("Eligible real V9.1 signal evidence exists but persistence is empty")

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
        raise RuntimeError("Safety violation: orders created without real prices")

    write_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE34844 PASS: runtime payload schema adaptation -> canonical persistence -> "
        "Phase 3.4.8 complete. "
        f"reported_eligible={capture['reported_signals_eligible']}, "
        f"adapted={len(signals)}, prices={len(prices)}, "
        f"orders={result['paper_orders_created']}, fills={result['simulated_fills']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
