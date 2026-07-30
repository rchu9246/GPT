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


FINMIND_TOKEN = "".join(required_env("FINMIND_TOKEN").split())
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
    }
    headers = {
        "Authorization": f"Bearer {FINMIND_TOKEN}",
        "User-Agent": "GPT-Quant-Automation/1.1",
    }
    response = requests.get(
        FINMIND_URL,
        params=params,
        headers=headers,
        timeout=TIMEOUT,
    )
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



def stochastic_kd(rows: list[dict[str, Any]], period: int = 9, smooth: int = 3):
    if len(rows) < period + smooth:
        return None, None
    raw = []
    for i in range(period - 1, len(rows)):
        window = rows[i-period+1:i+1]
        highest = max(fnum(r["high"]) for r in window)
        lowest = min(fnum(r["low"]) for r in window)
        close = fnum(rows[i]["close"])
        raw.append(50.0 if highest == lowest else (close-lowest)/(highest-lowest)*100)
    k = sum(raw[-smooth:]) / smooth
    k_series = [sum(raw[i-smooth+1:i+1])/smooth for i in range(smooth-1, len(raw))]
    d = sum(k_series[-smooth:]) / smooth if len(k_series) >= smooth else k_series[-1]
    return k, d


def obv_series(closes: list[float], volumes: list[float]) -> list[float]:
    result = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            result.append(result[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            result.append(result[-1] - volumes[i])
        else:
            result.append(result[-1])
    return result


def slope_percent(values: list[float], periods: int) -> float | None:
    if len(values) <= periods:
        return None
    start, end = values[-periods-1], values[-1]
    return (end-start) / (abs(start) if abs(start) > 1e-9 else 1.0) * 100


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
    closes = [fnum(r["close"]) for r in price_rows]
    volumes = [fnum(r["volume"]) for r in price_rows]
    current = price_rows[-1]
    close = closes[-1]
    ma5, ma20, ma60, ma120 = sma(closes,5), sma(closes,20), sma(closes,60), sma(closes,120)
    ema20s, ema60s, ema120s = ema_series(closes,20), ema_series(closes,60), ema_series(closes,120)
    ema20, ema60, ema120 = ema20s[-1], ema60s[-1], ema120s[-1]
    ema12, ema26 = ema_series(closes,12), ema_series(closes,26)
    macd_vals = [a-b for a,b in zip(ema12,ema26)]
    macd_sig_vals = ema_series(macd_vals,9)
    macd, macd_signal = macd_vals[-1], macd_sig_vals[-1]
    macd_hist = macd - macd_signal
    k, d = stochastic_kd(price_rows)
    obv = obv_series(closes, volumes)
    high20, high60 = max(closes[-20:]), max(closes[-60:])
    vol5, vol20 = sma(volumes,5), sma(volumes,20)
    daily_returns = [(closes[i]/closes[i-1]-1)*100 for i in range(1,len(closes)) if closes[i-1] != 0]
    volatility20 = statistics.pstdev(daily_returns[-20:]) if len(daily_returns) >= 2 else 0.0
    ma20_prev = sum(closes[-25:-5])/20 if len(closes)>=25 else ma20
    ma60_prev = sum(closes[-65:-5])/60 if len(closes)>=65 else ma60
    return {
        "trade_date": current["trade_date"], "close": round(close,4),
        "return_1d": pct_change(closes,1), "return_5d": pct_change(closes,5),
        "return_20d": pct_change(closes,20), "roc20": pct_change(closes,20),
        "ma5": ma5, "ma20": ma20, "ma60": ma60, "ma120": ma120,
        "ema20": ema20, "ema60": ema60, "ema120": ema120,
        "ma20_slope": ((ma20/ma20_prev)-1)*100 if ma20 and ma20_prev else None,
        "ma60_slope": ((ma60/ma60_prev)-1)*100 if ma60 and ma60_prev else None,
        "rsi14": rsi(closes,14), "stoch_k": k, "stoch_d": d,
        "macd": macd, "macd_signal": macd_signal, "macd_hist": macd_hist,
        "atr14": atr(price_rows,14),
        "volume_ratio_5d": volumes[-1]/vol5 if vol5 else None,
        "volume_ratio_20d": volumes[-1]/vol20 if vol20 else None,
        "obv_slope_20d": slope_percent(obv,20),
        "volatility_20d": volatility20,
        "high_20d": high20, "high_60d": high60,
        "distance_high_20d": (close/high20-1)*100 if high20 else None,
        "distance_high_60d": (close/high60-1)*100 if high60 else None,
        "foreign_net_5d": 0, "foreign_net_20d": 0,
        "trust_net_5d": 0, "trust_net_20d": 0,
    }

def score_feature(feature: dict[str, Any]) -> dict[str, Any]:
    close = fnum(feature["close"])
    ema20, ema60, ema120 = fnum(feature.get("ema20")), fnum(feature.get("ema60")), fnum(feature.get("ema120"))
    rsi14 = fnum(feature.get("rsi14"),50)
    k, d = fnum(feature.get("stoch_k"),50), fnum(feature.get("stoch_d"),50)
    macd_hist = fnum(feature.get("macd_hist"))
    volume_ratio = fnum(feature.get("volume_ratio_20d"),1)
    obv_slope = fnum(feature.get("obv_slope_20d"))
    roc20 = fnum(feature.get("roc20"))
    dist20, dist60 = fnum(feature.get("distance_high_20d"),-20), fnum(feature.get("distance_high_60d"),-30)
    volatility, atr14 = fnum(feature.get("volatility_20d")), fnum(feature.get("atr14"))
    reasons = []
    trend = 0
    if close > ema20 > 0: trend += 30; reasons.append("收盤站上 EMA20")
    if ema20 > ema60 > 0: trend += 35; reasons.append("EMA20 高於 EMA60")
    if ema60 > ema120 > 0: trend += 35; reasons.append("中長期均線多頭排列")
    trend = clamp(trend)
    momentum = clamp((100-abs(rsi14-60)*3)*0.35 + clamp(55+(k-d)*2)*0.2 + clamp(50+macd_hist*25)*0.25 + clamp(50+roc20*2.5)*0.2)
    if macd_hist > 0: reasons.append("MACD 柱狀體為正")
    if k > d and k < 85: reasons.append("KD 呈多方交叉")
    volume = clamp(clamp(45+(volume_ratio-1)*45)*0.7 + clamp(50+obv_slope*3)*0.3)
    if volume_ratio >= 1.3: reasons.append(f"量能放大至20日均量 {volume_ratio:.1f} 倍")
    breakout = clamp(clamp(100+dist20*10)*0.65 + clamp(100+dist60*6)*0.35)
    if dist20 >= -2: reasons.append("接近或突破20日高點")
    relative = clamp(50+roc20*2.5)
    institutional, market = 50.0, 60.0
    atr_pct = atr14/close*100 if close else 0
    risk = clamp(100-volatility*11-max(atr_pct-2,0)*8-max(rsi14-78,0)*2)
    total = trend*0.24 + momentum*0.20 + volume*0.14 + institutional*0.08 + breakout*0.14 + relative*0.08 + market*0.05 + risk*0.07
    signal = "S級強多" if total>=85 else "A級多頭" if total>=75 else "B級觀察" if total>=65 else "C級中性" if total>=50 else "D級避開"
    confidence = clamp(45+abs(total-50)*0.8+min(len(reasons),6)*2)
    return {
        "strategy_version":"V3.1-MULTI",
        "total_score":round(total,2), "trend_score":round(trend,2),
        "momentum_score":round(momentum,2), "volume_score":round(volume,2),
        "institutional_score":institutional, "breakout_score":round(breakout,2),
        "relative_strength_score":round(relative,2), "market_score":market,
        "risk_score":round(risk,2), "signal":signal, "confidence":round(confidence,2),
        "analysis_reasons":reasons[:8],
        "entry_low":round(close*0.985,2), "entry_high":round(close*1.015,2),
        "stop_loss_price":round(max(close-max(atr14*2,close*0.05),0.01),2),
        "target_price_1":round(close+max(atr14*2.5,close*0.08),2),
        "target_price_2":round(close+max(atr14*4,close*0.13),2),
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
    print(
        f"FinMind token loaded: length={len(FINMIND_TOKEN)}, "
        f"tail=...{FINMIND_TOKEN[-6:] if len(FINMIND_TOKEN) >= 6 else 'short'}"
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
