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
