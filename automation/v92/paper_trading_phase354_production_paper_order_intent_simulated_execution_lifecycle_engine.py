#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase354_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE354_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py"
UPSTREAM_JSON = ROOT / "phase353_output/phase353_position_sizing.json"

PLAN_TABLE = "paper_position_sizing_plans_v92"
ITEM_TABLE = "paper_position_sizing_items_v92"
INTENT_TABLE = "paper_order_intents_v92"
FILL_TABLE = "paper_simulated_fills_v92"
CYCLE_TABLE = "paper_execution_cycles_v92"

RESULT_JSON = OUT / "phase354_execution_lifecycle.json"

CONTRACT = "PHASE354_PRODUCTION_PAPER_ORDER_INTENT_SIMULATED_EXECUTION_LIFECYCLE_ENGINE"

ZERO_ORDER = "ZERO_ORDER_VALID_STATE"
INTENTS_CREATED = "PAPER_ORDER_INTENTS_CREATED"
EXECUTED = "PAPER_SIMULATED_EXECUTION_COMPLETED"
HALT_ZERO = "PAPER_HALT_ZERO_ORDERS"


def D(v: Any) -> Decimal:
    return Decimal(str(v))


def money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def supabase() -> tuple[str, dict[str, str]]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not base or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing")

    return base, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(table: str, params: list[tuple[str, str]]) -> list[dict[str, Any]]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.get(url, headers=headers, params=params, timeout=25)

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:900]}"
        )

    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(f"{table}: expected list response")

    return [x for x in data if isinstance(x, dict)]


def rest_upsert(
    table: str,
    rows: list[dict[str, Any]],
    on_conflict: str,
) -> None:
    if not rows:
        return

    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.post(
        url,
        headers=headers,
        params={"on_conflict": on_conflict},
        data=json.dumps(rows, ensure_ascii=False, default=str),
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1200]}"
        )


def run_upstream() -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE353_PORTFOLIO_ID"] = PORTFOLIO_ID

    proc = subprocess.run(
        [sys.executable, str(UPSTREAM)],
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
            f"Phase 3.5.3 evidence missing; upstream exit={proc.returncode}"
        )

    return proc.returncode, load_json(UPSTREAM_JSON)


def validate_sizing(data: dict[str, Any]) -> None:
    if data.get("status") != "PASS":
        raise RuntimeError("Phase 3.5.3 sizing did not PASS")

    for key in (
        "synthetic_market_data",
        "synthetic_signals",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    ):
        if data.get(key) is not False:
            raise RuntimeError(
                f"Safety contract violation: {key}={data.get(key)!r}"
            )

    if data.get("fail_closed_policy") is not True:
        raise RuntimeError("fail_closed_policy must remain enabled")

    if data.get("paper_halt") is True:
        if data.get("new_paper_entries_authorized") is not False:
            raise RuntimeError("PAPER_HALT cannot authorize new paper entries")
        if float(data.get("total_allocated_capital") or 0) != 0:
            raise RuntimeError("PAPER_HALT cannot carry non-zero allocation")


def latest_plan(plan_date: str) -> dict[str, Any]:
    rows = rest_get(
        PLAN_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("plan_date", f"eq.{plan_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("No persisted Phase 3.5.3 sizing plan found")

    return rows[0]


def sizing_items(plan_id: str) -> list[dict[str, Any]]:
    return rest_get(
        ITEM_TABLE,
        [
            ("select", "*"),
            ("plan_id", f"eq.{plan_id}"),
            ("order", "rank.asc"),
        ],
    )


def create_intents(
    plan: dict[str, Any],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if plan.get("paper_halt") is True:
        return []

    if plan.get("new_paper_entries_authorized") is not True:
        return []

    intents: list[dict[str, Any]] = []

    for item in items:
        if item.get("allocation_state") != "SIZED":
            continue

        qty = D(item.get("paper_quantity") or 0)
        price = D(item.get("real_market_price") or 0)
        notional = D(item.get("estimated_notional") or 0)

        if qty <= 0 or price <= 0 or notional <= 0:
            raise RuntimeError(
                f"Invalid sized item for {item.get('symbol')}"
            )

        seed = {
            "plan_id": plan["plan_id"],
            "symbol": item["symbol"],
            "qty": str(qty),
            "price": str(price),
            "notional": str(notional),
        }

        order_intent_id = "P354O-" + stable_hash(seed)[:28]

        intents.append(
            {
                "order_intent_id": order_intent_id,
                "plan_id": plan["plan_id"],
                "portfolio_id": PORTFOLIO_ID,
                "strategy_version": STRATEGY,
                "intent_date": str(plan["plan_date"]),
                "symbol": item["symbol"],
                "side": "BUY",
                "quantity": str(qty),
                "reference_price": str(price),
                "estimated_notional": str(money(notional)),
                "risk_state": plan["risk_state"],
                "allocation_state": item["allocation_state"],
                "intent_state": "READY_FOR_SIMULATED_EXECUTION",
                "synthetic_market_data": False,
                "synthetic_signal": False,
                "fake_price": False,
                "broker_api_used": False,
                "broker_credentials_used": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "live_money_release_authorized": False,
                "fail_closed_policy": True,
                "evidence_sha256": stable_hash(seed),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return intents


def persist_intents(intents: list[dict[str, Any]]) -> None:
    if intents:
        rest_upsert(
            INTENT_TABLE,
            intents,
            "plan_id,symbol",
        )


def simulate_fills(intents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fills: list[dict[str, Any]] = []

    for intent in intents:
        qty = D(intent["quantity"])
        px = D(intent["reference_price"])

        if qty <= 0 or px <= 0:
            raise RuntimeError("Invalid simulated fill input")

        seed = {
            "order_intent_id": intent["order_intent_id"],
            "symbol": intent["symbol"],
            "qty": str(qty),
            "fill_price": str(px),
        }

        fill_id = "P354F-" + stable_hash(seed)[:28]

        fills.append(
            {
                "fill_id": fill_id,
                "order_intent_id": intent["order_intent_id"],
                "plan_id": intent["plan_id"],
                "portfolio_id": PORTFOLIO_ID,
                "strategy_version": STRATEGY,
                "fill_date": intent["intent_date"],
                "symbol": intent["symbol"],
                "side": intent["side"],
                "quantity": str(qty),
                "fill_price": str(px),
                "fill_notional": str(money(qty * px)),
                "execution_state": "SIMULATED_FILLED",
                "price_source": "phase353_real_canonical_market_price",
                "synthetic_market_data": False,
                "synthetic_signal": False,
                "fake_price": False,
                "broker_api_used": False,
                "broker_credentials_used": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "live_money_release_authorized": False,
                "fail_closed_policy": True,
                "evidence_sha256": stable_hash(seed),
            }
        )

    return fills


def persist_fills(fills: list[dict[str, Any]]) -> None:
    if fills:
        rest_upsert(
            FILL_TABLE,
            fills,
            "order_intent_id",
        )


def classify_state(
    sizing: dict[str, Any],
    intents: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> str:
    if sizing.get("paper_halt") is True:
        if intents or fills:
            raise RuntimeError("PAPER_HALT produced order/fill activity")
        return HALT_ZERO

    sized = int(sizing.get("sized_candidates") or 0)

    if sized == 0:
        if intents or fills:
            raise RuntimeError("Zero sized candidates produced order/fill activity")
        return ZERO_ORDER

    if sized > 0 and not intents:
        raise RuntimeError("Sized candidates exist but no order intents were created")

    if intents and not fills:
        return INTENTS_CREATED

    if len(fills) != len(intents):
        raise RuntimeError("Order intent / simulated fill count mismatch")

    return EXECUTED


def persist_cycle(
    sizing: dict[str, Any],
    plan: dict[str, Any],
    intents: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    execution_state: str,
) -> dict[str, Any]:
    total_fill_notional = sum(
        (D(fill["fill_notional"]) for fill in fills),
        D(0),
    )

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "cycle_date": str(plan["plan_date"]),
        "plan_id": plan["plan_id"],
        "execution_state": execution_state,
        "intents": len(intents),
        "fills": len(fills),
        "total_fill_notional": str(total_fill_notional),
    }

    cycle_id = "P354C-" + stable_hash(seed)[:28]

    row = {
        "cycle_id": cycle_id,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "cycle_date": str(plan["plan_date"]),
        "plan_id": plan["plan_id"],
        "risk_state": sizing["risk_state"],
        "new_paper_entries_authorized": bool(
            sizing["new_paper_entries_authorized"]
        ),
        "paper_halt": bool(sizing["paper_halt"]),
        "sized_candidates": int(sizing["sized_candidates"]),
        "order_intents_created": len(intents),
        "simulated_fills_created": len(fills),
        "total_fill_notional": str(money(total_fill_notional)),
        "execution_state": execution_state,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": stable_hash(seed),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    rest_upsert(
        CYCLE_TABLE,
        [row],
        "portfolio_id,cycle_date",
    )

    rows = rest_get(
        CYCLE_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("cycle_date", f"eq.{row['cycle_date']}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Execution-cycle persistence verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.5.4",
        "",
        "## Production Paper Order Intent + Simulated Execution Lifecycle Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Execution Status: **{result['status']}**",
        f"- Cycle Date: `{result['cycle_date']}`",
        "",
        "### Sizing / Governance Input",
        "",
        f"- Risk State: **{result['risk_state']}**",
        f"- New Paper Entries Authorized: **{'YES' if result['new_paper_entries_authorized'] else 'NO'}**",
        f"- Paper Halt: **{'YES' if result['paper_halt'] else 'NO'}**",
        f"- Sized Candidates: **{result['sized_candidates']}**",
        "",
        "### Paper Execution Lifecycle",
        "",
        f"- Order Intents Created: **{result['order_intents_created']}**",
        f"- Simulated Fills Created: **{result['simulated_fills_created']}**",
        f"- Total Fill Notional: **{result['total_fill_notional']:.2f}**",
        f"- Execution State: **{result['execution_state']}**",
    ]

    if result["fills"]:
        lines.extend(["", "### Simulated Fills", ""])
        for fill in result["fills"]:
            lines.append(
                f"- `{fill['symbol']}` {fill['side']} qty={fill['quantity']} "
                f"fill={fill['fill_price']} notional={fill['fill_notional']}"
            )
    else:
        lines.extend(
            [
                "",
                "### Simulated Fills",
                "",
                "- No simulated fill created; zero-order state is valid for this cycle.",
            ]
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

    (OUT / "phase354_execution_lifecycle.md").write_text(
        text,
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    upstream_exit, sizing = run_upstream()
    validate_sizing(sizing)

    plan_date = str(sizing["plan_date"])
    plan = latest_plan(plan_date)
    items = sizing_items(plan["plan_id"])

    intents = create_intents(plan, items)
    persist_intents(intents)

    fills = simulate_fills(intents)
    persist_fills(fills)

    execution_state = classify_state(
        sizing,
        intents,
        fills,
    )

    cycle = persist_cycle(
        sizing,
        plan,
        intents,
        fills,
        execution_state,
    )

    result = {
        "version": "3.5.4",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "upstream_process_exit_code": upstream_exit,
        "cycle_id": cycle["cycle_id"],
        "cycle_date": str(cycle["cycle_date"]),
        "plan_id": cycle.get("plan_id"),
        "risk_state": cycle["risk_state"],
        "new_paper_entries_authorized": bool(
            cycle["new_paper_entries_authorized"]
        ),
        "paper_halt": bool(cycle["paper_halt"]),
        "sized_candidates": int(cycle["sized_candidates"]),
        "order_intents_created": int(
            cycle["order_intents_created"]
        ),
        "simulated_fills_created": int(
            cycle["simulated_fills_created"]
        ),
        "total_fill_notional": float(
            cycle["total_fill_notional"]
        ),
        "execution_state": cycle["execution_state"],
        "intents": intents,
        "fills": fills,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": cycle["evidence_sha256"],
    }

    if result["paper_halt"]:
        if result["order_intents_created"] != 0 or result["simulated_fills_created"] != 0:
            raise RuntimeError("PAPER_HALT must remain zero-order/zero-fill")

    if result["sized_candidates"] == 0:
        if result["execution_state"] not in {ZERO_ORDER, HALT_ZERO}:
            raise RuntimeError("Zero-sized cycle has invalid execution state")

    if result["simulated_fills_created"] != result["order_intents_created"]:
        if result["execution_state"] == EXECUTED:
            raise RuntimeError("Executed cycle must have 1:1 intents/fills")

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE354 PASS: paper order-intent + simulated execution lifecycle complete. "
        f"state={result['execution_state']}, "
        f"sized={result['sized_candidates']}, "
        f"intents={result['order_intents_created']}, "
        f"fills={result['simulated_fills_created']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
