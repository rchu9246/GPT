"""Opt-in, fail-closed Supabase adapter for forward-only gptq accounting.

Activation is deliberately off by default. It requires the additive SQL
migration and an explicitly initialized lineage; historical gptq rows are
never used to invent an opening accounting balance.
"""

from __future__ import annotations

from decimal import Decimal
import os
from typing import Any

import requests

from gptq_accounting_v1 import digest, money

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False


def enabled() -> bool:
    value = os.getenv("GPTQ_P0_ACCOUNTING_ENABLED", "false").strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError("GPTQ_P0_ACCOUNTING_ENABLED must be true or false")
    return value == "true"


def _config() -> tuple[str, dict[str, str]]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("Supabase service-role configuration missing")
    return url, {"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Accept": "application/json"}


def _get(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    url, headers = _config()
    response = requests.get(f"{url}/rest/v1/{table}", params=params,
                            headers=headers, timeout=30)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError(f"Unexpected {table} response")
    return rows


def _rpc(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    url, headers = _config()
    response = requests.post(f"{url}/rest/v1/rpc/{name}", json=payload,
                             headers=headers, timeout=30)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError(f"Unexpected {name} response")
    return value


def latest_state(strategy_version: str, business_date: str) -> dict[str, Any]:
    rows = _get("gptq_paper_accounting_states_v1", {
        "select": "*", "strategy_version": f"eq.{strategy_version}",
        "business_date": f"lte.{business_date}",
        "order": "business_date.desc", "limit": "1",
    })
    if not rows:
        raise RuntimeError("MISSING_PRIOR_ACCOUNTING_STATE: activation requires explicit initialization")
    return rows[0]


def opening_cash(strategy_version: str, business_date: str) -> Decimal:
    state = latest_state(strategy_version, business_date)
    if state["business_date"] < business_date and not state["finalized"]:
        raise RuntimeError("PRIOR_ACCOUNTING_DATE_NOT_FINALIZED")
    return money(state["closing_cash"])


def _rate(name: str, default: str) -> Decimal:
    value = Decimal(os.getenv(name, default))
    if value < 0:
        raise RuntimeError(f"Negative {name}")
    return value


def post_order(order: dict[str, Any]) -> tuple[dict[str, Any], Decimal]:
    """Atomically insert a shadow order and its financial event via one RPC."""
    if order.get("status", "FILLED") != "FILLED" or order.get("side") not in {"BUY", "SELL"}:
        raise RuntimeError("Only FILLED shadow BUY/SELL events are supported")
    if order.get("execution_mode", "SHADOW_ONLY_NO_BROKER") != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Broker execution forbidden")
    for field in ("run_date", "strategy_version", "stock_id", "run_id",
                  "shares", "simulated_fill_price", "reference_price"):
        if order.get(field) is None:
            raise RuntimeError(f"Uncertain accounting event identity: {field} missing")
    order = dict(order)
    shares = Decimal(str(order["shares"]))
    fill = Decimal(str(order["simulated_fill_price"]))
    notional = money(order.get("notional", fill * shares))
    # Producers persist a four-decimal fill but calculate the notional from
    # their full-precision fill. Bound that representational difference.
    if abs(notional - money(fill * shares)) > shares * Decimal("0.00005") + Decimal("0.01"):
        raise RuntimeError("Order notional disagrees with fill and shares")
    order["notional"] = str(notional)
    side = order["side"]
    key = f"{order['strategy_version']}:{order['run_date']}:{side}:{order['stock_id']}"
    buy_fee = money(notional * _rate("PAPER_COMMISSION_RATE", "0.001425")) if side == "BUY" else money(0)
    sell_fee = money(notional * _rate("PAPER_COMMISSION_RATE", "0.001425")) if side == "SELL" else money(0)
    tax_name = "PAPER_TAX_RATE" if order.get("reason") == "SHADOW_EXIT" else "PAPER_TRANSACTION_TAX_RATE"
    tax = money(notional * _rate(tax_name, "0.003")) if side == "SELL" else money(0)
    reference = Decimal(str(order["reference_price"]))
    slippage = money(abs(reference - fill) * shares)
    cash_delta = -notional - buy_fee if side == "BUY" else notional - sell_fee - tax
    trade_pnl = money(order.get("realized_pnl", 0)) if side == "SELL" else money(0)
    cost_basis = money(order.get("accounting_cost_basis", 0)) if side == "SELL" else money(0)
    canonical_pnl = money(cash_delta - cost_basis)
    if side == "SELL" and (order.get("realized_pnl") is None or
                           order.get("accounting_cost_basis") is None or cost_basis < 0 or
                           abs(canonical_pnl - trade_pnl) >
                           shares * Decimal("0.00005") + Decimal("0.03")):
        raise RuntimeError("SELL realized P&L disagrees with persisted cost basis")
    if side == "SELL":
        trade_pnl = canonical_pnl
        order["realized_pnl"] = str(trade_pnl)
    order["commission"] = str(buy_fee if side == "BUY" else sell_fee + tax)
    order["slippage"] = str(slippage)
    order["execution_mode"] = "SHADOW_ONLY_NO_BROKER"
    content = {"order": order, "cash_delta": str(cash_delta),
               "trade_realized_pnl": str(trade_pnl), "buy_commission": str(buy_fee),
               "sell_commission": str(sell_fee), "transaction_tax": str(tax),
               "slippage": str(slippage), "cost_basis": str(cost_basis)}
    result = _rpc("gptq_paper_accounting_post_order_v1", {
        "p_order": order, "p_event_key": key, "p_event_hash": digest(content),
        "p_state_hash": digest({"event": key, "content": content}),
        "p_cash_delta": str(cash_delta), "p_trade_realized_pnl": str(trade_pnl),
        "p_buy_commission": str(buy_fee), "p_sell_commission": str(sell_fee),
        "p_transaction_tax": str(tax), "p_slippage": str(slippage),
        "p_cost_basis": str(cost_basis),
        "p_owner_run_attempt": int(os.getenv("GITHUB_RUN_ATTEMPT", "1")),
    })
    if not isinstance(result.get("order"), dict) or not isinstance(result.get("state"), dict):
        raise RuntimeError("Accounting RPC did not return committed order and state")
    return result["order"], money(result["state"]["closing_cash"])


def finalize_from_phase24(strategy_version: str, business_date: str,
                          report: dict[str, Any]) -> dict[str, Any]:
    expected = {"cash": money(report["ending_cash"]),
                "market_value": money(report["ending_market_value"]),
                "equity": money(report["ending_equity"]),
                "unrealized_pnl": money(report["unrealized_pnl"])}
    mark_key = f"{strategy_version}:{business_date}:MARK_TO_MARKET"
    content = {"market_value": str(expected["market_value"]),
               "unrealized_pnl": str(expected["unrealized_pnl"])}
    marked = _rpc("gptq_paper_accounting_apply_event_v1", {
        "p_strategy_version": strategy_version, "p_business_date": business_date,
        "p_event_key": mark_key, "p_event_type": "MARK_TO_MARKET",
        "p_event_hash": digest(content), "p_state_hash": digest({"event": mark_key, **content}),
        "p_market_value": content["market_value"],
        "p_unrealized_pnl": content["unrealized_pnl"],
        "p_owner_run_id": int(os.getenv("GITHUB_RUN_ID", "0")) or None,
        "p_owner_run_attempt": int(os.getenv("GITHUB_RUN_ATTEMPT", "1")),
    })
    # In active mode Phase 2.4 reports the owner's full same-day realized
    # total, including any earlier Phase 2 exits. A stale report fails closed.
    expected["daily_realized_pnl"] = money(report["realized_pnl_today"])
    if expected["daily_realized_pnl"] != money(marked["daily_realized_pnl"]):
        raise RuntimeError("Phase 2.4 daily realized P&L disagrees with accounting state")
    state = _rpc("gptq_paper_accounting_finalize_v1", {
        "p_strategy_version": strategy_version, "p_business_date": business_date,
        "p_expected_cash": str(expected["cash"]),
        "p_expected_market_value": str(expected["market_value"]),
        "p_expected_equity": str(expected["equity"]),
        "p_expected_daily_realized_pnl": str(expected["daily_realized_pnl"]),
        "p_expected_unrealized_pnl": str(expected["unrealized_pnl"]),
    })
    return state
