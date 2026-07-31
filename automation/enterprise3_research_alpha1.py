"""Enterprise 3.0 Alpha 1 Research Intelligence.

This release uses existing internal quantitative evidence. It does not invent
external news or financial-statement facts. Manual/external research can be
added later through quant_research_items.
"""
from __future__ import annotations

import math
import os
from datetime import date
from typing import Any

from enterprise2.client import SupabaseRestClient

ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

def number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))

def rating(score: float, risk: float) -> str:
    if risk >= 70:
        return "AVOID"
    if score >= 75:
        return "STRONG_BUY"
    if score >= 60:
        return "BUY"
    if score >= 45:
        return "WATCH"
    return "AVOID"

def main() -> None:
    client = SupabaseRestClient()

    signals = client.get(
        "signals",
        "select=stock_id,trade_date,strategy_version,total_score,trend_score,"
        "momentum_score,volume_score,risk_score,confidence"
        "&order=trade_date.desc,total_score.desc&limit=1000",
    )
    if not signals:
        print("No signals; no research reports generated.")
        return

    latest_date = str(signals[0]["trade_date"])
    latest_signals = [
        row for row in signals if str(row.get("trade_date")) == latest_date
    ]

    stocks = client.get("stocks", "select=id,symbol,name&limit=10000")
    stock_by_id = {str(row["id"]): row for row in stocks}

    dedup: dict[str, dict[str, Any]] = {}
    for row in latest_signals:
        stock = stock_by_id.get(str(row.get("stock_id")))
        if not stock:
            continue
        symbol = str(stock.get("symbol") or "")
        if not symbol:
            continue
        current = dedup.get(symbol)
        if current is None or number(row.get("total_score")) > number(
            current["signal"].get("total_score")
        ):
            dedup[symbol] = {"signal": row, "stock": stock}

    generated = 0
    top_ideas = []

    for symbol, item in dedup.items():
        signal = item["signal"]
        stock = item["stock"]

        total = clamp(number(signal.get("total_score")))
        trend = clamp(number(signal.get("trend_score")))
        momentum = clamp(number(signal.get("momentum_score")))
        volume = clamp(number(signal.get("volume_score"), 50))
        risk = clamp(number(signal.get("risk_score"), 50))
        confidence = clamp(number(signal.get("confidence"), 50))

        research_score = clamp(
            total * 0.40
            + trend * 0.20
            + momentum * 0.20
            + volume * 0.10
            + (100 - risk) * 0.10
        )
        research_confidence = clamp(
            confidence * 0.65 + (100 - abs(trend - momentum)) * 0.35
        )
        final_rating = rating(research_score, risk)

        trend_view = (
            "POSITIVE" if trend >= 60 else "NEUTRAL" if trend >= 40 else "NEGATIVE"
        )
        momentum_view = (
            "POSITIVE"
            if momentum >= 60
            else "NEUTRAL"
            if momentum >= 40
            else "NEGATIVE"
        )
        risk_view = (
            "HIGH" if risk >= 65 else "MEDIUM" if risk >= 45 else "LOW"
        )
        catalyst_view = (
            "Internal quantitative factors are aligned."
            if trend >= 60 and momentum >= 60
            else "Factor alignment is incomplete; wait for confirmation."
        )

        thesis = (
            f"{symbol} {stock.get('name') or ''}: internal research score "
            f"{research_score:.1f}. Trend {trend:.1f}, momentum {momentum:.1f}, "
            f"volume {volume:.1f}, risk {risk:.1f}."
        )
        invalidation = (
            "Invalidate the thesis if risk rises above 70, trend falls below "
            "40, or the central risk governor blocks new exposure."
        )

        evidence = {
            "strategy_version": signal.get("strategy_version"),
            "signal_date": latest_date,
            "total_score": total,
            "trend_score": trend,
            "momentum_score": momentum,
            "volume_score": volume,
            "risk_score": risk,
            "signal_confidence": confidence,
        }

        client.upsert(
            "quant_research_items",
            {
                "account_name": ACCOUNT,
                "research_date": latest_date,
                "symbol": symbol,
                "stock_id": signal.get("stock_id"),
                "item_type": "QUANT_RESEARCH",
                "title": f"{symbol} Internal Quant Research",
                "summary": thesis,
                "sentiment": (
                    "POSITIVE"
                    if final_rating in {"STRONG_BUY", "BUY"}
                    else "NEGATIVE"
                    if final_rating == "AVOID"
                    else "NEUTRAL"
                ),
                "impact_score": research_score,
                "confidence": research_confidence,
                "source_key": "QUANT_SIGNAL",
                "source_reference": str(signal.get("strategy_version") or ""),
                "evidence": evidence,
            },
            "account_name,research_date,symbol,item_type,title",
        )

        client.upsert(
            "quant_research_reports",
            {
                "account_name": ACCOUNT,
                "report_date": latest_date,
                "symbol": symbol,
                "stock_id": signal.get("stock_id"),
                "report_version": "3.0-alpha1",
                "rating": final_rating,
                "research_score": research_score,
                "confidence": research_confidence,
                "trend_view": trend_view,
                "momentum_view": momentum_view,
                "risk_view": risk_view,
                "catalyst_view": catalyst_view,
                "thesis": thesis,
                "invalidation_conditions": invalidation,
                "evidence": evidence,
            },
            "account_name,report_date,symbol,report_version",
        )

        if risk >= 70:
            client.upsert(
                "quant_events",
                {
                    "account_name": ACCOUNT,
                    "event_date": latest_date,
                    "symbol": symbol,
                    "stock_id": signal.get("stock_id"),
                    "event_type": "RISK_THRESHOLD",
                    "event_severity": "WARNING",
                    "title": f"{symbol} elevated quantitative risk",
                    "description": f"Risk score reached {risk:.1f}.",
                    "expected_direction": "NEGATIVE",
                    "impact_score": risk,
                    "confidence": confidence,
                    "source_key": "RISK_ENGINE",
                    "metadata": evidence,
                },
                "account_name,event_date,symbol,event_type,title",
            )

        top_ideas.append(
            {
                "symbol": symbol,
                "name": stock.get("name"),
                "rating": final_rating,
                "score": round(research_score, 2),
                "confidence": round(research_confidence, 2),
                "risk": round(risk, 2),
            }
        )
        generated += 1

    # Strategy marketplace from current signal versions.
    versions: dict[str, list[dict[str, Any]]] = {}
    for row in signals:
        version = str(row.get("strategy_version") or "UNKNOWN")
        versions.setdefault(version, []).append(row)

    for version, rows in versions.items():
        latest_signal_date = max(str(row.get("trade_date")) for row in rows)
        average_score = sum(number(row.get("total_score")) for row in rows) / len(rows)
        average_risk = sum(number(row.get("risk_score"), 50) for row in rows) / len(rows)
        quality = clamp(average_score * 0.75 + (100 - average_risk) * 0.25)
        client.upsert(
            "quant_strategy_marketplace",
            {
                "strategy_key": version.lower().replace(".", "-"),
                "strategy_version": version,
                "strategy_name": version,
                "strategy_type": "MULTI_FACTOR",
                "lifecycle_status": "PAPER",
                "enabled": True,
                "author": "GPT Quant",
                "description": (
                    "Imported from the current production signal engine. "
                    "Performance metrics remain unverified until backtest "
                    "and walk-forward results are linked."
                ),
                "signal_count": len(rows),
                "latest_signal_date": latest_signal_date,
                "quality_score": quality,
                "validation_status": "SIGNALS_AVAILABLE",
                "config": {
                    "average_signal_score": average_score,
                    "average_risk_score": average_risk,
                },
            },
            "strategy_key,strategy_version",
        )

    print(f"Generated {generated} internal research reports.")
    print(f"Latest research date: {latest_date}")

if __name__ == "__main__":
    main()
