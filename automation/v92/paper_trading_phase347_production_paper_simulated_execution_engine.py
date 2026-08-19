#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase347_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"

INITIAL_CASH = float(os.getenv("PHASE347_INITIAL_CASH", "1000000"))
MAX_POSITION_PCT = float(os.getenv("PHASE347_MAX_POSITION_PCT", "0.20"))
MAX_NEW_POSITIONS = int(os.getenv("PHASE347_MAX_NEW_POSITIONS", "3"))
SCORE_THRESHOLD = float(os.getenv("PHASE347_SCORE_THRESHOLD", "65"))
ROUND_LOT = int(os.getenv("PHASE347_ROUND_LOT", "1000"))

PHASE346 = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase346_production_paper_runtime_execution_gate.py"
)

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"

CONTRACT = "PHASE347_PRODUCTION_PAPER_SIMULATED_EXECUTION_ENGINE"
SAFETY_CONTRACT = "PAPER_SIMULATION_ONLY_ZERO_BROKER_ZERO_REAL_MONEY"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing JSON evidence: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON object: {path}")
    return data


def sha256_payload(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def run_gate(approver: str) -> None:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    proc = subprocess.run(
        [
            sys.executable,
            str(PHASE346),
            "--approver",
            approver,
            "--note",
            "Phase 3.4.7 same-run runtime gate reconstruction",
        ],
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
        raise RuntimeError(f"Phase 3.4.6 runtime gate failed with exit code {proc.returncode}")


def discover_signal_candidates() -> list[dict[str, Any]]:
    """
    Prefer Phase 2.x / production evidence artifacts when present.
    Fall back to deterministic dry-run candidates ONLY for infrastructure validation.
    The fallback remains paper-only and is explicitly labeled synthetic_evidence=true.
    """

    candidate_paths = [
        ROOT / "phase21_output/signals.json",
        ROOT / "phase28_output/signals.json",
        ROOT / "phase29_output/signals.json",
        ROOT / "phase30_output/signals.json",
        ROOT / "phase32_output/signals.json",
        ROOT / "output/signals.json",
        ROOT / "artifacts/signals.json",
    ]

    for path in candidate_paths:
        if not path.exists():
            continue

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        rows: list[dict[str, Any]] = []
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            for key in ("signals", "top_candidates", "candidates", "items", "data"):
                if isinstance(raw.get(key), list):
                    rows = raw[key]
                    break

        normalized: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue

            symbol = str(
                item.get("symbol")
                or item.get("stock_id")
                or item.get("ticker")
                or ""
            ).strip()

            if not symbol:
                continue

            try:
                score = float(
                    item.get("total_score")
                    if item.get("total_score") is not None
                    else item.get("score", 0)
                )
            except (TypeError, ValueError):
                score = 0.0

            signal = str(item.get("signal") or item.get("action") or "BUY").upper()

            price = None
            for key in ("close", "price", "last_price", "market_price"):
                if item.get(key) is not None:
                    try:
                        price = float(item[key])
                    except (TypeError, ValueError):
                        price = None
                    if price and price > 0:
                        break

            if signal not in ("BUY", "LONG"):
                continue
            if score < SCORE_THRESHOLD:
                continue

            normalized.append(
                {
                    "symbol": symbol,
                    "score": round(score, 4),
                    "signal": "BUY",
                    "price": price,
                    "source": str(path.relative_to(ROOT)),
                    "synthetic_evidence": False,
                }
            )

        if normalized:
            normalized.sort(key=lambda x: (-x["score"], x["symbol"]))
            return normalized[:MAX_NEW_POSITIONS]

    # Infrastructure-validation fallback.
    # Prices are deliberately fixed test marks and are NOT real market quotes.
    fallback = [
        {
            "symbol": "2454",
            "score": 76.16,
            "signal": "BUY",
            "price": 1000.0,
            "source": "PHASE347_DETERMINISTIC_INFRASTRUCTURE_FALLBACK",
            "synthetic_evidence": True,
        },
        {
            "symbol": "2330",
            "score": 70.0,
            "signal": "BUY",
            "price": 1000.0,
            "source": "PHASE347_DETERMINISTIC_INFRASTRUCTURE_FALLBACK",
            "synthetic_evidence": True,
        },
    ]
    return fallback[:MAX_NEW_POSITIONS]


def round_lot_quantity(target_notional: float, price: float) -> int:
    if price <= 0:
        return 0

    raw_qty = int(target_notional // price)
    if ROUND_LOT <= 1:
        return max(raw_qty, 0)

    board_lot_qty = (raw_qty // ROUND_LOT) * ROUND_LOT
    if board_lot_qty > 0:
        return board_lot_qty

    # For infrastructure testing, allow an odd-lot quantity when portfolio
    # capital is not large enough for a full Taiwan board lot.
    return max(raw_qty, 0)


def simulate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    cash = INITIAL_CASH
    positions: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []

    eligible = [
        c for c in candidates
        if c["signal"] == "BUY"
        and float(c["score"]) >= SCORE_THRESHOLD
        and c.get("price")
        and float(c["price"]) > 0
    ]

    if not eligible:
        return {
            "cash": cash,
            "positions": positions,
            "orders": orders,
            "fills": fills,
            "eligible_candidates": [],
        }

    per_position_cap = INITIAL_CASH * MAX_POSITION_PCT

    for rank, c in enumerate(eligible[:MAX_NEW_POSITIONS], start=1):
        price = float(c["price"])
        budget = min(per_position_cap, cash)
        qty = round_lot_quantity(budget, price)

        if qty <= 0:
            continue

        notional = round(qty * price, 4)
        if notional > cash:
            qty = int(cash // price)
            notional = round(qty * price, 4)

        if qty <= 0 or notional <= 0:
            continue

        order_id = f"P347-{rank:02d}-{c['symbol']}"
        fill_id = f"{order_id}-FILL"

        order = {
            "order_id": order_id,
            "symbol": c["symbol"],
            "side": "BUY",
            "order_type": "PAPER_MARKET",
            "quantity": qty,
            "reference_price": price,
            "status": "SIMULATED_FILLED",
            "broker_submitted": False,
            "real_money": False,
            "source": c["source"],
            "synthetic_evidence": c["synthetic_evidence"],
        }

        fill = {
            "fill_id": fill_id,
            "order_id": order_id,
            "symbol": c["symbol"],
            "side": "BUY",
            "quantity": qty,
            "fill_price": price,
            "gross_notional": notional,
            "commission": 0.0,
            "tax": 0.0,
            "slippage": 0.0,
            "execution_venue": "GPT_QUANT_PAPER_SIMULATOR",
            "broker_submitted": False,
            "real_money": False,
        }

        cash = round(cash - notional, 4)

        position = {
            "symbol": c["symbol"],
            "quantity": qty,
            "average_cost": price,
            "mark_price": price,
            "market_value": notional,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "source_score": c["score"],
            "synthetic_evidence": c["synthetic_evidence"],
        }

        orders.append(order)
        fills.append(fill)
        positions.append(position)

    return {
        "cash": cash,
        "positions": positions,
        "orders": orders,
        "fills": fills,
        "eligible_candidates": eligible,
    }


def write_files(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = sha256_payload(result)

    (OUT / "phase347_execution.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    (OUT / "phase347_orders.json").write_text(
        json.dumps(result["orders"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    (OUT / "phase347_fills.json").write_text(
        json.dumps(result["fills"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    (OUT / "phase347_positions.json").write_text(
        json.dumps(result["positions"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    (OUT / "phase347_portfolio.json").write_text(
        json.dumps(result["portfolio"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.7",
        "",
        "## Production Paper Simulated Execution Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Execution Contract: **{result['execution_contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        (
            "- Paper Execution Authorized: "
            f"**{'YES' if result['paper_execution_authorized'] else 'NO'}**"
        ),
        "",
        "### Execution",
        "",
        f"- Candidates Discovered: **{result['candidates_discovered']}**",
        f"- Eligible Candidates: **{result['eligible_candidates_count']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
        "",
        "### Portfolio",
        "",
        f"- Initial Cash: **{result['portfolio']['initial_cash']:.2f}**",
        f"- Ending Cash: **{result['portfolio']['cash']:.2f}**",
        f"- Market Value: **{result['portfolio']['market_value']:.2f}**",
        f"- NAV: **{result['portfolio']['nav']:.2f}**",
        f"- Realized P&L: **{result['portfolio']['realized_pnl']:.2f}**",
        f"- Unrealized P&L: **{result['portfolio']['unrealized_pnl']:.2f}**",
        "",
        "### Safety Boundary",
        "",
        "- Production Paper only: **YES**",
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
        (
            "- Synthetic infrastructure evidence present: "
            f"**{'YES' if result['synthetic_evidence_present'] else 'NO'}**"
        ),
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    if result.get("errors"):
        lines.extend(["", "### Errors", ""])
        lines.extend(f"- {e}" for e in result["errors"])

    summary = "\n".join(lines) + "\n"
    (OUT / "phase347_execution.md").write_text(summary, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(summary)


def blocked_result(gate: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    portfolio = {
        "initial_cash": INITIAL_CASH,
        "cash": INITIAL_CASH,
        "market_value": 0.0,
        "nav": INITIAL_CASH,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }

    return {
        "version": "3.4.7",
        "status": "BLOCKED",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "execution_contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": gate.get("runtime_execution_gate", "BLOCKED"),
        "paper_execution_authorized": False,
        "candidates_discovered": 0,
        "eligible_candidates_count": 0,
        "paper_orders_created": 0,
        "simulated_fills": 0,
        "open_positions": 0,
        "orders": [],
        "fills": [],
        "positions": [],
        "portfolio": portfolio,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": True,
        "synthetic_evidence_present": False,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE347_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: mode must remain SHADOW_ONLY_NO_BROKER")

    if not PHASE346.exists():
        raise RuntimeError(f"Missing Phase 3.4.6 engine: {PHASE346}")

    run_gate(approver)
    gate = load_json(GATE_JSON)

    gate_errors: list[str] = []
    if gate.get("status") != "PASS":
        gate_errors.append("Phase 3.4.6 status is not PASS")
    if gate.get("runtime_execution_gate") != "OPEN":
        gate_errors.append("Runtime Execution Gate is not OPEN")
    if gate.get("paper_execution_authorized") is not True:
        gate_errors.append("Paper Execution Authorized is not true")
    if gate.get("production_paper_release_state") != "ACTIVE":
        gate_errors.append("Production Paper Release is not ACTIVE")
    if gate.get("broker_trading_enabled") is not False:
        gate_errors.append("Broker trading safety lock is not disabled")
    if gate.get("broker_order_submission_enabled") is not False:
        gate_errors.append("Broker order submission safety lock is not disabled")
    if gate.get("real_money_trading_enabled") is not False:
        gate_errors.append("Real-money trading safety lock is not disabled")
    if gate.get("live_money_release_authorized") is not False:
        gate_errors.append("Live-money release must remain unauthorized")

    if gate_errors:
        result = blocked_result(gate, gate_errors)
        write_files(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            "PHASE347 BLOCKED / FAIL-CLOSED: " + "; ".join(gate_errors),
            file=sys.stderr,
        )
        return 2

    candidates = discover_signal_candidates()
    sim = simulate(candidates)

    positions = sim["positions"]
    market_value = round(sum(float(p["market_value"]) for p in positions), 4)
    unrealized = round(sum(float(p["unrealized_pnl"]) for p in positions), 4)
    realized = round(sum(float(p["realized_pnl"]) for p in positions), 4)
    cash = round(float(sim["cash"]), 4)
    nav = round(cash + market_value, 4)

    synthetic_present = any(
        bool(x.get("synthetic_evidence"))
        for x in candidates
    )

    result: dict[str, Any] = {
        "version": "3.4.7",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "execution_contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": "OPEN",
        "paper_execution_authorized": True,
        "production_paper_release_state": "ACTIVE",
        "candidates_discovered": len(candidates),
        "eligible_candidates_count": len(sim["eligible_candidates"]),
        "paper_orders_created": len(sim["orders"]),
        "simulated_fills": len(sim["fills"]),
        "open_positions": len(positions),
        "orders": sim["orders"],
        "fills": sim["fills"],
        "positions": positions,
        "portfolio": {
            "initial_cash": INITIAL_CASH,
            "cash": cash,
            "market_value": market_value,
            "nav": nav,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
        },
        "risk_limits": {
            "max_position_pct": MAX_POSITION_PCT,
            "max_new_positions": MAX_NEW_POSITIONS,
            "score_threshold": SCORE_THRESHOLD,
            "round_lot": ROUND_LOT,
        },
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": False,
        "synthetic_evidence_present": synthetic_present,
        "errors": [],
    }

    write_files(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE347 PASS: Production Paper simulated execution completed. "
        f"orders={len(sim['orders'])}, fills={len(sim['fills'])}, nav={nav:.2f}. "
        "Zero broker orders; zero real money."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
