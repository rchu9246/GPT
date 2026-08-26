"""GPT Quant V18 AI Fund Manager.

Deterministic multi-agent investment committee built from existing Supabase
quantitative signals. It does not call an external model and does not place
live broker orders.

Outputs:
- agent votes
- committee score and conviction
- dynamic target weights
- explainable PAPER proposed orders
- daily CIO report
"""
from __future__ import annotations

import math
import os
from datetime import date
from typing import Any
from urllib.parse import quote

import requests

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")

if not URL or not KEY:
    raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}
RETURN = {**HEADERS, "Prefer": "return=representation"}
UPSERT = {
    **HEADERS,
    "Prefer": "resolution=merge-duplicates,return=representation",
}

def api(table: str, query: str = "") -> str:
    return f"{URL}/rest/v1/{table}" + (f"?{query}" if query else "")

def get_rows(table: str, query: str = "") -> list[dict[str, Any]]:
    response = requests.get(api(table, query), headers=HEADERS, timeout=45)
    response.raise_for_status()
    return response.json()

def insert_rows(table: str, payload: Any) -> list[dict[str, Any]]:
    response = requests.post(api(table), headers=RETURN, json=payload, timeout=45)
    response.raise_for_status()
    return response.json()

def upsert_rows(table: str, payload: Any, conflict: str) -> list[dict[str, Any]]:
    response = requests.post(
        api(table, f"on_conflict={quote(conflict)}"),
        headers=UPSERT,
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()

def number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

def integer(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def money(value: float) -> float:
    return round(value + 1e-9, 2)

config_rows = get_rows(
    "autotrader_configs_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not config_rows:
    raise SystemExit("No autotrader config")
config = config_rows[0]

if not bool(config.get("enabled")):
    raise SystemExit("Autotrader disabled")
if bool(config.get("kill_switch")):
    raise SystemExit("Kill switch enabled")
if str(config.get("mode")) != "PAPER":
    raise SystemExit("V18 supports PAPER mode only")

account_rows = get_rows(
    "paper_accounts_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not account_rows:
    raise SystemExit("No paper account")
account = account_rows[0]

signals = get_rows(
    "signals",
    "select=stock_id,trade_date,strategy_version,total_score,trend_score,"
    "momentum_score,volume_score,risk_score,confidence"
    "&order=trade_date.desc,total_score.desc&limit=500",
)
if not signals:
    raise SystemExit("No signals")

decision_date = str(signals[0]["trade_date"])
latest = [row for row in signals if str(row["trade_date"]) == decision_date]

stocks = get_rows("stocks", "select=id,symbol,name&limit=10000")
stock_by_id = {str(row["id"]): row for row in stocks}

stock_ids = sorted({
    str(row["stock_id"]) for row in latest if row.get("stock_id") is not None
})
prices = get_rows(
    "daily_prices",
    "select=stock_id,trade_date,close,volume"
    f"&stock_id=in.({','.join(stock_ids)})"
    "&order=trade_date.desc&limit=5000",
)
price_by_id: dict[str, dict[str, Any]] = {}
for row in prices:
    stock_id = str(row["stock_id"])
    if stock_id not in price_by_id:
        price_by_id[stock_id] = row

positions = get_rows(
    "paper_positions_v13",
    f"account_name=eq.{quote(ACCOUNT)}&select=symbol,market_value&limit=1000",
)
held = {str(row["symbol"]) for row in positions}

open_orders = get_rows(
    "trade_orders_v13",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&status=in.(PROPOSED,APPROVED)&select=symbol,side&limit=1000",
)
blocked = {
    str(row["symbol"])
    for row in open_orders
    if str(row.get("side")) == "BUY"
}

cash = number(account.get("cash"))
equity = number(account.get("equity"), cash)
current_exposure = sum(number(row.get("market_value")) for row in positions)
exposure_pct = current_exposure / equity * 100 if equity else 0

avg_score = sum(number(row.get("total_score")) for row in latest) / max(1, len(latest))
avg_risk = sum(number(row.get("risk_score"), 50) for row in latest) / max(1, len(latest))

if avg_score >= 60 and avg_risk <= 45:
    regime = "RISK_ON"
    target_cash_pct = 20.0
elif avg_score >= 40 and avg_risk <= 60:
    regime = "NEUTRAL"
    target_cash_pct = number(config.get("target_cash_pct"), 30)
else:
    regime = "RISK_OFF"
    target_cash_pct = 50.0

min_weight = number(config.get("min_position_pct"), 3)
conviction_weight = number(config.get("conviction_position_pct"), 12)
max_weight = number(config.get("max_position_pct"), 15)
lot_size = max(1, integer(config.get("lot_size"), 1))
max_positions = integer(config.get("max_positions"), 5)
max_daily_orders = integer(config.get("max_daily_orders"), 5)

dedup: dict[str, dict[str, Any]] = {}
for signal in latest:
    stock = stock_by_id.get(str(signal.get("stock_id")))
    price = price_by_id.get(str(signal.get("stock_id")))
    if not stock or not price or not stock.get("symbol"):
        continue
    symbol = str(stock["symbol"])
    current = dedup.get(symbol)
    if current is None or number(signal.get("total_score")) > number(current["signal"].get("total_score")):
        dedup[symbol] = {"signal": signal, "stock": stock, "price": price}

committee_rows = []
eligible = []

for symbol, item in dedup.items():
    signal = item["signal"]
    stock = item["stock"]
    price = number(item["price"].get("close"))
    volume = number(item["price"].get("volume"))

    trend_vote = clamp(number(signal.get("trend_score")), 0, 100)
    momentum_vote = clamp(number(signal.get("momentum_score")), 0, 100)
    quality_vote = clamp(
        0.55 * number(signal.get("total_score"))
        + 0.45 * number(signal.get("confidence"), 50),
        0,
        100,
    )
    risk_vote = clamp(100 - number(signal.get("risk_score"), 50), 0, 100)
    liquidity_vote = 70 if volume > 0 else 20

    committee_score = (
        0.25 * trend_vote
        + 0.22 * momentum_vote
        + 0.23 * quality_vote
        + 0.20 * risk_vote
        + 0.10 * liquidity_vote
    )

    if committee_score >= 65:
        conviction = "HIGH"
        target_weight = min(max_weight, conviction_weight)
    elif committee_score >= 50:
        conviction = "MEDIUM"
        target_weight = min(max_weight, max(min_weight, conviction_weight * 0.65))
    elif committee_score >= 40:
        conviction = "LOW"
        target_weight = min(max_weight, min_weight)
    else:
        conviction = "AVOID"
        target_weight = 0

    decision = "WATCH"
    memo = (
        f"Trend {trend_vote:.1f}, momentum {momentum_vote:.1f}, "
        f"quality {quality_vote:.1f}, risk-adjusted {risk_vote:.1f}; "
        f"committee {committee_score:.1f}."
    )

    if symbol in held:
        decision = "HOLD"
        memo += " Existing position; no duplicate entry."
    elif symbol in blocked:
        decision = "PENDING"
        memo += " Existing open buy order."
    elif conviction in {"HIGH", "MEDIUM"} and regime != "RISK_OFF":
        decision = "BUY"
        eligible.append((committee_score, symbol, target_weight, item))
    elif conviction == "LOW":
        memo += " Conviction too low for a new position."
    else:
        memo += " Committee rejected a new position."

    committee_rows.append({
        "account_name": ACCOUNT,
        "decision_date": decision_date,
        "stock_id": signal.get("stock_id"),
        "symbol": symbol,
        "name": stock.get("name"),
        "trend_vote": trend_vote,
        "momentum_vote": momentum_vote,
        "quality_vote": quality_vote,
        "risk_vote": risk_vote,
        "liquidity_vote": liquidity_vote,
        "committee_score": committee_score,
        "conviction": conviction,
        "target_weight": target_weight,
        "cash_regime": regime,
        "decision": decision,
        "memo": memo,
    })

eligible.sort(key=lambda row: row[0], reverse=True)
slots = max(0, max_positions - len(held) - len(blocked))
available_orders = min(slots, max_daily_orders)
investable_cash = max(0.0, cash - equity * target_cash_pct / 100)

created = 0
for committee_score, symbol, target_weight, item in eligible[:available_orders]:
    price = number(item["price"].get("close"))
    target_notional = min(
        equity * target_weight / 100,
        investable_cash / max(1, available_orders - created),
    )
    raw_quantity = math.floor(target_notional / price)
    quantity = (raw_quantity // lot_size) * lot_size
    if quantity <= 0:
        continue

    key = f"{ACCOUNT}:{decision_date}:{symbol}:BUY:V18_AI_COMMITTEE"
    existing = get_rows(
        "trade_orders_v13",
        f"idempotency_key=eq.{quote(key)}&select=id&limit=1",
    )
    order_id = None
    if not existing:
        signal = item["signal"]
        rows = insert_rows(
            "trade_orders_v13",
            {
                "account_name": ACCOUNT,
                "symbol": symbol,
                "side": "BUY",
                "quantity": quantity,
                "reference_price": money(price),
                "notional": money(quantity * price),
                "score": number(signal.get("total_score")),
                "risk_score": number(signal.get("risk_score"), 50),
                "confidence": number(signal.get("confidence"), 50),
                "reason": "V18_AI_COMMITTEE",
                "mode": "PAPER",
                "status": "PROPOSED",
                "signal_date": decision_date,
                "execution_date": decision_date,
                "idempotency_key": key,
            },
        )
        order_id = rows[0]["id"]
        created += 1
        investable_cash = max(0.0, investable_cash - quantity * price)
    else:
        order_id = existing[0]["id"]

    for row in committee_rows:
        if row["symbol"] == symbol:
            row["order_id"] = order_id
            row["decision"] = "BUY"
            row["memo"] += (
                f" Proposed target weight {target_weight:.1f}% "
                f"and quantity {quantity}."
            )

for row in committee_rows:
    upsert_rows(
        "ai_committee_decisions_v18",
        row,
        "account_name,decision_date,symbol",
    )

proposed_count = len([
    row for row in open_orders if row.get("side") == "BUY"
]) + created
approved_count = len(get_rows(
    "trade_orders_v13",
    f"account_name=eq.{quote(ACCOUNT)}&status=eq.APPROVED&select=id&limit=1000",
))

chief_message = (
    f"Market regime {regime}. Committee reviewed {len(committee_rows)} symbols "
    f"and created {created} proposed orders."
)
risk_message = (
    f"Target cash {target_cash_pct:.1f}%; current exposure {exposure_pct:.1f}%. "
    f"Average signal risk {avg_risk:.1f}."
)
action_plan = (
    "Review proposed orders before simulation fill."
    if created or proposed_count
    else "Maintain cash and wait for stronger committee conviction."
)

upsert_rows(
    "cio_reports_v18",
    {
        "account_name": ACCOUNT,
        "report_date": decision_date,
        "market_regime": regime,
        "target_cash_pct": target_cash_pct,
        "portfolio_equity": equity,
        "portfolio_exposure": exposure_pct,
        "proposed_orders": proposed_count,
        "approved_orders": approved_count,
        "positions_count": len(positions),
        "chief_message": chief_message,
        "risk_message": risk_message,
        "action_plan": action_plan,
    },
    "account_name,report_date",
)

print(chief_message)
print(risk_message)
print(action_plan)
# Phase 3.7.18.5 compatibility entrypoint.
#
# ai_fund_manager_v18.py is a legacy top-level executable. Enterprise 3.0 Stable
# loads this module via importlib, so the existing AI Fund Manager body already
# runs during module loading. The orchestrator then requires a callable main().
#
# This no-op main() satisfies that compatibility contract without re-running the
# market-regime analysis, committee review, risk sizing, or proposed PAPER order
# generation a second time.
def main() -> None:
    return None
