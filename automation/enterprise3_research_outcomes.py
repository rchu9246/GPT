from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from enterprise2.client import SupabaseRestClient

ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

def number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback

def main() -> None:
    client = SupabaseRestClient()

    reports = client.get(
        "quant_research_reports",
        f"account_name=eq.{ACCOUNT}&order=report_date.asc&limit=5000",
    )
    stocks = client.get("stocks", "select=id,symbol&limit=10000")
    stock_by_symbol = {str(r["symbol"]): r for r in stocks}

    evaluated = 0
    for report in reports:
        report_date = str(report.get("report_date"))
        if report_date >= RUN_DATE:
            continue

        symbol = str(report.get("symbol"))
        stock = stock_by_symbol.get(symbol)
        if not stock:
            continue

        prices = client.get(
            "daily_prices",
            f"stock_id=eq.{stock['id']}"
            f"&trade_date=gte.{report_date}"
            f"&trade_date=lte.{RUN_DATE}"
            "&select=trade_date,close"
            "&order=trade_date.asc&limit=100",
        )
        if len(prices) < 2:
            continue

        reference_price = number(prices[0].get("close"))
        evaluation_price = number(prices[-1].get("close"))
        if reference_price <= 0:
            continue

        return_pct = (evaluation_price / reference_price - 1) * 100
        rating = str(report.get("rating"))
        bullish = rating in {"STRONG_BUY", "BUY"}
        hit = return_pct > 0 if bullish else return_pct <= 0
        holding_days = (
            datetime.fromisoformat(str(prices[-1]["trade_date"]))
            - datetime.fromisoformat(str(prices[0]["trade_date"]))
        ).days

        client.upsert(
            "quant_research_outcomes",
            {
                "account_name": ACCOUNT,
                "report_id": report.get("id"),
                "report_date": report_date,
                "evaluation_date": str(prices[-1]["trade_date"]),
                "symbol": symbol,
                "original_rating": rating,
                "original_score": number(report.get("research_score")),
                "reference_price": reference_price,
                "evaluation_price": evaluation_price,
                "return_pct": return_pct,
                "benchmark_return_pct": None,
                "excess_return_pct": None,
                "hit": hit,
                "holding_days": holding_days,
                "outcome_status": "EVALUATED",
                "metadata": {
                    "price_points": len(prices),
                    "evaluation_run_date": RUN_DATE,
                },
            },
            "report_id,evaluation_date",
        )
        evaluated += 1

    print(f"Evaluated {evaluated} research outcomes.")

if __name__ == "__main__":
    main()
