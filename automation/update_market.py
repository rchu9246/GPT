from __future__ import annotations

import math
import os
import statistics
import sys
import time
from datetime import date, timedelta
from typing import Any

import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
TIMEOUT = 45


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


FINMIND_TOKEN = required_env("FINMIND_TOKEN")
SUPABASE_URL = required_env("SUPABASE_URL").rstrip("/")
SERVICE_KEY = required_env("SUPABASE_SERVICE_ROLE_KEY")
SYMBOLS = [
    item.strip()
    for item in os.getenv("STOCK_SYMBOLS", "2330,2454,2382").split(",")
    if item.strip()
]
LOOKBACK_DAYS = max(130, int(os.getenv("LOOKBACK_DAYS", "220")))

session = requests.Session()
session.headers.update(
    {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "GPT-Quant-Automation/1.0",
    }
)


def api_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def check_response(response: requests.Response, context: str) -> None:
    if response.ok:
        return
    body = response.text[:1000]
    raise RuntimeError(f"{context} failed: HTTP {response.status_code}: {body}")


def supabase_upsert(
    table: str,
    rows: list[dict[str, Any]],
    on_conflict: str,
    chunk_size: int = 300,
) -> None:
    if not rows:
        return

    headers = {
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        response = session.post(
            api_url(table),
            params={"on_conflict": on_conflict},
            headers=headers,
            json=chunk,
            timeout=TIMEOUT,
        )
        check_response(response, f"upsert {table}")
        print(f"  {table}: upserted {min(start + len(chunk), len(rows))}/{len(rows)}")


def get_stock(symbol: str) -> dict[str, Any] | None:
    response = session.get(
        api_url("stocks"),
        params={
            "select": "id,symbol,name,market,industry",
            "symbol": f"eq.{symbol}",
            "limit": "1",
        },
        timeout=TIMEOUT,
    )
    check_response(response, f"read stock {symbol}")
    rows = response.json()
    return rows[0] if rows else None


def fetch_finmind(dataset: str, symbol: str, start_date: str) -> list[dict[str, Any]]:
    params = {
        "dataset": dataset,
        "data_id": symbol,
        "start_date": start_date,
        "token": FINMIND_TOKEN,
    }
    response = requests.get(FINMIND_URL, params=params, timeout=TIMEOUT)
    check_response(response, f"FinMind {dataset} {symbol}")
    payload = response.json()

    status = payload.get("status")
    if status not in (None, 200):
        raise RuntimeError(
            f"FinMind returned status={status}: {payload.get('msg', payload)}"
        )

    data = payload.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected FinMind response for {symbol}")
    return data


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def inum(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def pct_change(values: list[float], periods: int) -> float | None:
    if len(values) <= periods or values[-periods - 1] == 0:
        return None
    return (values[-1] / values[-periods - 1] - 1.0) * 100.0


def ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = sum(max(change, 0.0) for change in recent) / period
    losses = sum(max(-change, 0.0) for change in recent) / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def atr(rows: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(rows) <= period:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(rows)):
        current = rows[index]
        previous_close = fnum(rows[index - 1]["close"])
        high = fnum(current["high"])
        low = fnum(current["low"])
        true_ranges.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )
    return sum(true_ranges[-period:]) / period


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def calculate_latest_feature(price_rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [fnum(row["close"]) for row in price_rows]
    volumes = [fnum(row["volume"]) for row in price_rows]
    current = price_rows[-1]
    current_close = closes[-1]

    ma5 = sma(closes, 5)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    ma120 = sma(closes, 120)

    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    macd_values = [a - b for a, b in zip(ema12, ema26)]
    signal_values = ema_series(macd_values, 9)
    macd = macd_values[-1] if macd_values else None
    macd_signal = signal_values[-1] if signal_values else None
    macd_hist = (
        macd - macd_signal
        if macd is not None and macd_signal is not None
        else None
    )

    high20 = max(closes[-20:]) if len(closes) >= 20 else max(closes)
    high60 = max(closes[-60:]) if len(closes) >= 60 else max(closes)
    vol5 = sma(volumes, 5)
    vol20 = sma(volumes, 20)

    daily_returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] != 0:
            daily_returns.append((closes[i] / closes[i - 1] - 1.0) * 100)

    volatility20 = (
        statistics.pstdev(daily_returns[-20:])
        if len(daily_returns) >= 2
        else 0.0
    )

    ma20_prev = (
        sum(closes[-25:-5]) / 20 if len(closes) >= 25 else ma20
    )
    ma60_prev = (
        sum(closes[-65:-5]) / 60 if len(closes) >= 65 else ma60
    )

    return {
        "trade_date": current["trade_date"],
        "close": round(current_close, 4),
        "return_1d": pct_change(closes, 1),
        "return_5d": pct_change(closes, 5),
        "return_20d": pct_change(closes, 20),
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "ma120": ma120,
        "ma20_slope": (
            ((ma20 / ma20_prev) - 1) * 100
            if ma20 and ma20_prev
            else None
        ),
        "ma60_slope": (
            ((ma60 / ma60_prev) - 1) * 100
            if ma60 and ma60_prev
            else None
        ),
        "rsi14": rsi(closes, 14),
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "atr14": atr(price_rows, 14),
        "volume_ratio_5d": (
            volumes[-1] / vol5 if vol5 and vol5 > 0 else None
        ),
        "volume_ratio_20d": (
            volumes[-1] / vol20 if vol20 and vol20 > 0 else None
        ),
        "volatility_20d": volatility20,
        "high_20d": high20,
        "high_60d": high60,
        "distance_high_20d": (
            (current_close / high20 - 1) * 100 if high20 else None
        ),
        "distance_high_60d": (
            (current_close / high60 - 1) * 100 if high60 else None
        ),
        "foreign_net_5d": 0,
        "foreign_net_20d": 0,
        "trust_net_5d": 0,
        "trust_net_20d": 0,
    }


def score_feature(feature: dict[str, Any]) -> dict[str, Any]:
    close = fnum(feature["close"])
    ma5 = fnum(feature["ma5"])
    ma20 = fnum(feature["ma20"])
    ma60 = fnum(feature["ma60"])
    ma120 = fnum(feature["ma120"])
    rsi14 = fnum(feature["rsi14"], 50)
    macd_hist = fnum(feature["macd_hist"])
    volume_ratio = fnum(feature["volume_ratio_20d"], 1)
    return20 = fnum(feature["return_20d"])
    distance_high = fnum(feature["distance_high_20d"], -20)
    volatility = fnum(feature["volatility_20d"])

    trend_points = 0
    trend_points += 25 if close > ma5 > 0 else 0
    trend_points += 25 if ma5 > ma20 > 0 else 0
    trend_points += 25 if ma20 > ma60 > 0 else 0
    trend_points += 25 if ma60 > ma120 > 0 else 0
    trend_score = clamp(trend_points)

    if 50 <= rsi14 <= 70:
        rsi_points = 80 + (rsi14 - 50)
    elif 40 <= rsi14 < 50:
        rsi_points = 50 + (rsi14 - 40) * 3
    elif 70 < rsi14 <= 80:
        rsi_points = 90 - (rsi14 - 70) * 4
    else:
        rsi_points = 30
    momentum_score = clamp(
        rsi_points * 0.6
        + clamp(50 + macd_hist * 20) * 0.2
        + clamp(50 + return20 * 3) * 0.2
    )

    volume_score = clamp(40 + (volume_ratio - 1) * 50)
    breakout_score = clamp(100 + distance_high * 8)
    relative_strength_score = clamp(50 + return20 * 3)
    institutional_score = 50.0
    market_score = 70.0
    risk_score = clamp(100 - volatility * 15)

    total = (
        trend_score * 0.20
        + momentum_score * 0.15
        + volume_score * 0.15
        + institutional_score * 0.15
        + breakout_score * 0.10
        + relative_strength_score * 0.10
        + market_score * 0.10
        + risk_score * 0.05
    )

    if total >= 90:
        signal = "S級強多"
    elif total >= 80:
        signal = "A級多頭"
    elif total >= 70:
        signal = "B級觀察"
    elif total >= 60:
        signal = "C級中性"
    else:
        signal = "D級避開"

    confidence = clamp(50 + abs(total - 50) * 0.8)

    return {
        "strategy_version": "V2.5-AUTO",
        "total_score": round(total, 2),
        "trend_score": round(trend_score, 2),
        "momentum_score": round(momentum_score, 2),
        "volume_score": round(volume_score, 2),
        "institutional_score": round(institutional_score, 2),
        "breakout_score": round(breakout_score, 2),
        "relative_strength_score": round(relative_strength_score, 2),
        "market_score": round(market_score, 2),
        "risk_score": round(risk_score, 2),
        "signal": signal,
        "confidence": round(confidence, 2),
    }


def normalize_prices(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}

    for row in raw_rows:
        trade_date = row.get("date")
        if not trade_date:
            continue

        normalized[trade_date] = {
            "trade_date": trade_date,
            "open": fnum(row.get("open")),
            "high": fnum(row.get("max", row.get("high"))),
            "low": fnum(row.get("min", row.get("low"))),
            "close": fnum(row.get("close")),
            "volume": inum(
                row.get("Trading_Volume", row.get("volume"))
            ),
            "turnover": fnum(
                row.get("Trading_money", row.get("turnover"))
            ),
            "adj_close": fnum(row.get("close")),
        }

    return sorted(normalized.values(), key=lambda item: item["trade_date"])


def process_symbol(symbol: str, start_date: str) -> None:
    print(f"\n=== {symbol} ===")

    stock = get_stock(symbol)
    if stock is None:
        supabase_upsert(
            "stocks",
            [
                {
                    "symbol": symbol,
                    "name": symbol,
                    "market": "TWSE",
                    "industry": None,
                    "is_active": True,
                }
            ],
            "symbol",
        )
        stock = get_stock(symbol)

    if stock is None:
        raise RuntimeError(f"Unable to create stock row for {symbol}")

    stock_id = stock["id"]
    raw_prices = fetch_finmind("TaiwanStockPrice", symbol, start_date)
    price_rows = normalize_prices(raw_prices)

    if not price_rows:
        print(f"  no price data returned for {symbol}")
        return

    db_prices = [{**row, "stock_id": stock_id} for row in price_rows]
    supabase_upsert("daily_prices", db_prices, "stock_id,trade_date")

    if len(price_rows) < 120:
        print(
            f"  only {len(price_rows)} rows; need at least 120 rows to calculate signals"
        )
        return

    feature = calculate_latest_feature(price_rows)
    feature["stock_id"] = stock_id
    supabase_upsert(
        "features",
        [feature],
        "stock_id,trade_date",
    )

    signal = score_feature(feature)
    signal.update(
        {
            "stock_id": stock_id,
            "trade_date": feature["trade_date"],
        }
    )
    supabase_upsert(
        "signals",
        [signal],
        "stock_id,trade_date,strategy_version",
    )

    print(
        f"  latest={feature['trade_date']} score={signal['total_score']} "
        f"signal={signal['signal']}"
    )


def main() -> int:
    if not SYMBOLS:
        raise RuntimeError("STOCK_SYMBOLS is empty")

    start_date = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    print(
        f"Updating {len(SYMBOLS)} symbols from {start_date}; "
        f"Supabase={SUPABASE_URL}"
    )

    failures: list[str] = []
    for symbol in SYMBOLS:
        try:
            process_symbol(symbol, start_date)
            time.sleep(0.4)
        except Exception as exc:
            failures.append(symbol)
            print(f"ERROR {symbol}: {exc}", file=sys.stderr)

    if failures:
        raise RuntimeError(f"Failed symbols: {', '.join(failures)}")

    print("\nMarket update completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
