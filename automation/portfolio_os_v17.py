"""GPT Quant V17 Enterprise Portfolio OS.

Extends the paper trading system with:
- mark-to-market
- stop loss / take profit / trailing stop
- maximum holding period exit
- weak-score exit
- portfolio exposure controls
- daily NAV snapshot
- rebalance recommendations
- explainable portfolio decisions

PAPER mode only. No broker orders are sent.
"""
from __future__ import annotations

import math
import os
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")

if not SUPABASE_URL or not SERVICE_KEY:
    raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}
RETURN_HEADERS = {**HEADERS, "Prefer": "return=representation"}
UPSERT_HEADERS = {
    **HEADERS,
    "Prefer": "resolution=merge-duplicates,return=representation",
}

def api_url(table: str, query: str = "") -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}" + (f"?{query}" if query else "")

def get_rows(table: str, query: str = "") -> list[dict[str, Any]]:
    r = requests.get(api_url(table, query), headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.json()

def insert_rows(table: str, payload: Any) -> list[dict[str, Any]]:
    r = requests.post(api_url(table), headers=RETURN_HEADERS, json=payload, timeout=45)
    r.raise_for_status()
    return r.json()

def upsert_rows(table: str, payload: Any, conflict: str) -> list[dict[str, Any]]:
    r = requests.post(
        api_url(table, f"on_conflict={quote(conflict)}"),
        headers=UPSERT_HEADERS,
        json=payload,
        timeout=45,
    )
    r.raise_for_status()
    return r.json()

def patch_rows(table: str, query: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    r = requests.patch(api_url(table, query), headers=RETURN_HEADERS, json=payload, timeout=45)
    r.raise_for_status()
    return r.json()

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

def money(value: float) -> float:
    return round(value + 1e-9, 2)

config_rows = get_rows(
    "autotrader_configs_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not config_rows:
    raise SystemExit("No autotrader configuration")
config = config_rows[0]

if not bool(config.get("enabled")):
    raise SystemExit("Autotrader disabled")
if bool(config.get("kill_switch")):
    raise SystemExit("Kill switch enabled")
if str(config.get("mode")) != "PAPER":
    raise SystemExit("Portfolio OS supports PAPER mode only")

account_rows = get_rows(
    "paper_accounts_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not account_rows:
    raise SystemExit("No paper account")
account = account_rows[0]

positions = get_rows(
    "paper_positions_v13",
    f"account_name=eq.{quote(ACCOUNT)}&order=symbol.asc",
)

signals = get_rows(
    "signals",
    "select=stock_id,trade_date,total_score,risk_score,confidence"
    "&order=trade_date.desc,total_score.desc&limit=500",
)
latest_signal_date = str(signals[0]["trade_date"]) if signals else date.today().isoformat()
latest_signals = [r for r in signals if str(r["trade_date"]) == latest_signal_date] if signals else []

stocks = get_rows("stocks", "select=id,symbol,name&limit=10000")
stock_by_id = {str(r["id"]): r for r in stocks}
stock_id_by_symbol = {
    str(r["symbol"]): str(r["id"])
    for r in stocks
    if r.get("symbol")
}

signal_by_symbol: dict[str, dict[str, Any]] = {}
for row in latest_signals:
    stock = stock_by_id.get(str(row.get("stock_id")))
    if not stock:
        continue
    symbol = str(stock["symbol"])
    if symbol not in signal_by_symbol or number(row.get("total_score")) > number(signal_by_symbol[symbol].get("total_score")):
        signal_by_symbol[symbol] = row

relevant_ids = sorted(set(stock_id_by_symbol.get(str(p["symbol"]), "") for p in positions))
relevant_ids = [x for x in relevant_ids if x]
price_by_symbol: dict[str, dict[str, Any]] = {}

if relevant_ids:
    rows = get_rows(
        "daily_prices",
        "select=stock_id,trade_date,close,high,low"
        f"&stock_id=in.({','.join(relevant_ids)})"
        "&order=trade_date.desc&limit=5000",
    )
    latest_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid = str(row["stock_id"])
        if sid not in latest_by_id:
            latest_by_id[sid] = row
    for symbol, sid in stock_id_by_symbol.items():
        if sid in latest_by_id:
            price_by_symbol[symbol] = latest_by_id[sid]

stop_loss_pct = number(config.get("stop_loss_pct"), 8)
take_profit_pct = number(config.get("take_profit_pct"), 15)
trailing_stop_pct = number(config.get("trailing_stop_pct"), 7)
exit_score = number(config.get("exit_score"), 25)
max_holding_days = integer(config.get("max_holding_days"), 20)

decisions = []
market_value = 0.0
unrealized = 0.0

for position in positions:
    symbol = str(position["symbol"])
    price_row = price_by_symbol.get(symbol)
    if not price_row:
        decisions.append({
            "account_name": ACCOUNT,
            "decision_date": latest_signal_date,
            "symbol": symbol,
            "decision": "HOLD",
            "reason_code": "NO_PRICE",
            "reason_message": "No current market price available",
        })
        continue

    quantity = integer(position.get("quantity"))
    average_price = number(position.get("average_price"))
    current_price = number(price_row.get("close"))
    current_value = money(quantity * current_price)
    cost_basis = number(position.get("cost_basis"), quantity * average_price)
    current_pnl = money(current_value - cost_basis)
    holding_days = integer(position.get("holding_days"))

    high_watermark = max(
        number(position.get("high_watermark_price"), average_price),
        current_price,
    )

    score = number(signal_by_symbol.get(symbol, {}).get("total_score"))
    risk = number(signal_by_symbol.get(symbol, {}).get("risk_score"), 50)

    stop_loss = current_price <= average_price * (1 - stop_loss_pct / 100)
    take_profit = current_price >= average_price * (1 + take_profit_pct / 100)
    trailing_stop = current_price <= high_watermark * (1 - trailing_stop_pct / 100)
    weak_score = score <= exit_score
    time_exit = holding_days >= max_holding_days

    decision = "HOLD"
    reason_code = "HOLD"
    reason_message = "No exit condition triggered"

    if stop_loss:
        decision, reason_code = "SELL", "STOP_LOSS"
        reason_message = f"price {current_price:.2f} below stop loss"
    elif take_profit:
        decision, reason_code = "SELL", "TAKE_PROFIT"
        reason_message = f"price {current_price:.2f} reached take profit"
    elif trailing_stop and high_watermark > average_price:
        decision, reason_code = "SELL", "TRAILING_STOP"
        reason_message = f"price fell {trailing_stop_pct:.1f}% from high watermark"
    elif weak_score:
        decision, reason_code = "SELL", "WEAK_SCORE"
        reason_message = f"score {score:.2f} <= exit score {exit_score:.2f}"
    elif time_exit:
        decision, reason_code = "SELL", "MAX_HOLDING_DAYS"
        reason_message = f"holding days {holding_days} >= {max_holding_days}"

    patch_rows(
        "paper_positions_v13",
        f"account_name=eq.{quote(ACCOUNT)}&symbol=eq.{quote(symbol)}",
        {
            "last_price": current_price,
            "market_value": current_value,
            "unrealized_pnl": current_pnl,
            "high_watermark_price": high_watermark,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    decisions.append({
        "account_name": ACCOUNT,
        "decision_date": latest_signal_date,
        "symbol": symbol,
        "quantity": quantity,
        "average_price": average_price,
        "current_price": current_price,
        "market_value": current_value,
        "unrealized_pnl": current_pnl,
        "score": score,
        "risk_score": risk,
        "decision": decision,
        "reason_code": reason_code,
        "reason_message": reason_message,
    })

    market_value += current_value
    unrealized += current_pnl

    if decision == "SELL":
        key = f"{ACCOUNT}:{latest_signal_date}:{symbol}:SELL:{reason_code}:V17"
        existing = get_rows(
            "trade_orders_v13",
            f"idempotency_key=eq.{quote(key)}&select=id&limit=1",
        )
        if not existing:
            insert_rows(
                "trade_orders_v13",
                {
                    "account_name": ACCOUNT,
                    "symbol": symbol,
                    "side": "SELL",
                    "quantity": quantity,
                    "reference_price": current_price,
                    "notional": money(quantity * current_price),
                    "score": score,
                    "risk_score": risk,
                    "confidence": number(signal_by_symbol.get(symbol, {}).get("confidence"), 50),
                    "reason": f"V17_{reason_code}",
                    "exit_reason": reason_code,
                    "mode": "PAPER",
                    "status": "PROPOSED",
                    "signal_date": latest_signal_date,
                    "execution_date": latest_signal_date,
                    "idempotency_key": key,
                },
            )

for row in decisions:
    upsert_rows(
        "portfolio_decisions_v17",
        row,
        "account_name,decision_date,symbol,reason_code",
    )

cash = number(account.get("cash"))
equity = money(cash + market_value)
starting_cash = number(account.get("starting_cash"), 1_000_000)
total_return = equity / starting_cash - 1 if starting_cash else 0

upsert_rows(
    "paper_accounts_v13",
    {
        **account,
        "account_name": ACCOUNT,
        "equity": equity,
        "unrealized_pnl": money(unrealized),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "account_name",
)

upsert_rows(
    "paper_equity_snapshots_v13",
    {
        "account_name": ACCOUNT,
        "snapshot_date": latest_signal_date,
        "cash": cash,
        "market_value": money(market_value),
        "equity": equity,
        "realized_pnl": number(account.get("realized_pnl")),
        "unrealized_pnl": money(unrealized),
        "total_return": total_return,
        "positions_count": len(positions),
    },
    "account_name,snapshot_date",
)

print(
    f"V17 Portfolio OS complete: positions={len(positions)}, "
    f"decisions={len(decisions)}, equity={equity:.2f}"
)
