#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase348452_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"

UPSTREAM = ROOT / "automation/v92/paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix.py"
UPSTREAM_JSON = ROOT / "phase348451_output/phase348451_signal_input_contract_fix.json"

RESULT_JSON = OUT / "phase348452_zero_eligible_valid_state.json"

CONTRACT = "PHASE348452_ZERO_ELIGIBLE_SIGNAL_VALID_STATE_CONTRACT_FIX"
SAFE_ZERO_STATE = "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"

ALLOWED_UPSTREAM_EXECUTION_STATES = {
    "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
    "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
    "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
    "REAL_CANONICAL_EVIDENCE_EXECUTED",
}


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_upstream(approver: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    proc = subprocess.run(
        [sys.executable, str(UPSTREAM), "--approver", approver],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if not UPSTREAM_JSON.exists():
        raise RuntimeError(
            f"Phase 3.4.8.4.5.1 evidence missing; exit code={proc.returncode}"
        )

    return proc, load_json(UPSTREAM_JSON)


def validate_safety(data: dict[str, Any]) -> None:
    expected_false = {
        "synthetic_market_data": False,
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }

    errors = [
        f"{key}={data.get(key)!r}, expected=False"
        for key, expected in expected_false.items()
        if data.get(key) is not expected
    ]

    if data.get("fail_closed_policy") is not True:
        errors.append(
            f"fail_closed_policy={data.get('fail_closed_policy')!r}, expected=True"
        )

    if errors:
        raise RuntimeError("Safety contract violation: " + "; ".join(errors))


def classify(data: dict[str, Any]) -> tuple[str, str]:
    market_source = data.get("market_data_source")
    stocks_with_history = int(data.get("stocks_with_history") or 0)
    rows_scanned = int(data.get("rows_scanned") or 0)
    engine_exit = int(data.get("signal_engine_exit_code") or 0)
    engine_scanned = int(data.get("signal_engine_stocks_scanned") or 0)
    reported = int(data.get("reported_signals_eligible") or 0)
    adapted = int(data.get("eligible_v91_signals") or 0)
    orders = int(data.get("paper_orders_created") or 0)
    fills = int(data.get("simulated_fills") or 0)
    execution_state = data.get("execution_state")

    if not market_source:
        raise RuntimeError("NO_REAL_MARKET_SOURCE")

    if stocks_with_history <= 0 or rows_scanned <= 0:
        raise RuntimeError(
            "MARKET_INPUT_INVALID: real source exists but usable market history is empty"
        )

    if engine_exit != 0:
        raise RuntimeError(
            f"SIGNAL_ENGINE_FAILED: exit code={engine_exit}"
        )

    if engine_scanned <= 0:
        raise RuntimeError(
            "SIGNAL_INPUT_CONTRACT_MISMATCH: market history exists but signal engine scanned zero stocks"
        )

    if execution_state not in ALLOWED_UPSTREAM_EXECUTION_STATES:
        raise RuntimeError(
            f"Unexpected upstream execution_state={execution_state!r}"
        )

    # This is the exact valid state this patch introduces.
    if reported == 0 and adapted == 0:
        if orders != 0 or fills != 0:
            raise RuntimeError(
                "Safety violation: zero eligible V9.1 signals must produce zero orders/fills"
            )

        return SAFE_ZERO_STATE, (
            "Real market data and signal-engine input are healthy; "
            "no V9.1 candidates met the configured eligibility threshold."
        )

    # If the engine says signals exist, adapter and persistence must agree.
    if reported > 0:
        if adapted <= 0:
            raise RuntimeError(
                "SIGNAL_OUTPUT_CONTRACT_MISMATCH: reported eligible > 0 but adapted signals = 0"
            )

        if int(data.get("signals_persisted") or 0) <= 0:
            raise RuntimeError(
                "Canonical signal persistence missing for real eligible signals"
            )

    if orders > 0:
        if int(data.get("prices_persisted") or 0) <= 0:
            raise RuntimeError(
                "Paper orders exist without persisted real market prices"
            )
        if execution_state != "REAL_CANONICAL_EVIDENCE_EXECUTED":
            raise RuntimeError(
                "Paper orders exist without REAL_CANONICAL_EVIDENCE_EXECUTED"
            )
        if fills != orders:
            raise RuntimeError(
                "Paper order/fill mismatch"
            )

    return execution_state or "PASS", "Upstream canonical execution contract is valid."


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.5.2",
        "",
        "## Zero Eligible Signal Valid-State Contract Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        "",
        "### Runtime Market + Signal Input",
        "",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Active Stocks: **{result['active_stocks']}**",
        f"- Stocks With History: **{result['stocks_with_history']}**",
        f"- Rows Scanned: **{result['rows_scanned']}**",
        f"- Latest Market Date: `{result['latest_market_date']}`",
        f"- Signal Engine Stocks Scanned: **{result['signal_engine_stocks_scanned']}**",
        f"- Top Symbol: `{result['top_symbol'] or 'NONE'}`",
        f"- Top Score: **{result['top_score'] if result['top_score'] is not None else 'NONE'}**",
        f"- Score Threshold: **{result['score_threshold']}**",
        "",
        "### Eligibility Contract",
        "",
        f"- Reported signals_eligible: **{result['reported_signals_eligible']}**",
        f"- Adapted Eligible V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- Canonical Valid State: **{result['canonical_valid_state']}**",
        f"- State Reason: {result['state_reason']}",
        "",
        "### Paper Execution",
        "",
        f"- Upstream Execution State: **{result['upstream_execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
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
    ]

    text = "\n".join(lines) + "\n"

    (OUT / "phase348452_zero_eligible_valid_state.md").write_text(
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
        default=os.getenv("PHASE348452_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety violation: mode must remain SHADOW_ONLY_NO_BROKER"
        )

    proc, upstream = run_upstream(approver)
    validate_safety(upstream)

    canonical_state, reason = classify(upstream)

    result = {
        "version": "3.4.8.4.5.2",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "upstream_process_exit_code": proc.returncode,
        "market_data_source": upstream.get("market_data_source"),
        "active_stocks": upstream.get("active_stocks"),
        "stocks_with_history": upstream.get("stocks_with_history"),
        "rows_scanned": upstream.get("rows_scanned"),
        "latest_market_date": upstream.get("latest_market_date"),
        "signal_engine_stocks_scanned": upstream.get("signal_engine_stocks_scanned"),
        "score_threshold": upstream.get("score_threshold"),
        "reported_signals_eligible": upstream.get("reported_signals_eligible"),
        "eligible_v91_signals": upstream.get("eligible_v91_signals"),
        "top_symbol": upstream.get("top_symbol"),
        "top_score": upstream.get("top_score"),
        "signals_persisted": upstream.get("signals_persisted"),
        "prices_persisted": upstream.get("prices_persisted"),
        "upstream_execution_state": upstream.get("execution_state"),
        "canonical_valid_state": canonical_state,
        "state_reason": reason,
        "paper_orders_created": upstream.get("paper_orders_created", 0),
        "simulated_fills": upstream.get("simulated_fills", 0),
        "open_positions": upstream.get("open_positions", 0),
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

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    print(
        "PHASE348452 PASS: zero-eligible valid-state contract accepted. "
        f"state={canonical_state}, "
        f"market={result['market_data_source']}, "
        f"engine_scanned={result['signal_engine_stocks_scanned']}, "
        f"eligible={result['eligible_v91_signals']}, "
        f"orders={result['paper_orders_created']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
