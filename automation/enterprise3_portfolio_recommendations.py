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

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def main() -> None:
    client = SupabaseRestClient()

    reports = client.get(
        "quant_research_reports",
        f"account_name=eq.{ACCOUNT}"
        "&order=report_date.desc,research_score.desc&limit=100",
    )
    if not reports:
        print("No research reports.")
        return

    latest_date = str(reports[0]["report_date"])
    reports = [r for r in reports if str(r.get("report_date")) == latest_date]

    config_rows = client.get(
        "autotrader_configs_v13",
        f"account_name=eq.{ACCOUNT}&limit=1",
    )
    config = config_rows[0] if config_rows else {}
    max_positions = int(config.get("max_positions") or 5)
    max_position_pct = number(config.get("max_position_pct"), 15)
    min_position_pct = number(config.get("min_position_pct"), 3)
    reserve_cash_pct = number(config.get("reserve_cash_pct"), 30)

    eligible = [
        row for row in reports
        if str(row.get("rating")) in {"STRONG_BUY", "BUY"}
        and str(row.get("risk_view")) != "HIGH"
    ]
    eligible.sort(key=lambda r: number(r.get("research_score")), reverse=True)
    selected = eligible[:max_positions]

    if selected:
        total_conviction = sum(
            max(1.0, number(row.get("research_score")))
            * max(0.25, number(row.get("confidence")) / 100)
            for row in selected
        )
    else:
        total_conviction = 1.0

    generated = 0

    for row in reports:
        symbol = str(row.get("symbol"))
        rating = str(row.get("rating"))
        score = number(row.get("research_score"))
        confidence = number(row.get("confidence"))
        risk_view = str(row.get("risk_view"))
        risk_score = {"LOW": 30, "MEDIUM": 50, "HIGH": 75}.get(risk_view, 50)

        action = "WATCH"
        target_weight = 0.0
        if row in selected:
            action = "BUY"
            conviction_weight = (
                max(1.0, score) * max(0.25, confidence / 100)
            ) / total_conviction
            investable_pct = max(0.0, 100 - reserve_cash_pct)
            target_weight = clamp(
                investable_pct * conviction_weight,
                min_position_pct,
                max_position_pct,
            )
        elif rating == "AVOID" or risk_view == "HIGH":
            action = "AVOID"

        stop_loss = 6 if risk_view == "LOW" else 5 if risk_view == "MEDIUM" else 3
        take_profit = 12 if score >= 75 else 9 if score >= 60 else 6
        holding_days = 20 if score >= 75 else 10 if score >= 60 else 5

        positive = []
        negative = []
        risks = []

        if str(row.get("trend_view")) == "POSITIVE":
            positive.append("Trend score is positive")
        else:
            negative.append(f"Trend view is {row.get('trend_view')}")

        if str(row.get("momentum_view")) == "POSITIVE":
            positive.append("Momentum is aligned")
        else:
            negative.append(f"Momentum view is {row.get('momentum_view')}")

        if confidence >= 70:
            positive.append("Research confidence is high")
        elif confidence < 50:
            negative.append("Research confidence is low")

        if risk_view == "HIGH":
            risks.append("High quantitative risk")
        elif risk_view == "MEDIUM":
            risks.append("Moderate quantitative risk")

        summary = (
            f"{symbol}: {action}. Research score {score:.1f}, confidence "
            f"{confidence:.1f}, risk {risk_view}, target weight "
            f"{target_weight:.1f}%."
        )

        client.upsert(
            "quant_portfolio_recommendations",
            {
                "account_name": ACCOUNT,
                "recommendation_date": latest_date,
                "symbol": symbol,
                "stock_id": row.get("stock_id"),
                "action": action,
                "target_weight": target_weight,
                "max_weight": max_position_pct,
                "expected_return_score": score,
                "risk_score": risk_score,
                "conviction": confidence,
                "sizing_method": "CONVICTION_WEIGHTED_CAP",
                "stop_loss_pct": stop_loss,
                "take_profit_pct": take_profit,
                "suggested_holding_days": holding_days,
                "rationale": summary,
                "constraints": {
                    "reserve_cash_pct": reserve_cash_pct,
                    "max_positions": max_positions,
                    "max_position_pct": max_position_pct,
                },
            },
            "account_name,recommendation_date,symbol",
        )

        client.upsert(
            "quant_explainability_records",
            {
                "account_name": ACCOUNT,
                "explanation_date": latest_date,
                "entity_type": "STOCK",
                "entity_key": symbol,
                "action": action,
                "positive_factors": positive,
                "negative_factors": negative,
                "risk_factors": risks,
                "thresholds": {
                    "buy_score": 60,
                    "high_confidence": 70,
                    "high_risk": 70,
                },
                "decision_path": [
                    "Research report",
                    "Rating filter",
                    "Risk filter",
                    "Position limit",
                    "Conviction sizing",
                ],
                "natural_language_summary": summary,
            },
            (
                "account_name,explanation_date,entity_type,"
                "entity_key,action"
            ),
        )
        generated += 1

    print(f"Generated {generated} portfolio recommendations.")

if __name__ == "__main__":
    main()
