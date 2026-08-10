from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import requests

TIMEOUT = 60
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

RUN_DATE = os.getenv("RUN_DATE", str(date.today())).strip()
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip()
SCORE_THRESHOLD = float(os.getenv("PAPER_SCORE_THRESHOLD", "65"))
MIN_HISTORY_ROWS = int(os.getenv("SIGNAL_MIN_HISTORY_ROWS", "122"))
MAX_STALE_DAYS = int(os.getenv("SIGNAL_MAX_STALE_DAYS", "5"))
TOP_N = int(os.getenv("SIGNAL_TOP_N", "30"))
ARTIFACT_DIR = Path(os.getenv("SIGNAL_ARTIFACT_DIR", "artifacts/paper_trading_phase21"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "GPT-Quant-V9.2-Phase2.1-SignalEngine/1.0",
})

def api_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"

def check(response: requests.Response, context: str) -> None:
    if not response.ok:
        raise RuntimeError(f"{context}: HTTP {response.status_code}: {response.text[:1500]}")

def fetch_all(table: str, params: dict[str, str], page_size: int = 1000) -> list[dict[str, Any]]:
    out, offset = [], 0
    while True:
        p = dict(params)
        p["limit"] = str(page_size)
        p["offset"] = str(offset)
        r = session.get(api_url(table), params=p, timeout=TIMEOUT)
        check(r, f"fetch {table}")
        batch = r.json()
        out.extend(batch)
        if len(batch) < page_size:
            return out
        offset += page_size

def upsert(table: str, payload: dict[str, Any], on_conflict: str) -> dict[str, Any]:
    r = session.post(
        api_url(table),
        params={"on_conflict": on_conflict},
        headers={"Prefer":"resolution=merge-duplicates,return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"upsert {table}")
    rows = r.json()
    return rows[0] if rows else payload

def patch_where(table: str, filters: dict[str, str], payload: dict[str, Any]) -> None:
    r = session.patch(
        api_url(table),
        params=filters,
        headers={"Prefer":"return=minimal"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"patch {table}")

def fnum(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default

def ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2 / (period + 1)
    cur = values[0]
    for value in values[1:]:
        cur = alpha * value + (1 - alpha) * cur
    return cur

def sma(values: list[float], period: int) -> float | None:
    return sum(values[-period:]) / period if len(values) >= period else None

def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = sum(max(x,0) for x in recent) / period
    losses = sum(max(-x,0) for x in recent) / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100/(1+rs)

def atr(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) <= period:
        return 0.0
    vals = []
    for i in range(1, len(rows)):
        h = fnum(rows[i]["high"])
        l = fnum(rows[i]["low"])
        pc = fnum(rows[i-1]["close"])
        vals.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(vals[-period:]) / period

def clamp(v: float) -> float:
    return max(0.0, min(100.0, v))

def score_signal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [fnum(r["close"]) for r in rows]
    volumes = [fnum(r["volume"]) for r in rows]
    close = closes[-1]
    ema20 = ema(closes[-120:],20) or 0
    ema60 = ema(closes[-180:],60) or 0
    ema120 = ema(closes[-240:],120) or 0

    trend = 0.0
    trend += 30 if close > ema20 > 0 else 0
    trend += 35 if ema20 > ema60 > 0 else 0
    trend += 35 if ema60 > ema120 > 0 else 0

    rsi14 = rsi(closes)
    ema12 = ema(closes[-80:],12) or 0
    ema26 = ema(closes[-100:],26) or 0
    macd = ema12 - ema26
    roc20 = (close/closes[-21]-1)*100 if len(closes) > 20 and closes[-21] else 0

    momentum = clamp(
        (100 - abs(rsi14-60)*3)*0.45 +
        clamp(50 + macd*20)*0.25 +
        clamp(50 + roc20*2.5)*0.30
    )

    vol20 = sma(volumes,20) or volumes[-1] or 1
    volume_ratio = volumes[-1]/vol20 if vol20 else 1
    volume_score = clamp(45 + (volume_ratio-1)*45)

    high20 = max(closes[-20:])
    high60 = max(closes[-60:])
    breakout = clamp(
        clamp(100 + (close/high20-1)*100*10)*0.65 +
        clamp(100 + (close/high60-1)*100*6)*0.35
    )

    daily_returns = [
        (closes[i]/closes[i-1]-1)*100
        for i in range(1,len(closes)) if closes[i-1]
    ]
    volatility = statistics.pstdev(daily_returns[-20:]) if len(daily_returns)>1 else 0
    atr_pct = atr(rows)/close*100 if close else 0
    risk = clamp(100 - volatility*11 - max(atr_pct-2,0)*8)

    total = (
        trend*0.24 +
        momentum*0.20 +
        volume_score*0.14 +
        50*0.08 +
        breakout*0.14 +
        clamp(50 + roc20*2.5)*0.08 +
        60*0.05 +
        risk*0.07
    )

    label = (
        "S級強多" if total >= 85 else
        "A級多頭" if total >= 75 else
        "B級觀察" if total >= 65 else
        "C級中性" if total >= 50 else
        "D級避開"
    )

    return {
        "score": round(total,2),
        "label": label,
        "trend_score": round(trend,2),
        "momentum_score": round(momentum,2),
        "volume_score": round(volume_score,2),
        "breakout_score": round(breakout,2),
        "risk_score": round(risk,2),
        "rsi14": round(rsi14,2),
        "roc20": round(roc20,2),
        "volume_ratio": round(volume_ratio,4),
        "atr_pct": round(atr_pct,4),
        "reference_price": round(close,4),
    }

def main() -> int:
    stocks = fetch_all("stocks", {
        "select":"id,symbol,name",
        "is_active":"eq.true",
        "order":"symbol.asc",
    })
    prices = fetch_all("daily_prices", {
        "select":"stock_id,trade_date,open,high,low,close,volume",
        "order":"stock_id.asc,trade_date.asc",
    })

    grouped: dict[int,list[dict[str,Any]]] = defaultdict(list)
    latest_market_date = None
    for row in prices:
        if row["trade_date"] <= RUN_DATE:
            grouped[int(row["stock_id"])].append(row)
            if latest_market_date is None or row["trade_date"] > latest_market_date:
                latest_market_date = row["trade_date"]

    stale_days = None
    data_status = "NO_DATA"
    if latest_market_date:
        stale_days = (date.fromisoformat(RUN_DATE) - date.fromisoformat(latest_market_date)).days
        data_status = "FRESH" if stale_days <= MAX_STALE_DAYS else "STALE"

    stocks_with_history = sum(1 for s in stocks if len(grouped.get(int(s["id"]),[])) >= MIN_HISTORY_ROWS)

    upsert("gptq_market_data_health", {
        "run_date":RUN_DATE,
        "source_table":"daily_prices",
        "active_stocks":len(stocks),
        "stocks_with_history":stocks_with_history,
        "latest_market_date":latest_market_date,
        "stale_days":stale_days,
        "rows_scanned":len(prices),
        "status":data_status,
        "message":f"latest_market_date={latest_market_date}; min_history_rows={MIN_HISTORY_ROWS}",
    }, "run_date,source_table")

    ranked = []
    for stock in stocks:
        sid = int(stock["id"])
        rows = grouped.get(sid,[])
        if len(rows) < MIN_HISTORY_ROWS:
            continue

        metrics = score_signal(rows)
        eligible = metrics["score"] >= SCORE_THRESHOLD and data_status == "FRESH"
        reject = None
        if data_status != "FRESH":
            reject = "STALE_MARKET_DATA"
        elif metrics["score"] < SCORE_THRESHOLD:
            reject = "BELOW_SCORE_THRESHOLD"

        row = {
            "run_date":RUN_DATE,
            "strategy_version":STRATEGY_VERSION,
            "stock_id":sid,
            "symbol":stock.get("symbol"),
            "score":metrics["score"],
            "signal_label":metrics["label"],
            "reference_price":metrics["reference_price"],
            "eligible":eligible,
            "selected":False,
            "reject_reason":reject,
            "market_date":rows[-1]["trade_date"],
            "trend_score":metrics["trend_score"],
            "momentum_score":metrics["momentum_score"],
            "volume_score":metrics["volume_score"],
            "breakout_score":metrics["breakout_score"],
            "risk_score":metrics["risk_score"],
            "rsi14":metrics["rsi14"],
            "roc20":metrics["roc20"],
            "volume_ratio":metrics["volume_ratio"],
            "atr_pct":metrics["atr_pct"],
            "data_rows":len(rows),
            "data_fresh":data_status=="FRESH",
        }
        upsert("gptq_paper_signals", row, "run_date,strategy_version,stock_id")
        ranked.append(row)

    ranked.sort(key=lambda x:(-float(x["score"]), x.get("symbol") or ""))
    for i,row in enumerate(ranked, start=1):
        patch_where("gptq_paper_signals", {
            "run_date":f"eq.{RUN_DATE}",
            "strategy_version":f"eq.{STRATEGY_VERSION}",
            "stock_id":f"eq.{row['stock_id']}",
        }, {"rank_no":i})

    eligible_rows = [r for r in ranked if r["eligible"]]
    top = ranked[0] if ranked else None

    dist = {
        "gte_85":sum(1 for r in ranked if r["score"]>=85),
        "gte_75":sum(1 for r in ranked if r["score"]>=75),
        "gte_65":sum(1 for r in ranked if r["score"]>=65),
        "gte_50":sum(1 for r in ranked if r["score"]>=50),
        "below_50":sum(1 for r in ranked if r["score"]<50),
    }

    upsert("gptq_signal_generation_summary", {
        "run_date":RUN_DATE,
        "strategy_version":STRATEGY_VERSION,
        "score_threshold":SCORE_THRESHOLD,
        "stocks_scanned":len(ranked),
        "stocks_eligible":len(eligible_rows),
        "top_score":top["score"] if top else None,
        "top_symbol":top.get("symbol") if top else None,
        "latest_market_date":latest_market_date,
        "data_status":data_status,
        "distribution":dist,
    }, "run_date,strategy_version")

    report = {
        "run_date":RUN_DATE,
        "strategy_version":STRATEGY_VERSION,
        "mode":"SHADOW_ONLY_NO_BROKER",
        "market_data":{
            "status":data_status,
            "latest_market_date":latest_market_date,
            "stale_days":stale_days,
            "active_stocks":len(stocks),
            "stocks_with_history":stocks_with_history,
            "rows_scanned":len(prices),
        },
        "signal_engine":{
            "score_threshold":SCORE_THRESHOLD,
            "stocks_scanned":len(ranked),
            "signals_eligible":len(eligible_rows),
            "top_symbol":top.get("symbol") if top else None,
            "top_score":top["score"] if top else None,
            "distribution":dist,
        },
        "top_candidates":[{
            "rank":i+1,
            "symbol":r.get("symbol"),
            "score":r["score"],
            "label":r["signal_label"],
            "eligible":r["eligible"],
            "reject_reason":r["reject_reason"],
            "market_date":r["market_date"],
        } for i,r in enumerate(ranked[:TOP_N])]
    }

    (ARTIFACT_DIR/"phase21_signal_report.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8",
    )

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("# GPT Quant V9.2 Paper Trading Phase 2.1\n\n")
            f.write(f"- **Market data status**: `{data_status}`\n")
            f.write(f"- **Latest market date**: `{latest_market_date}`\n")
            f.write(f"- **Stocks scanned**: `{len(ranked)}`\n")
            f.write(f"- **Signals eligible**: `{len(eligible_rows)}`\n")
            f.write(f"- **Top candidate**: `{top.get('symbol') if top else None}` / `{top['score'] if top else None}`\n")
            f.write("\n## Top Candidates\n\n")
            f.write("| Rank | Symbol | Score | Label | Eligible | Reason |\n")
            f.write("|---:|---|---:|---|---|---|\n")
            for i,r in enumerate(ranked[:15],start=1):
                f.write(f"| {i} | {r.get('symbol')} | {r['score']} | {r['signal_label']} | {r['eligible']} | {r['reject_reason'] or ''} |\n")

    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
