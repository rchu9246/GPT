"""GPT Quant V13.1 operational PAPER trading engine.

What it does:
1. Loads the latest signal date and actual latest daily close from Supabase.
2. Marks positions to market.
3. Generates and optionally fills SELL orders:
   stop loss, take profit, weak score, or maximum holding days.
4. Generates and optionally fills BUY orders under cash/position/risk limits.
5. Updates cash, positions, fills, realized/unrealized P&L and daily equity.
6. Uses idempotency keys so the same trading day can be run safely again.

Security:
- PAPER mode only. LIVE_LOCKED is never executed.
- SUPABASE_SERVICE_ROLE_KEY stays in GitHub Secrets or a secure server.
"""
from __future__ import annotations

import math
import os
import sys
import traceback
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")

if not SUPABASE_URL or not SERVICE_KEY:
    raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

BASE_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}
RETURN_HEADERS = {**BASE_HEADERS, "Prefer": "return=representation"}
UPSERT_HEADERS = {
    **BASE_HEADERS,
    "Prefer": "resolution=merge-duplicates,return=representation",
}


def api_url(table: str, query: str = "") -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}" + (f"?{query}" if query else "")


def get_rows(table: str, query: str = "") -> list[dict[str, Any]]:
    response = requests.get(api_url(table, query), headers=BASE_HEADERS, timeout=45)
    response.raise_for_status()
    return response.json()


def insert_rows(table: str, payload: Any) -> list[dict[str, Any]]:
    response = requests.post(
        api_url(table), headers=RETURN_HEADERS, json=payload, timeout=45
    )
    response.raise_for_status()
    return response.json()


def upsert_rows(
    table: str,
    payload: Any,
    on_conflict: str,
) -> list[dict[str, Any]]:
    query = f"on_conflict={quote(on_conflict)}"
    response = requests.post(
        api_url(table, query), headers=UPSERT_HEADERS, json=payload, timeout=45
    )
    response.raise_for_status()
    return response.json()


def patch_rows(table: str, query: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = requests.patch(
        api_url(table, query), headers=RETURN_HEADERS, json=payload, timeout=45
    )
    response.raise_for_status()
    return response.json()


def delete_rows(table: str, query: str) -> None:
    response = requests.delete(api_url(table, query), headers=BASE_HEADERS, timeout=45)
    response.raise_for_status()


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


def start_run() -> str:
    rows = insert_rows(
        "paper_engine_runs_v13",
        {
            "account_name": ACCOUNT,
            "run_date": date.today().isoformat(),
            "status": "RUNNING",
        },
    )
    return str(rows[0]["id"])


def finish_run(
    run_id: str,
    status: str,
    message: str,
    signals_date: str | None = None,
    buy_orders: int = 0,
    sell_orders: int = 0,
    fills: int = 0,
) -> None:
    patch_rows(
        "paper_engine_runs_v13",
        f"id=eq.{run_id}",
        {
            "status": status,
            "signals_date": signals_date,
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
            "fills": fills,
            "message": message[:1000],
            "finished_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def load_config() -> dict[str, Any] | None:
    rows = get_rows(
        "autotrader_configs_v13",
        f"account_name=eq.{quote(ACCOUNT)}&limit=1",
    )
    return rows[0] if rows else None


def load_or_create_account(config: dict[str, Any]) -> dict[str, Any]:
    rows = get_rows(
        "paper_accounts_v13",
        f"account_name=eq.{quote(ACCOUNT)}&limit=1",
    )
    if rows:
        return rows[0]
    starting_cash = number(config.get("starting_cash"), 1_000_000)
    created = upsert_rows(
        "paper_accounts_v13",
        {
            "account_name": ACCOUNT,
            "starting_cash": starting_cash,
            "cash": starting_cash,
            "equity": starting_cash,
        },
        "account_name",
    )
    return created[0]


def load_market_data() -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    signals = get_rows(
        "signals",
        "select=stock_id,trade_date,strategy_version,total_score,"
        "trend_score,momentum_score,volume_score,risk_score,confidence"
        "&order=trade_date.desc,total_score.desc&limit=500",
    )
    if not signals:
        raise RuntimeError("No signals available")

    latest_signal_date = str(signals[0]["trade_date"])
    latest_signals = [row for row in signals if str(row["trade_date"]) == latest_signal_date]

    stocks = get_rows("stocks", "select=id,symbol,name&limit=10000")
    stock_by_id = {str(row["id"]): row for row in stocks}
    stock_id_by_symbol = {
        str(row.get("symbol")): str(row["id"])
        for row in stocks
        if row.get("symbol")
    }

    relevant_ids = sorted(
        {str(row.get("stock_id")) for row in latest_signals if row.get("stock_id") is not None}
    )
    prices: list[dict[str, Any]] = []
    # PostgREST URL size remains manageable for the current small signal universe.
    if relevant_ids:
        encoded_ids = ",".join(relevant_ids)
        prices = get_rows(
            "daily_prices",
            "select=stock_id,trade_date,open,high,low,close,volume"
            f"&stock_id=in.({encoded_ids})"
            "&order=trade_date.desc&limit=5000",
        )

    latest_price_by_stock_id: dict[str, dict[str, Any]] = {}
    for row in prices:
        stock_id = str(row["stock_id"])
        if stock_id not in latest_price_by_stock_id:
            latest_price_by_stock_id[stock_id] = row

    signal_by_symbol: dict[str, dict[str, Any]] = {}
    for row in latest_signals:
        stock = stock_by_id.get(str(row.get("stock_id")))
        if not stock or not stock.get("symbol"):
            continue
        symbol = str(stock["symbol"])
        current = signal_by_symbol.get(symbol)
        if current is None or number(row.get("total_score")) > number(current.get("total_score")):
            signal_by_symbol[symbol] = {**row, "stock": stock}

    price_by_symbol: dict[str, dict[str, Any]] = {}
    for symbol, stock_id in stock_id_by_symbol.items():
        price = latest_price_by_stock_id.get(stock_id)
        if price:
            price_by_symbol[symbol] = price

    return latest_signal_date, latest_signals, signal_by_symbol, price_by_symbol


def load_positions() -> list[dict[str, Any]]:
    return get_rows(
        "paper_positions_v13",
        f"account_name=eq.{quote(ACCOUNT)}&order=symbol.asc",
    )


def order_exists(idempotency_key: str) -> bool:
    rows = get_rows(
        "trade_orders_v13",
        f"idempotency_key=eq.{quote(idempotency_key)}&select=id&limit=1",
    )
    return bool(rows)


def create_order(
    *,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    score: float,
    risk: float,
    confidence: float,
    signal_date: str,
    reason: str,
    exit_reason: str | None,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    key = f"{ACCOUNT}:{signal_date}:{symbol}:{side}:{reason}"
    if order_exists(key):
        return None

    require_approval = bool(config.get("require_approval"))
    auto_fill = bool(config.get("auto_fill"))
    status = "PROPOSED" if require_approval or not auto_fill else "APPROVED"
    payload = {
        "account_name": ACCOUNT,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "reference_price": money(price),
        "notional": money(quantity * price),
        "score": score,
        "risk_score": risk,
        "confidence": confidence,
        "reason": reason,
        "exit_reason": exit_reason,
        "mode": "PAPER",
        "status": status,
        "signal_date": signal_date,
        "execution_date": signal_date,
        "idempotency_key": key,
    }
    rows = insert_rows("trade_orders_v13", payload)
    return rows[0]


def fill_order(
    order: dict[str, Any],
    config: dict[str, Any],
    account: dict[str, Any],
    positions_by_symbol: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    if order["status"] != "APPROVED" or not bool(config.get("auto_fill")):
        return account, 0

    symbol = str(order["symbol"])
    side = str(order["side"])
    quantity = integer(order["quantity"])
    price = number(order["reference_price"])
    gross = money(quantity * price)
    commission = money(max(1.0, gross * number(config.get("commission_rate"), 0.001425)))
    tax = money(gross * number(config.get("sell_tax_rate"), 0.003)) if side == "SELL" else 0.0
    cash = number(account.get("cash"))
    position = positions_by_symbol.get(symbol)

    if side == "BUY":
        total_debit = money(gross + commission)
        if cash < total_debit:
            patch_rows(
                "trade_orders_v13",
                f"id=eq.{order['id']}",
                {"status": "FAILED", "error_message": "Insufficient paper cash"},
            )
            return account, 0

        old_quantity = integer(position.get("quantity")) if position else 0
        old_cost_basis = number(position.get("cost_basis")) if position else 0.0
        new_quantity = old_quantity + quantity
        new_cost_basis = money(old_cost_basis + gross + commission)
        average_price = new_cost_basis / new_quantity

        position_payload = {
            "account_name": ACCOUNT,
            "symbol": symbol,
            "stock_id": position.get("stock_id") if position else None,
            "name": position.get("name") if position else None,
            "quantity": new_quantity,
            "average_price": money(average_price),
            "last_price": price,
            "cost_basis": new_cost_basis,
            "market_value": money(new_quantity * price),
            "unrealized_pnl": money(new_quantity * price - new_cost_basis),
            "last_trade_date": order.get("execution_date"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_rows("paper_positions_v13", position_payload, "account_name,symbol")
        positions_by_symbol[symbol] = position_payload
        net_cash_flow = -total_debit
        realized_pnl = 0.0
        cash = money(cash - total_debit)

    else:
        if not position or integer(position.get("quantity")) < quantity:
            patch_rows(
                "trade_orders_v13",
                f"id=eq.{order['id']}",
                {"status": "FAILED", "error_message": "Insufficient paper position"},
            )
            return account, 0

        old_quantity = integer(position["quantity"])
        average_price = number(position["average_price"])
        proceeds = money(gross - commission - tax)
        realized_pnl = money((price - average_price) * quantity - commission - tax)
        remaining = old_quantity - quantity

        if remaining == 0:
            delete_rows(
                "paper_positions_v13",
                f"account_name=eq.{quote(ACCOUNT)}&symbol=eq.{quote(symbol)}",
            )
            positions_by_symbol.pop(symbol, None)
        else:
            remaining_cost = money(number(position.get("cost_basis")) * remaining / old_quantity)
            position_payload = {
                **position,
                "quantity": remaining,
                "cost_basis": remaining_cost,
                "market_value": money(remaining * price),
                "last_price": price,
                "unrealized_pnl": money(remaining * price - remaining_cost),
                "realized_pnl": money(number(position.get("realized_pnl")) + realized_pnl),
                "last_trade_date": order.get("execution_date"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            upsert_rows("paper_positions_v13", position_payload, "account_name,symbol")
            positions_by_symbol[symbol] = position_payload

        net_cash_flow = proceeds
        cash = money(cash + proceeds)

    insert_rows(
        "paper_fills_v13",
        {
            "order_id": order["id"],
            "account_name": ACCOUNT,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "fill_price": price,
            "gross_amount": gross,
            "commission": commission,
            "transaction_tax": tax,
            "net_cash_flow": net_cash_flow,
            "realized_pnl": realized_pnl,
            "trade_date": order.get("execution_date"),
        },
    )

    patch_rows(
        "trade_orders_v13",
        f"id=eq.{order['id']}",
        {
            "status": "FILLED",
            "fill_price": price,
            "commission": commission,
            "transaction_tax": tax,
            "realized_pnl": realized_pnl,
            "filled_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    account = {
        **account,
        "cash": cash,
        "realized_pnl": money(number(account.get("realized_pnl")) + realized_pnl),
        "total_fees": money(number(account.get("total_fees")) + commission),
        "total_tax": money(number(account.get("total_tax")) + tax),
    }
    return account, 1


def mark_to_market(
    positions_by_symbol: dict[str, dict[str, Any]],
    price_by_symbol: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    market_value = 0.0
    unrealized = 0.0
    today = date.today()

    for symbol, position in list(positions_by_symbol.items()):
        price_row = price_by_symbol.get(symbol)
        if not price_row:
            continue
        price = number(price_row.get("close"))
        quantity = integer(position.get("quantity"))
        value = money(quantity * price)
        pnl = money(value - number(position.get("cost_basis")))
        opened_at = str(position.get("opened_at") or today.isoformat())[:10]
        try:
            holding_days = max(0, (today - date.fromisoformat(opened_at)).days)
        except ValueError:
            holding_days = integer(position.get("holding_days"))

        updated = {
            **position,
            "last_price": price,
            "market_value": value,
            "unrealized_pnl": pnl,
            "holding_days": holding_days,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_rows("paper_positions_v13", updated, "account_name,symbol")
        positions_by_symbol[symbol] = updated
        market_value += value
        unrealized += pnl

    return money(market_value), money(unrealized)


def main() -> None:
    run_id = start_run()
    signal_date: str | None = None
    buy_orders = 0
    sell_orders = 0
    fills = 0

    try:
        config = load_config()
        if not config:
            finish_run(run_id, "SKIPPED", "No autotrader config")
            return

        if (
            not bool(config.get("enabled"))
            or bool(config.get("kill_switch"))
            or str(config.get("mode")) != "PAPER"
        ):
            finish_run(run_id, "SKIPPED", "Trader disabled, killed, or not PAPER")
            return

        account = load_or_create_account(config)
        signal_date, _, signal_by_symbol, price_by_symbol = load_market_data()
        positions = load_positions()
        positions_by_symbol = {str(row["symbol"]): row for row in positions}

        # Mark existing positions before generating exits.
        market_value, unrealized = mark_to_market(positions_by_symbol, price_by_symbol)

        # SELL rules first, so exits release cash and position slots.
        for symbol, position in list(positions_by_symbol.items()):
            price_row = price_by_symbol.get(symbol)
            if not price_row:
                continue

            price = number(price_row.get("close"))
            average_price = number(position.get("average_price"))
            quantity = integer(position.get("quantity"))
            signal = signal_by_symbol.get(symbol, {})
            score = number(signal.get("total_score"))
            risk = number(signal.get("risk_score"), 50)
            confidence = number(signal.get("confidence"), 50)
            holding_days = integer(position.get("holding_days"))

            stop_loss = price <= average_price * (
                1 - number(config.get("stop_loss_pct"), 8) / 100
            )
            take_profit = price >= average_price * (
                1 + number(config.get("take_profit_pct"), 15) / 100
            )
            weak_score = score <= number(config.get("exit_score"), 25)
            time_exit = holding_days >= integer(config.get("max_holding_days"), 20)

            exit_reason: str | None = None
            if stop_loss:
                exit_reason = "STOP_LOSS"
            elif take_profit:
                exit_reason = "TAKE_PROFIT"
            elif weak_score:
                exit_reason = "WEAK_SCORE"
            elif time_exit:
                exit_reason = "MAX_HOLDING_DAYS"

            if not exit_reason:
                continue

            order = create_order(
                symbol=symbol,
                side="SELL",
                quantity=quantity,
                price=price,
                score=score,
                risk=risk,
                confidence=confidence,
                signal_date=signal_date,
                reason=f"EXIT_{exit_reason}",
                exit_reason=exit_reason,
                config=config,
            )
            if order:
                sell_orders += 1
                account, filled = fill_order(
                    order, config, account, positions_by_symbol
                )
                fills += filled

        # Refresh marked values after exits.
        market_value, unrealized = mark_to_market(positions_by_symbol, price_by_symbol)
        account_cash = number(account.get("cash"))
        equity_before_buys = account_cash + market_value
        reserve_cash = equity_before_buys * number(config.get("reserve_cash_pct"), 30) / 100
        investable_cash = max(0.0, account_cash - reserve_cash)
        open_slots = max(
            0,
            integer(config.get("max_positions"), 5) - len(positions_by_symbol),
        )
        daily_limit = integer(config.get("max_daily_orders"), 5)
        max_buys = min(open_slots, daily_limit)
        max_notional = number(account.get("starting_cash"), 1_000_000) * number(
            config.get("max_position_pct"), 15
        ) / 100
        lot_size = max(1, integer(config.get("lot_size"), 1))

        candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for symbol, signal in signal_by_symbol.items():
            if symbol in positions_by_symbol:
                continue
            price = price_by_symbol.get(symbol)
            if not price:
                continue
            score = number(signal.get("total_score"))
            risk = number(signal.get("risk_score"), 50)
            if score < number(config.get("min_score"), 40):
                continue
            if risk > number(config.get("max_risk_score"), 60):
                continue
            candidates.append((symbol, signal, price))

        candidates.sort(key=lambda item: number(item[1].get("total_score")), reverse=True)

        for index, (symbol, signal, price_row) in enumerate(candidates[:max_buys]):
            price = number(price_row.get("close"))
            remaining_count = max(1, max_buys - index)
            budget = min(max_notional, investable_cash / remaining_count)
            raw_quantity = math.floor(budget / price)
            quantity = (raw_quantity // lot_size) * lot_size
            if quantity <= 0:
                continue

            estimated_gross = quantity * price
            estimated_commission = max(
                1.0,
                estimated_gross * number(config.get("commission_rate"), 0.001425),
            )
            if estimated_gross + estimated_commission > investable_cash:
                continue

            order = create_order(
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                price=price,
                score=number(signal.get("total_score")),
                risk=number(signal.get("risk_score"), 50),
                confidence=number(signal.get("confidence"), 50),
                signal_date=signal_date,
                reason="ENTRY_SIGNAL",
                exit_reason=None,
                config=config,
            )
            if order:
                buy_orders += 1
                account, filled = fill_order(
                    order, config, account, positions_by_symbol
                )
                fills += filled
                if filled:
                    investable_cash = max(
                        0.0,
                        investable_cash
                        - number(order.get("notional"))
                        - max(
                            1.0,
                            number(order.get("notional"))
                            * number(config.get("commission_rate"), 0.001425),
                        ),
                    )

        market_value, unrealized = mark_to_market(positions_by_symbol, price_by_symbol)
        equity = money(number(account.get("cash")) + market_value)
        starting_cash = number(account.get("starting_cash"), 1_000_000)
        total_return = equity / starting_cash - 1 if starting_cash else 0.0

        account_payload = {
            **account,
            "account_name": ACCOUNT,
            "equity": equity,
            "unrealized_pnl": unrealized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_rows("paper_accounts_v13", account_payload, "account_name")

        upsert_rows(
            "paper_equity_snapshots_v13",
            {
                "account_name": ACCOUNT,
                "snapshot_date": signal_date,
                "cash": number(account_payload.get("cash")),
                "market_value": market_value,
                "equity": equity,
                "realized_pnl": number(account_payload.get("realized_pnl")),
                "unrealized_pnl": unrealized,
                "total_return": total_return,
                "positions_count": len(positions_by_symbol),
            },
            "account_name,snapshot_date",
        )

        message = (
            f"Operational paper cycle complete: buys={buy_orders}, "
            f"sells={sell_orders}, fills={fills}, equity={equity:.2f}"
        )
        patch_rows(
            "autotrader_configs_v13",
            f"account_name=eq.{quote(ACCOUNT)}",
            {
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_run_status": "SUCCESS",
                "last_run_message": message,
            },
        )
        finish_run(
            run_id,
            "SUCCESS",
            message,
            signals_date=signal_date,
            buy_orders=buy_orders,
            sell_orders=sell_orders,
            fills=fills,
        )
        print(message)

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        try:
            patch_rows(
                "autotrader_configs_v13",
                f"account_name=eq.{quote(ACCOUNT)}",
                {
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                    "last_run_status": "FAILED",
                    "last_run_message": message,
                },
            )
            finish_run(
                run_id,
                "FAILED",
                message,
                signals_date=signal_date,
                buy_orders=buy_orders,
                sell_orders=sell_orders,
                fills=fills,
            )
        except Exception:
            pass
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
