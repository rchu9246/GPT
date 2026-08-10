from __future__ import annotations

import csv
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import requests

TIMEOUT = 60
STRATEGY_VERSION = os.getenv("BACKTEST_STRATEGY", "V3.1-MULTI").strip()
SCORE_THRESHOLD = float(os.getenv("BACKTEST_SCORE_THRESHOLD", "65"))
TAKE_PROFIT = float(os.getenv("BACKTEST_TAKE_PROFIT", "0.10"))
STOP_LOSS = float(os.getenv("BACKTEST_STOP_LOSS", "0.05"))
MAX_HOLDING_DAYS = int(os.getenv("BACKTEST_MAX_HOLDING_DAYS", "10"))
INITIAL_CAPITAL = float(os.getenv("BACKTEST_INITIAL_CAPITAL", "1000000"))
POSITION_SIZE = float(os.getenv("BACKTEST_POSITION_SIZE", "0.10"))
COMMISSION_RATE = float(os.getenv("BACKTEST_COMMISSION_RATE", "0.001425"))
TAX_RATE = float(os.getenv("BACKTEST_TAX_RATE", "0.003"))
SLIPPAGE_RATE = float(os.getenv("BACKTEST_SLIPPAGE_RATE", "0.001"))
START_DATE = os.getenv("BACKTEST_START_DATE", "").strip()
END_DATE = os.getenv("BACKTEST_END_DATE", "").strip()

GPTQ_RAW_METRICS_OUTPUT = os.getenv("GPTQ_RAW_METRICS_OUTPUT", "").strip()
GPTQ_RAW_TRADES_OUTPUT = os.getenv("GPTQ_RAW_TRADES_OUTPUT", "").strip()
GPTQ_RAW_EQUITY_OUTPUT = os.getenv("GPTQ_RAW_EQUITY_OUTPUT", "").strip()
GPTQ_METRICS_OUTPUT = os.getenv("GPTQ_METRICS_OUTPUT", "").strip()
GPTQ_TRADES_OUTPUT = os.getenv("GPTQ_TRADES_OUTPUT", "").strip()
GPTQ_EQUITY_OUTPUT = os.getenv("GPTQ_EQUITY_OUTPUT", "").strip()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


SUPABASE_URL = required_env("SUPABASE_URL").rstrip("/")
SERVICE_KEY = required_env("SUPABASE_SERVICE_ROLE_KEY")

session = requests.Session()
session.headers.update(
    {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "GPT-Quant-V4-Backtest/1.0",
    }
)


def api_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def check(response: requests.Response, context: str) -> None:
    if response.ok:
        return
    raise RuntimeError(
        f"{context}: HTTP {response.status_code}: {response.text[:1200]}"
    )


def fetch_all(table: str, params: dict[str, str], page_size: int = 1000):
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        paged = dict(params)
        paged["limit"] = str(page_size)
        paged["offset"] = str(offset)
        response = session.get(api_url(table), params=paged, timeout=TIMEOUT)
        check(response, f"fetch {table}")
        batch = response.json()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def insert_row(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = session.post(
        api_url(table),
        headers={"Prefer": "return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(response, f"insert {table}")
    rows = response.json()
    if not rows:
        raise RuntimeError(f"insert {table} returned no row")
    return rows[0]


def insert_many(table: str, rows: list[dict[str, Any]], chunk_size: int = 300):
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        response = session.post(
            api_url(table),
            headers={"Prefer": "return=minimal"},
            json=chunk,
            timeout=TIMEOUT,
        )
        check(response, f"insert {table}")
        print(f"{table}: {min(start + len(chunk), len(rows))}/{len(rows)}")


def update_run(run_id: str, payload: dict[str, Any]):
    response = session.patch(
        api_url("backtest_runs"),
        params={"id": f"eq.{run_id}"},
        headers={"Prefer": "return=minimal"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(response, "update backtest run")


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def sma(values: list[float], period: int) -> float | None:
    return sum(values[-period:]) / period if len(values) >= period else None


def ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1 - alpha) * current
    return current


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = sum(max(x, 0) for x in recent) / period
    losses = sum(max(-x, 0) for x in recent) / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)


def atr(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) <= period:
        return 0.0
    values = []
    for i in range(1, len(rows)):
        high = fnum(rows[i]["high"])
        low = fnum(rows[i]["low"])
        prev_close = fnum(rows[i - 1]["close"])
        values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(values[-period:]) / period


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def historical_score(window: list[dict[str, Any]]) -> tuple[float, str]:
    closes = [fnum(row["close"]) for row in window]
    volumes = [fnum(row["volume"]) for row in window]
    close = closes[-1]
    ema20 = ema(closes[-120:], 20) or 0
    ema60 = ema(closes[-160:], 60) or 0
    ema120 = ema(closes[-220:], 120) or 0

    trend = 0.0
    trend += 30 if close > ema20 > 0 else 0
    trend += 35 if ema20 > ema60 > 0 else 0
    trend += 35 if ema60 > ema120 > 0 else 0

    rsi14 = rsi(closes)
    ema12 = ema(closes[-80:], 12) or 0
    ema26 = ema(closes[-100:], 26) or 0
    macd = ema12 - ema26
    roc20 = (close / closes[-21] - 1) * 100 if len(closes) > 20 else 0
    momentum = clamp(
        (100 - abs(rsi14 - 60) * 3) * 0.45
        + clamp(50 + macd * 20) * 0.25
        + clamp(50 + roc20 * 2.5) * 0.30
    )

    vol20 = sma(volumes, 20) or volumes[-1] or 1
    volume_ratio = volumes[-1] / vol20
    volume_score = clamp(45 + (volume_ratio - 1) * 45)

    high20 = max(closes[-20:])
    high60 = max(closes[-60:])
    distance20 = (close / high20 - 1) * 100
    distance60 = (close / high60 - 1) * 100
    breakout = clamp(
        clamp(100 + distance20 * 10) * 0.65
        + clamp(100 + distance60 * 6) * 0.35
    )

    relative = clamp(50 + roc20 * 2.5)
    daily_returns = [
        (closes[i] / closes[i - 1] - 1) * 100
        for i in range(1, len(closes))
        if closes[i - 1]
    ]
    volatility = statistics.pstdev(daily_returns[-20:]) if len(daily_returns) > 1 else 0
    atr_pct = atr(window) / close * 100 if close else 0
    risk = clamp(100 - volatility * 11 - max(atr_pct - 2, 0) * 8)

    total = (
        trend * 0.24
        + momentum * 0.20
        + volume_score * 0.14
        + 50 * 0.08
        + breakout * 0.14
        + relative * 0.08
        + 60 * 0.05
        + risk * 0.07
    )

    signal = (
        "S級強多" if total >= 85 else
        "A級多頭" if total >= 75 else
        "B級觀察" if total >= 65 else
        "C級中性" if total >= 50 else
        "D級避開"
    )
    return round(total, 2), signal


def calculate_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    maximum = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            maximum = max(maximum, (peak - value) / peak)
    return maximum



def _write_json(path_value: str, payload: dict[str, Any]) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_trades_csv(path_value: str, trades: list[dict[str, Any]]) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["timestamp", "side", "entry_price", "exit_price", "pnl"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for trade in trades:
            writer.writerow({
                "timestamp": trade.get("exit_date") or trade.get("entry_date") or trade.get("signal_date"),
                "side": "LONG",
                "entry_price": trade.get("entry_price"),
                "exit_price": trade.get("exit_price"),
                "pnl": trade.get("pnl"),
            })


def _write_equity_csv(path_value: str, equity: list[float]) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "equity"])
        writer.writeheader()
        for index, value in enumerate(equity):
            writer.writerow({
                "timestamp": f"trade_{index}",
                "equity": round(value, 2),
            })


def export_production_evidence(
    *,
    trades: list[dict[str, Any]],
    equity: list[float],
    metrics: dict[str, Any],
) -> None:
    metrics_paths = [GPTQ_RAW_METRICS_OUTPUT, GPTQ_METRICS_OUTPUT]
    trades_paths = [GPTQ_RAW_TRADES_OUTPUT, GPTQ_TRADES_OUTPUT]
    equity_paths = [GPTQ_RAW_EQUITY_OUTPUT, GPTQ_EQUITY_OUTPUT]

    for path in dict.fromkeys(path for path in metrics_paths if path):
        _write_json(path, metrics)
    for path in dict.fromkeys(path for path in trades_paths if path):
        _write_trades_csv(path, trades)
    for path in dict.fromkeys(path for path in equity_paths if path):
        _write_equity_csv(path, equity)

    if any(metrics_paths + trades_paths + equity_paths):
        print(json.dumps({
            "production_evidence_export": True,
            "strategy_version": STRATEGY_VERSION,
            "metrics_output": next((p for p in metrics_paths if p), None),
            "trades_output": next((p for p in trades_paths if p), None),
            "equity_output": next((p for p in equity_paths if p), None),
        }, ensure_ascii=False))


def main():
    stocks = fetch_all(
        "stocks",
        {"select": "id,symbol,name", "is_active": "eq.true", "order": "symbol.asc"},
    )
    if not stocks:
        raise RuntimeError("No active stocks")

    prices = fetch_all(
        "daily_prices",
        {
            "select": "stock_id,trade_date,open,high,low,close,volume",
            "order": "stock_id.asc,trade_date.asc",
        },
    )

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in prices:
        if START_DATE and row["trade_date"] < START_DATE:
            continue
        if END_DATE and row["trade_date"] > END_DATE:
            continue
        grouped[int(row["stock_id"])].append(row)

    all_dates = sorted({row["trade_date"] for row in prices})
    resolved_start = START_DATE or (all_dates[0] if all_dates else str(date.today()))
    resolved_end = END_DATE or (all_dates[-1] if all_dates else str(date.today()))

    run = insert_row(
        "backtest_runs",
        {
            "strategy_version": STRATEGY_VERSION,
            "start_date": resolved_start,
            "end_date": resolved_end,
            "initial_capital": INITIAL_CAPITAL,
            "score_threshold": SCORE_THRESHOLD,
            "take_profit": TAKE_PROFIT,
            "stop_loss": STOP_LOSS,
            "max_positions": 10,
            "position_size": POSITION_SIZE,
            "commission_rate": COMMISSION_RATE,
            "tax_rate": TAX_RATE,
            "slippage_rate": SLIPPAGE_RATE,
            "status": "RUNNING",
            "parameters": {
                "entry": "T+1 open",
                "max_holding_days": MAX_HOLDING_DAYS,
                "conservative_same_day_exit": True,
            },
        },
    )
    run_id = run["id"]
    trades = []

    try:
        for stock in stocks:
            stock_id = int(stock["id"])
            rows = grouped.get(stock_id, [])
            if len(rows) < 122:
                continue

            next_available_index = 120
            index = 120
            while index < len(rows) - 1:
                if index < next_available_index:
                    index += 1
                    continue

                score, signal = historical_score(rows[: index + 1])
                if score < SCORE_THRESHOLD:
                    index += 1
                    continue

                signal_date = rows[index]["trade_date"]
                entry_index = index + 1
                entry_price = fnum(rows[entry_index]["open"]) * (1 + SLIPPAGE_RATE)
                if entry_price <= 0:
                    index += 1
                    continue

                exit_index = min(entry_index + MAX_HOLDING_DAYS - 1, len(rows) - 1)
                exit_price = fnum(rows[exit_index]["close"]) * (1 - SLIPPAGE_RATE)
                reason = "TIME"
                mfe = 0.0
                mae = 0.0

                for cursor in range(entry_index, exit_index + 1):
                    high = fnum(rows[cursor]["high"])
                    low = fnum(rows[cursor]["low"])
                    mfe = max(mfe, high / entry_price - 1)
                    mae = min(mae, low / entry_price - 1)

                    stop_price = entry_price * (1 - STOP_LOSS)
                    target_price = entry_price * (1 + TAKE_PROFIT)

                    # Conservative assumption: stop executes first if both are touched.
                    if low <= stop_price:
                        exit_index = cursor
                        exit_price = stop_price * (1 - SLIPPAGE_RATE)
                        reason = "STOP"
                        break
                    if high >= target_price:
                        exit_index = cursor
                        exit_price = target_price * (1 - SLIPPAGE_RATE)
                        reason = "TARGET"
                        break

                gross_return = exit_price / entry_price - 1
                costs = COMMISSION_RATE * 2 + TAX_RATE + SLIPPAGE_RATE * 2
                net_return = gross_return - costs
                allocated = INITIAL_CAPITAL * POSITION_SIZE
                shares = max(int(allocated / entry_price), 1)
                pnl = shares * entry_price * net_return

                trades.append(
                    {
                        "run_id": run_id,
                        "stock_id": stock_id,
                        "signal_date": signal_date,
                        "entry_date": rows[entry_index]["trade_date"],
                        "exit_date": rows[exit_index]["trade_date"],
                        "entry_price": round(entry_price, 4),
                        "exit_price": round(exit_price, 4),
                        "shares": shares,
                        "gross_return": round(gross_return, 8),
                        "net_return": round(net_return, 8),
                        "pnl": round(pnl, 2),
                        "exit_reason": reason,
                        "max_favorable_excursion": round(mfe, 8),
                        "max_adverse_excursion": round(mae, 8),
                        "score": score,
                        "signal": signal,
                        "holding_days": exit_index - entry_index + 1,
                    }
                )
                next_available_index = exit_index + 1
                index = next_available_index

        if trades:
            insert_many("backtest_trades", trades)

        returns = [fnum(trade["net_return"]) for trade in trades]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]

        equity = [INITIAL_CAPITAL]
        for value in returns:
            equity.append(equity[-1] * (1 + value * POSITION_SIZE))

        total_return = equity[-1] / INITIAL_CAPITAL - 1
        day_span = max(
            (
                date.fromisoformat(resolved_end) - date.fromisoformat(resolved_start)
            ).days,
            1,
        )
        annual_return = (1 + total_return) ** (365 / day_span) - 1 if total_return > -1 else -1
        win_rate = len(wins) / len(returns) if returns else 0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss else (999 if wins else 0)
        std = statistics.pstdev(returns) if len(returns) > 1 else 0
        sharpe = statistics.mean(returns) / std * math.sqrt(252 / max(MAX_HOLDING_DAYS, 1)) if std else 0
        downside = [min(value, 0) for value in returns]
        downside_std = statistics.pstdev(downside) if len(downside) > 1 else 0
        sortino = statistics.mean(returns) / downside_std * math.sqrt(252 / max(MAX_HOLDING_DAYS, 1)) if downside_std else 0

        max_drawdown = calculate_drawdown(equity)
        average_return = statistics.mean(returns) if returns else 0
        average_holding_days = (
            statistics.mean([trade["holding_days"] for trade in trades])
            if trades else 0
        )

        # Rich evidence payload: used only for files / comparison pipeline.
        metrics_payload = {
            "strategy_version": STRATEGY_VERSION,
            "total_return": round(total_return, 8),
            "annual_return": round(annual_return, 8),
            "win_rate": round(win_rate, 8),
            "profit_factor": round(profit_factor, 8),
            "max_drawdown": round(max_drawdown, 8),
            "sharpe": round(sharpe, 8),
            "sharpe_ratio": round(sharpe, 8),
            "sortino": round(sortino, 8),
            "sortino_ratio": round(sortino, 8),
            "total_trades": len(trades),
            "average_trade": round(average_return, 8),
            "average_return": round(average_return, 8),
            "average_holding_days": round(average_holding_days, 2),
            "best_trade": max(returns) if returns else 0,
            "worst_trade": min(returns) if returns else 0,
            "final_capital": round(equity[-1], 2),
        }

        # Supabase compatibility payload:
        # ONLY fields already used by the original backtest_runs schema.
        # Do not send evidence-only aliases such as average_trade, sharpe,
        # sortino, or strategy_version as update columns.
        db_payload = {
            "status": "COMPLETED",
            "total_return": round(total_return, 8),
            "annual_return": round(annual_return, 8),
            "win_rate": round(win_rate, 8),
            "profit_factor": round(profit_factor, 8),
            "max_drawdown": round(max_drawdown, 8),
            "sharpe_ratio": round(sharpe, 8),
            "sortino_ratio": round(sortino, 8),
            "total_trades": len(trades),
            "average_return": round(average_return, 8),
            "average_holding_days": round(average_holding_days, 2),
            "best_trade": max(returns) if returns else 0,
            "worst_trade": min(returns) if returns else 0,
            "final_capital": round(equity[-1], 2),
            "equity_curve": [
                {"trade": index, "equity": round(value, 2)}
                for index, value in enumerate(equity)
            ],
            "completed_at": "now()",
        }

        update_run(run_id, db_payload)

        # Export after DB update succeeds.
        export_production_evidence(
            trades=trades,
            equity=equity,
            metrics=metrics_payload,
        )

        print(json.dumps({
            "run_id": run_id,
            "trades": len(trades),
            "total_return": total_return,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
        }, ensure_ascii=False, indent=2))
    except Exception:
        update_run(run_id, {"status": "FAILED", "completed_at": "now()"})
        raise


if __name__ == "__main__":
    main()