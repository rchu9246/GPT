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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase34846_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
UPSTREAM = ROOT / "automation/v92/paper_trading_phase348453_canonical_market_data_metrics_propagation_contract_fix.py"
UPSTREAM_JSON = ROOT / "phase348453_output/phase348453_metrics_propagation_fix.json"

RESULT_JSON = OUT / "phase34846_daily_paper_cycle.json"

CONTRACT = "PHASE34846_ZERO_ELIGIBLE_CANONICAL_RUNTIME_COMPLETION_DAILY_PAPER_CYCLE"

ZERO_ELIGIBLE = "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"
EXECUTED = "REAL_CANONICAL_EVIDENCE_EXECUTED"

ALLOWED_CANONICAL_STATES = {
    ZERO_ELIGIBLE,
    EXECUTED,
    "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
    "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
}


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
            f"Phase 3.4.8.4.5.3 evidence missing; exit code={proc.returncode}"
        )

    return proc, load_json(UPSTREAM_JSON)


def validate_safety(data: dict[str, Any]) -> None:
    false_keys = (
        "synthetic_market_data",
        "synthetic_fallback_allowed",
        "synthetic_evidence_present",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    )

    errors = [
        f"{k}={data.get(k)!r}, expected=False"
        for k in false_keys
        if data.get(k) is not False
    ]

    if data.get("fail_closed_policy") is not True:
        errors.append("fail_closed_policy must be True")

    if errors:
        raise RuntimeError("Safety contract violation: " + "; ".join(errors))


def classify_cycle(data: dict[str, Any]) -> tuple[str, str]:
    canonical = data.get("canonical_valid_state")
    upstream_execution = data.get("upstream_execution_state")

    active = int(data.get("active_stocks") or 0)
    history = int(data.get("stocks_with_history") or 0)
    rows = int(data.get("rows_scanned") or 0)
    scanned = int(data.get("signal_engine_stocks_scanned") or 0)

    reported = int(data.get("reported_signals_eligible") or 0)
    adapted = int(data.get("eligible_v91_signals") or 0)

    signals_persisted = int(data.get("signals_persisted") or 0)
    prices_persisted = int(data.get("prices_persisted") or 0)

    orders = int(data.get("paper_orders_created") or 0)
    fills = int(data.get("simulated_fills") or 0)

    if active <= 0 or history <= 0 or rows <= 0 or scanned <= 0:
        raise RuntimeError(
            "DAILY_CYCLE_INPUT_INVALID: market/signal runtime is not healthy"
        )

    if canonical not in ALLOWED_CANONICAL_STATES:
        raise RuntimeError(
            f"Unsupported canonical runtime state: {canonical!r}"
        )

    if canonical == ZERO_ELIGIBLE:
        if reported != 0 or adapted != 0:
            raise RuntimeError(
                "ZERO_ELIGIBLE_CONTRACT_MISMATCH: zero-eligible state with non-zero eligible counts"
            )
        if orders != 0 or fills != 0:
            raise RuntimeError(
                "ZERO_ELIGIBLE_ORDER_VIOLATION: zero-eligible state must create no paper orders/fills"
            )

        return "COMPLETED", "Daily paper cycle completed safely with no eligible V9.1 signal."

    if canonical == EXECUTED or upstream_execution == EXECUTED:
        if adapted <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without eligible signals"
            )
        if signals_persisted <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without persisted signals"
            )
        if prices_persisted <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without persisted real prices"
            )
        if orders <= 0 or fills <= 0:
            raise RuntimeError(
                "EXECUTION_CONTRACT_MISMATCH: executed state without paper orders/fills"
            )
        if orders != fills:
            raise RuntimeError("Paper order/fill mismatch")

        return "COMPLETED", "Daily paper cycle completed with real canonical paper execution."

    # Other safe no-order runtime states are still a completed daily cycle.
    if orders != 0 or fills != 0:
        raise RuntimeError(
            "SAFE_ZERO_STATE_VIOLATION: safe zero-order state created orders/fills"
        )

    return "COMPLETED", f"Daily paper cycle completed in safe state {canonical}."


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.4.6",
        "",
        "## Zero-Eligible Canonical Runtime Completion + Daily Production Paper Cycle",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Daily Cycle Status: **{result['daily_cycle_status']}**",
        f"- Canonical Runtime State: **{result['canonical_runtime_state']}**",
        f"- Completion Reason: {result['completion_reason']}",
        "",
        "### Real Runtime Inputs",
        "",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Active Stocks: **{result['active_stocks']}**",
        f"- Stocks With History: **{result['stocks_with_history']}**",
        f"- Rows Scanned: **{result['rows_scanned']}**",
        f"- Latest Market Date: `{result['latest_market_date']}`",
        f"- Signal Engine Stocks Scanned: **{result['signal_engine_stocks_scanned']}**",
        f"- Score Threshold: **{result['score_threshold']}**",
        f"- Top Symbol: `{result['top_symbol'] or 'NONE'}`",
        f"- Top Score: **{result['top_score'] if result['top_score'] is not None else 'NONE'}**",
        "",
        "### Signal + Paper Execution",
        "",
        f"- Reported signals_eligible: **{result['reported_signals_eligible']}**",
        f"- Adapted Eligible V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- Signals Persisted: **{result['signals_persisted']}**",
        f"- Prices Persisted: **{result['prices_persisted']}**",
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
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    text = "\n".join(lines) + "\n"

    (OUT / "phase34846_daily_paper_cycle.md").write_text(
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
        default=os.getenv("PHASE34846_APPROVER", "rchu9246"),
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

    daily_status, reason = classify_cycle(upstream)

    result = {
        "version": "3.4.8.4.6",
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "upstream_process_exit_code": proc.returncode,
        "daily_cycle_status": daily_status,
        "canonical_runtime_state": upstream.get("canonical_valid_state"),
        "completion_reason": reason,
        "market_data_source": upstream.get("market_data_source"),
        "active_stocks": int(upstream.get("active_stocks") or 0),
        "stocks_with_history": int(upstream.get("stocks_with_history") or 0),
        "rows_scanned": int(upstream.get("rows_scanned") or 0),
        "latest_market_date": upstream.get("latest_market_date"),
        "signal_engine_stocks_scanned": int(upstream.get("signal_engine_stocks_scanned") or 0),
        "score_threshold": upstream.get("score_threshold"),
        "top_symbol": upstream.get("top_symbol"),
        "top_score": upstream.get("top_score"),
        "reported_signals_eligible": int(upstream.get("reported_signals_eligible") or 0),
        "eligible_v91_signals": int(upstream.get("eligible_v91_signals") or 0),
        "signals_persisted": int(upstream.get("signals_persisted") or 0),
        "prices_persisted": int(upstream.get("prices_persisted") or 0),
        "paper_orders_created": int(upstream.get("paper_orders_created") or 0),
        "simulated_fills": int(upstream.get("simulated_fills") or 0),
        "open_positions": int(upstream.get("open_positions") or 0),
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

    result["evidence_sha256"] = stable_hash(result)

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE34846 PASS: daily production-paper cycle completed. "
        f"state={result['canonical_runtime_state']}, "
        f"eligible={result['eligible_v91_signals']}, "
        f"orders={result['paper_orders_created']}, "
        f"fills={result['simulated_fills']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
