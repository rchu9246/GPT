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
OUT = ROOT / "phase34841_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
SCORE_THRESHOLD = float(os.getenv("PHASE34841_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE34841_MAX_CANDIDATES", "3"))

PHASE3484 = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase3484_v91_signal_producer_canonical_persistence_contract_fix.py"
)

P3484_JSON = ROOT / "phase3484_output/phase3484_contract_fix.json"

CANONICAL_EXPORT = ROOT / "phase21_output/signals.json"
DISCOVERY_JSON = OUT / "phase34841_discovery.json"
RESULT_JSON = OUT / "phase34841_export_fix.json"

CONTRACT = "PHASE34841_V91_RUNTIME_SIGNAL_PRODUCER_DISCOVERY_CANONICAL_EXPORT_FIX"
SAFETY_CONTRACT = "REAL_RUNTIME_SIGNAL_SOURCE_ONLY_ZERO_SYNTHETIC_ZERO_BROKER_ZERO_REAL_MONEY"

# Highest priority is based on the actual PostgREST hint surfaced in the
# Phase 3.4.8.3 diagnostics.
SUPABASE_SIGNAL_TABLES = [
    "gptq_paper_signals",
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

EXPLICIT_RUNTIME_FILES = [
    ROOT / "phase21_output/signals.json",
    ROOT / "phase21_output/phase21_signals.json",
    ROOT / "phase21_output/signal_generation.json",
    ROOT / "phase21_output/phase21_signal_generation.json",
    ROOT / "output/signals.json",
    ROOT / "output/latest_signals.json",
    ROOT / "artifacts/signals.json",
    ROOT / "artifacts/latest_signals.json",
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
            timeout=20,
        )
    except requests.RequestException as exc:
        return [], f"{table}: request error: {exc}"

    if response.status_code >= 400:
        return [], f"{table}: HTTP {response.status_code}: {response.text[:350]}"

    try:
        data = response.json()
    except ValueError:
        return [], f"{table}: invalid JSON"

    if not isinstance(data, list):
        return [], f"{table}: response was not a row list"

    return [x for x in data if isinstance(x, dict)], None


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
        or row.get("signal_date")
        or row.get("created_date")
        or ""
    ).strip()[:10]


def normalize_signal(
    row: dict[str, Any],
    source: str,
) -> dict[str, Any] | None:
    symbol = normalize_symbol(row)
    if not symbol:
        return None

    raw_signal = str(
        row.get("signal")
        or row.get("action")
        or row.get("recommendation")
        or row.get("side")
        or ""
    ).strip().upper()

    # Do not silently turn an unknown signal into BUY.
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

    explicit_strategy = row.get("strategy_version") or row.get("strategy")
    if explicit_strategy:
        if str(explicit_strategy).strip().upper() != STRATEGY.upper():
            return None

    trade_date = normalize_date(row)
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


def choose_latest(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        return []

    latest = max(x["trade_date"] for x in rows)
    selected = [x for x in rows if x["trade_date"] == latest]
    selected.sort(key=lambda x: (-float(x["total_score"]), x["symbol"]))
    return selected[:MAX_CANDIDATES]


def discover_from_supabase() -> tuple[
    list[dict[str, Any]],
    str | None,
    list[str],
]:
    diagnostics: list[str] = []

    for table in SUPABASE_SIGNAL_TABLES:
        rows, error = rest_get(
            table,
            [
                ("select", "*"),
                ("limit", "1000"),
            ],
        )

        if error:
            diagnostics.append(error)
            continue

        normalized = [
            item
            for row in rows
            if (item := normalize_signal(row, f"supabase:{table}")) is not None
        ]

        if normalized:
            return choose_latest(normalized), f"supabase:{table}", diagnostics

        diagnostics.append(
            f"{table}: readable but no eligible {STRATEGY} BUY rows >= {SCORE_THRESHOLD}"
        )

    return [], None, diagnostics


def discover_from_explicit_files() -> tuple[
    list[dict[str, Any]],
    str | None,
    list[str],
]:
    diagnostics: list[str] = []

    for path in EXPLICIT_RUNTIME_FILES:
        if not path.exists():
            continue

        try:
            rows = extract_rows(load_json(path))
        except Exception as exc:
            diagnostics.append(f"{path}: JSON read error: {exc}")
            continue

        source = (
            str(path.relative_to(ROOT))
            if path.is_relative_to(ROOT)
            else str(path)
        )

        normalized = [
            item
            for row in rows
            if (item := normalize_signal(row, source)) is not None
        ]

        if normalized:
            return choose_latest(normalized), source, diagnostics

        diagnostics.append(
            f"{source}: readable but no eligible {STRATEGY} BUY rows >= {SCORE_THRESHOLD}"
        )

    return [], None, diagnostics


def discover_from_repository_scan() -> tuple[
    list[dict[str, Any]],
    str | None,
    list[str],
]:
    diagnostics: list[str] = []
    candidates: list[Path] = []

    # Search only JSON artifacts and skip generated phase348* outputs to avoid
    # circularly consuming downstream evidence as a producer source.
    for path in ROOT.rglob("*.json"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/").lower()

        if any(
            token in rel
            for token in (
                ".git/",
                "node_modules/",
                "phase348_output/",
                "phase3481_output/",
                "phase3482_output/",
                "phase3483_output/",
                "phase3484_output/",
                "phase34841_output/",
            )
        ):
            continue

        name = path.name.lower()
        rel_text = rel.lower()

        score = 0
        if "signal" in name:
            score += 5
        if "phase21" in rel_text or "phase2" in rel_text:
            score += 4
        if "v91" in rel_text or "v9.1" in rel_text:
            score += 3
        if "candidate" in name:
            score += 2

        if score > 0:
            candidates.append(path)

    # Highest-likelihood artifacts first.
    candidates = sorted(
        set(candidates),
        key=lambda p: (
            -(
                (5 if "signal" in p.name.lower() else 0)
                + (4 if "phase21" in str(p).lower() or "phase2" in str(p).lower() else 0)
                + (3 if "v91" in str(p).lower() or "v9.1" in str(p).lower() else 0)
                + (2 if "candidate" in p.name.lower() else 0)
            ),
            len(str(p)),
            str(p),
        ),
    )[:80]

    for path in candidates:
        try:
            rows = extract_rows(load_json(path))
        except Exception:
            continue

        source = str(path.relative_to(ROOT))

        normalized = [
            item
            for row in rows
            if (item := normalize_signal(row, source)) is not None
        ]

        if normalized:
            return choose_latest(normalized), source, diagnostics

    diagnostics.append(
        f"repository scan checked {len(candidates)} likely JSON artifacts; "
        "no eligible real V9.1 BUY signal source found"
    )
    return [], None, diagnostics


def discover_real_v91_signals() -> tuple[
    list[dict[str, Any]],
    str | None,
    list[str],
]:
    all_diagnostics: list[str] = []

    # 1. Supabase runtime producer source
    rows, source, diagnostics = discover_from_supabase()
    all_diagnostics.extend(diagnostics)
    if rows:
        return rows, source, all_diagnostics

    # 2. Known runtime/local files
    rows, source, diagnostics = discover_from_explicit_files()
    all_diagnostics.extend(diagnostics)
    if rows:
        return rows, source, all_diagnostics

    # 3. Broader repository artifact discovery
    rows, source, diagnostics = discover_from_repository_scan()
    all_diagnostics.extend(diagnostics)
    if rows:
        return rows, source, all_diagnostics

    return [], None, all_diagnostics


def export_phase21_contract(
    signals: list[dict[str, Any]],
    source: str | None,
) -> None:
    payload = {
        "run_date": max(
            (x["trade_date"] for x in signals),
            default=None,
        ),
        "strategy_version": STRATEGY,
        "mode": MODE,
        "canonical_export_contract": CONTRACT,
        "producer_source": source,
        "signals": [
            {
                "symbol": x["symbol"],
                "trade_date": x["trade_date"],
                "strategy_version": STRATEGY,
                "total_score": x["total_score"],
                "signal": "BUY",
                "source": x["source"],
                "synthetic_evidence": False,
                "producer_evidence_sha256": x["producer_evidence_sha256"],
            }
            for x in signals
        ],
        "top_candidates": [
            {
                "rank": idx,
                "symbol": x["symbol"],
                "trade_date": x["trade_date"],
                "strategy_version": STRATEGY,
                "total_score": x["total_score"],
                "signal": "BUY",
                "source": x["source"],
                "synthetic_evidence": False,
            }
            for idx, x in enumerate(signals, start=1)
        ],
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
    }

    dump_json(CANONICAL_EXPORT, payload)


def run_phase3484(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE3484_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE3484_MAX_CANDIDATES"] = str(MAX_CANDIDATES)

    proc = subprocess.run(
        [sys.executable, str(PHASE3484), "--approver", approver],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(
            proc.stderr,
            file=sys.stderr,
            end="" if proc.stderr.endswith("\n") else "\n",
        )

    if proc.returncode != 0:
        raise RuntimeError(
            f"Phase 3.4.8.4 failed with exit code {proc.returncode}"
        )

    if not P3484_JSON.exists():
        raise RuntimeError("Phase 3.4.8.4 output evidence missing")

    return load_json(P3484_JSON)


def write_summary(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = stable_hash(result)
    dump_json(RESULT_JSON, result)

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.1",
        "",
        "## V9.1 Runtime Signal Producer Discovery + Canonical Export Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        "",
        "### Runtime Producer Discovery",
        "",
        f"- Discovered Producer Source: `{result['discovered_producer_source'] or 'NONE'}`",
        f"- Eligible Real V9.1 Signals: **{result['eligible_real_v91_signals']}**",
        f"- Canonical Export Path: `{result['canonical_export_path']}`",
        f"- Canonical Export Rows: **{result['canonical_export_rows']}**",
        "",
        "### Downstream Phase 3.4.8.4",
        "",
        f"- Local V9.1 Producer Source: `{result['phase3484_local_producer_source'] or 'NONE'}`",
        f"- Eligible V9.1 Signals Found: **{result['phase3484_eligible_v91_signals']}**",
        f"- Rows Round-trip Eligible: **{result['phase3484_rows_roundtrip_eligible']}**",
        f"- Phase 3.4.8.3 Producer Signal Source: `{result['phase3483_producer_signal_source'] or 'NONE'}`",
        f"- Phase 3.4.8.3 Producer Market Source: `{result['phase3483_producer_market_source'] or 'NONE'}`",
        f"- Signals Persisted: **{result['signals_persisted']}**",
        f"- Prices Persisted: **{result['prices_persisted']}**",
        f"- Execution State: **{result['execution_state']}**",
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
        lines.extend(["", "### Discovery Diagnostics", ""])
        lines.extend(f"- {x}" for x in result["diagnostics"][:40])

    text = "\n".join(lines) + "\n"
    (OUT / "phase34841_export_fix.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE34841_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety violation: mode must remain SHADOW_ONLY_NO_BROKER"
        )

    signals, source, diagnostics = discover_real_v91_signals()

    discovery = {
        "version": "3.4.8.4.1",
        "strategy_version": STRATEGY,
        "score_threshold": SCORE_THRESHOLD,
        "max_candidates": MAX_CANDIDATES,
        "discovered_producer_source": source,
        "eligible_real_v91_signals": len(signals),
        "signals": signals,
        "diagnostics": diagnostics,
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
    }
    dump_json(DISCOVERY_JSON, discovery)

    # Critical bridge: Phase 3.4.8.4 already knows how to consume this path.
    export_phase21_contract(signals, source)

    phase3484 = run_phase3484(approver)

    result = {
        "version": "3.4.8.4.1",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "discovered_producer_source": source,
        "eligible_real_v91_signals": len(signals),
        "canonical_export_path": "phase21_output/signals.json",
        "canonical_export_rows": len(signals),
        "phase3484_local_producer_source": phase3484.get(
            "local_producer_source"
        ),
        "phase3484_eligible_v91_signals": phase3484.get(
            "eligible_v91_signals_found",
            0,
        ),
        "phase3484_rows_roundtrip_eligible": phase3484.get(
            "rows_roundtrip_eligible",
            0,
        ),
        "phase3483_producer_signal_source": phase3484.get(
            "phase3483_producer_signal_source"
        ),
        "phase3483_producer_market_source": phase3484.get(
            "phase3483_producer_market_source"
        ),
        "signals_persisted": phase3484.get(
            "phase3483_signals_persisted",
            0,
        ),
        "prices_persisted": phase3484.get(
            "phase3483_prices_persisted",
            0,
        ),
        "execution_state": phase3484.get(
            "phase3483_execution_state"
        ),
        "paper_orders_created": phase3484.get(
            "paper_orders_created",
            0,
        ),
        "simulated_fills": phase3484.get(
            "simulated_fills",
            0,
        ),
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

    # Strong postconditions.
    if signals:
        if result["canonical_export_rows"] <= 0:
            raise RuntimeError("Discovered real signals were not exported")
        if result["phase3484_eligible_v91_signals"] <= 0:
            raise RuntimeError(
                "Canonical export exists, but Phase 3.4.8.4 still cannot "
                "discover eligible V9.1 signals"
            )

    if result["paper_orders_created"] > 0:
        if not source:
            raise RuntimeError("Orders exist without a discovered real producer source")
        if result["signals_persisted"] <= 0:
            raise RuntimeError("Orders exist without persisted canonical signals")
        if result["prices_persisted"] <= 0:
            raise RuntimeError("Orders exist without persisted real market prices")
        if result["execution_state"] != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError(
                "Orders exist without REAL_CANONICAL_EVIDENCE_EXECUTED"
            )

    write_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE34841 PASS: runtime producer discovery + canonical export completed. "
        f"source={source or 'NONE'}, signals={len(signals)}, "
        f"orders={result['paper_orders_created']}, "
        f"fills={result['simulated_fills']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
