from __future__ import annotations

import json
import os
import statistics
from datetime import date
from typing import Any

import requests

TIMEOUT = 60
STRATEGY_VERSION = os.getenv("REPORT_STRATEGY", "V3.1-MULTI").strip()


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
        "User-Agent": "GPT-Quant-V5-Report/1.0",
    }
)


def api_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def check(response: requests.Response, context: str) -> None:
    if response.ok:
        return
    raise RuntimeError(
        f"{context}: HTTP {response.status_code}: {response.text[:1000]}"
    )


def fetch(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    response = session.get(api_url(table), params=params, timeout=TIMEOUT)
    check(response, f"fetch {table}")
    return response.json()


def upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    response = session.post(
        api_url(table),
        params={"on_conflict": on_conflict},
        headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        json=rows,
        timeout=TIMEOUT,
    )
    check(response, f"upsert {table}")


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def main() -> None:
    latest = fetch(
        "signals",
        {
            "select": "trade_date",
            "strategy_version": f"eq.{STRATEGY_VERSION}",
            "order": "trade_date.desc",
            "limit": "1",
        },
    )
    if not latest:
        raise RuntimeError(f"No signals for strategy {STRATEGY_VERSION}")

    report_date = latest[0]["trade_date"]

    signals = fetch(
        "signals",
        {
            "select": (
                "id,stock_id,trade_date,strategy_version,total_score,"
                "trend_score,momentum_score,volume_score,risk_score,"
                "signal,confidence,analysis_reasons,entry_low,entry_high,"
                "stop_loss_price,target_price_1,target_price_2,"
                "stocks(symbol,name,industry)"
            ),
            "strategy_version": f"eq.{STRATEGY_VERSION}",
            "trade_date": f"eq.{report_date}",
            "order": "total_score.desc",
            "limit": "50",
        },
    )

    features = fetch(
        "features",
        {
            "select": "stock_id,return_20d,volatility_20d,rsi14",
            "trade_date": f"eq.{report_date}",
            "limit": "500",
        },
    )
    features_by_stock = {int(row["stock_id"]): row for row in features}

    scores = [number(row["total_score"]) for row in signals]
    risks = [number(row["risk_score"]) for row in signals]
    bullish = [row for row in signals if number(row["total_score"]) >= 60]
    bullish_ratio = len(bullish) / len(signals) if signals else 0.0
    average_score = statistics.mean(scores) if scores else 0.0
    average_risk = statistics.mean(risks) if risks else 0.0

    volatilities = [
        number(features_by_stock.get(int(row["stock_id"]), {}).get("volatility_20d"))
        for row in signals
    ]
    volatilities = [value for value in volatilities if value > 0]
    average_volatility = statistics.mean(volatilities) if volatilities else 0.0

    health = max(
        0.0,
        min(
            100.0,
            average_score * 0.50
            + average_risk * 0.25
            + bullish_ratio * 100 * 0.25,
        ),
    )

    if average_score >= 70 and bullish_ratio >= 0.60:
        market_state = "強勢多頭"
    elif average_score >= 55 and bullish_ratio >= 0.50:
        market_state = "偏多"
    elif average_score >= 45:
        market_state = "中性整理"
    elif average_score >= 35:
        market_state = "偏空"
    else:
        market_state = "空頭"

    if average_volatility >= 4.0 or health < 40:
        risk_level = "HIGH"
    elif average_volatility >= 2.5 or health < 60:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    top_signals = []
    for row in signals[:10]:
        stock = row.get("stocks") or {}
        top_signals.append(
            {
                "symbol": stock.get("symbol"),
                "name": stock.get("name"),
                "score": number(row.get("total_score")),
                "signal": row.get("signal"),
                "confidence": number(row.get("confidence")),
                "entry_low": row.get("entry_low"),
                "entry_high": row.get("entry_high"),
                "stop_loss": row.get("stop_loss_price"),
                "target_1": row.get("target_price_1"),
                "reasons": row.get("analysis_reasons") or [],
            }
        )

    risk_flags = []
    for row in signals:
        score = number(row.get("total_score"))
        risk_score = number(row.get("risk_score"))
        stock = row.get("stocks") or {}
        if risk_score < 45 or score < 40:
            risk_flags.append(
                {
                    "symbol": stock.get("symbol"),
                    "name": stock.get("name"),
                    "score": score,
                    "risk_score": risk_score,
                    "message": "分數或風險指標低於安全門檻",
                }
            )

    leader = top_signals[0] if top_signals else None
    if leader:
        summary = (
            f"{report_date} 市場狀態為{market_state}，平均分數 "
            f"{average_score:.1f}，策略健康度 {health:.0f}/100。"
            f"目前最高分為 {leader['symbol']} {leader['name']}，"
            f"Score {leader['score']:.1f}。"
        )
    else:
        summary = (
            f"{report_date} 沒有可用訊號，建議檢查市場資料與策略執行狀態。"
        )

    if risk_level == "HIGH":
        action_plan = "風險偏高：降低曝險、縮小部位，優先等待市場與策略分數回升。"
    elif risk_level == "MEDIUM":
        action_plan = "風險中等：僅關注高分且風險分數較佳的標的，嚴守停損。"
    else:
        action_plan = "風險較低：可依分數、進場區間與停損規則分批建立模擬部位。"

    report = {
        "report_date": report_date,
        "market_state": market_state,
        "market_score": round(average_score, 2),
        "strategy_health": round(health, 2),
        "top_signals": top_signals,
        "risk_flags": risk_flags[:20],
        "summary": summary,
        "action_plan": action_plan,
        "generated_by": "V5-RULE-ENGINE",
    }
    upsert("daily_reports", [report], "report_date")

    risk_snapshot = {
        "snapshot_date": report_date,
        "average_score": round(average_score, 2),
        "bullish_ratio": round(bullish_ratio, 6),
        "average_volatility": round(average_volatility, 6),
        "risk_level": risk_level,
        "var_95": None,
        "concentration_risk": None,
    }
    upsert("risk_snapshots", [risk_snapshot], "snapshot_date")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
