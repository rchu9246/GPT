from __future__ import annotations

import json
import math
import os
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

TIMEOUT = 60

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip()
RUN_DATE = os.getenv("RUN_DATE", str(date.today())).strip()

INITIAL_CAPITAL = float(os.getenv("PAPER_INITIAL_CAPITAL", "1000000"))
SCORE_THRESHOLD = float(os.getenv("PAPER_SCORE_THRESHOLD", "65"))
POSITION_SIZE = float(os.getenv("PAPER_POSITION_SIZE", "0.10"))
MAX_NEW_ORDERS = int(os.getenv("PAPER_MAX_NEW_ORDERS", "5"))
MAX_OPEN_POSITIONS = int(os.getenv("PAPER_MAX_OPEN_POSITIONS", "10"))
SLIPPAGE_RATE = float(os.getenv("PAPER_SLIPPAGE_RATE", "0.001"))
COMMISSION_RATE = float(os.getenv("PAPER_COMMISSION_RATE", "0.001425"))
TAX_RATE = float(os.getenv("PAPER_TAX_RATE", "0.003"))

ARTIFACT_DIR = Path(os.getenv("PAPER_ARTIFACT_DIR", "artifacts/paper_trading"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "GPT-Quant-V9.2-Paper-Trading/1.0",
})


def api_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def check(response: requests.Response, context: str) -> None:
    if not response.ok:
        raise RuntimeError(f"{context}: HTTP {response.status_code}: {response.text[:1200]}")


def fetch_all(table: str, params: dict[str, str], page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        p = dict(params)
        p["limit"] = str(page_size)
        p["offset"] = str(offset)
        r = session.get(api_url(table), params=p, timeout=TIMEOUT)
        check(r, f"fetch {table}")
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        offset += page_size


def upsert(table: str, payload: dict[str, Any], on_conflict: str) -> dict[str, Any]:
    r = session.post(
        api_url(table),
        params={"on_conflict": on_conflict},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"upsert {table}")
    rows = r.json()
    return rows[0] if rows else payload


def insert(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = session.post(
        api_url(table),
        headers={"Prefer": "return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"insert {table}")
    rows = r.json()
    return rows[0] if rows else payload


def patch(table: str, eq_field: str, eq_value: Any, payload: dict[str, Any]) -> None:
    r = session.patch(
        api_url(table),
        params={eq_field: f"eq.{eq_value}"},
        headers={"Prefer": "return=minimal"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"patch {table}")


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
        values.append(max(high-low, abs(high-prev_close), abs(low-prev_close)))
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
    breakout = clamp(
        clamp(100 + (close / high20 - 1) * 100 * 10) * 0.65
        + clamp(100 + (close / high60 - 1) * 100 * 6) * 0.35
    )

    daily_returns = [
        (closes[i] / closes[i-1] - 1) * 100
        for i in range(1, len(closes)) if closes[i-1]
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
        + clamp(50 + roc20 * 2.5) * 0.08
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


def main() -> int:
    run = upsert("gptq_paper_runs", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "status": "RUNNING",
        "starting_cash": INITIAL_CAPITAL,
    }, "run_date,strategy_version")
    run_id = run.get("id")

    stocks = fetch_all("stocks", {
        "select": "id,symbol,name",
        "is_active": "eq.true",
        "order": "symbol.asc",
    })
    prices = fetch_all("daily_prices", {
        "select": "stock_id,trade_date,open,high,low,close,volume",
        "order": "stock_id.asc,trade_date.asc",
    })

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in prices:
        grouped[int(row["stock_id"])].append(row)

    existing_positions = fetch_all("gptq_paper_positions", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
    })
    position_by_stock = {int(p["stock_id"]): p for p in existing_positions}

    signals = []
    for stock in stocks:
        sid = int(stock["id"])
        rows = grouped.get(sid, [])
        if len(rows) < 122:
            continue
        latest = rows[-1]
        if latest["trade_date"] > RUN_DATE:
            continue
        score, label = historical_score(rows)
        if score < SCORE_THRESHOLD:
            continue
        signals.append({
            "stock_id": sid,
            "symbol": stock.get("symbol"),
            "score": score,
            "label": label,
            "reference_price": fnum(latest["close"]),
        })

    signals.sort(key=lambda x: (-x["score"], x["symbol"] or ""))

    cash = INITIAL_CAPITAL
    for p in existing_positions:
        cash -= fnum(p["average_price"]) * int(p["shares"])

    new_capacity = max(0, MAX_OPEN_POSITIONS - len(existing_positions))
    selected = [
        s for s in signals
        if s["stock_id"] not in position_by_stock
    ][:min(MAX_NEW_ORDERS, new_capacity)]

    orders = []
    for signal in selected:
        ref = signal["reference_price"]
        if ref <= 0:
            continue
        fill = ref * (1 + SLIPPAGE_RATE)
        target_notional = INITIAL_CAPITAL * POSITION_SIZE
        shares = max(int(target_notional / fill), 1)
        notional = fill * shares
        commission = notional * COMMISSION_RATE
        total_cost = notional + commission
        if total_cost > cash:
            continue

        cash -= total_cost

        order = insert("gptq_paper_orders", {
            "run_id": run_id,
            "run_date": RUN_DATE,
            "strategy_version": STRATEGY_VERSION,
            "stock_id": signal["stock_id"],
            "symbol": signal["symbol"],
            "side": "BUY",
            "signal_score": signal["score"],
            "signal_label": signal["label"],
            "reference_price": round(ref, 4),
            "simulated_fill_price": round(fill, 4),
            "shares": shares,
            "notional": round(notional, 2),
            "status": "FILLED",
            "reason": "SHADOW_ENTRY",
        })
        orders.append(order)

        upsert("gptq_paper_positions", {
            "strategy_version": STRATEGY_VERSION,
            "stock_id": signal["stock_id"],
            "symbol": signal["symbol"],
            "shares": shares,
            "average_price": round(fill, 4),
            "last_price": round(ref, 4),
            "market_value": round(ref * shares, 2),
            "unrealized_pnl": round((ref-fill) * shares, 2),
            "opened_at": RUN_DATE,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, "strategy_version,stock_id")

    positions = fetch_all("gptq_paper_positions", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
    })

    latest_price_by_stock = {}
    for sid, rows in grouped.items():
        if rows:
            latest_price_by_stock[sid] = fnum(rows[-1]["close"])

    market_value = 0.0
    unrealized = 0.0
    for p in positions:
        sid = int(p["stock_id"])
        last = latest_price_by_stock.get(sid, fnum(p.get("last_price")))
        shares = int(p["shares"])
        avg = fnum(p["average_price"])
        mv = last * shares
        upnl = (last - avg) * shares
        market_value += mv
        unrealized += upnl
        upsert("gptq_paper_positions", {
            **p,
            "last_price": round(last, 4),
            "market_value": round(mv, 2),
            "unrealized_pnl": round(upnl, 2),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, "strategy_version,stock_id")

    total_equity = cash + market_value

    upsert("gptq_paper_equity_snapshots", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "total_equity": round(total_equity, 2),
        "realized_pnl": 0,
        "unrealized_pnl": round(unrealized, 2),
        "open_positions": len(positions),
    }, "run_date,strategy_version")

    if run_id is not None:
        patch("gptq_paper_runs", "id", run_id, {
            "status": "COMPLETED",
            "ending_cash": round(cash, 2),
            "ending_equity": round(total_equity, 2),
            "realized_pnl": 0,
            "unrealized_pnl": round(unrealized, 2),
            "orders_created": len(orders),
            "positions_open": len(positions),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    report = {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "signals_found": len(signals),
        "orders_created": len(orders),
        "positions_open": len(positions),
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "total_equity": round(total_equity, 2),
        "unrealized_pnl": round(unrealized, 2),
        "mode": "SHADOW_ONLY_NO_BROKER",
    }
    (ARTIFACT_DIR/"paper_trading_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("# GPT Quant Paper Trading / Shadow Production\n\n")
            for k,v in report.items():
                f.write(f"- **{k}**: `{v}`\n")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
