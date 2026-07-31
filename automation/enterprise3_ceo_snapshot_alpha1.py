from __future__ import annotations

import os
from datetime import date
from typing import Any

from enterprise2.client import SupabaseRestClient

ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

def number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback

def latest(
    client: SupabaseRestClient,
    table: str,
    date_field: str,
) -> dict[str, Any] | None:
    rows = client.get(
        table,
        f"account_name=eq.{ACCOUNT}&order={date_field}.desc&limit=1",
    )
    return rows[0] if rows else None

def main() -> None:
    client = SupabaseRestClient()

    operational = latest(client, "quant_operational_status", "status_date") or {}
    health = latest(client, "quant_system_health", "health_date") or {}
    portfolio = latest(client, "quant_portfolio_snapshots", "snapshot_date") or {}
    directive = latest(client, "trading_directives_v22", "directive_date") or {}

    reports = client.get(
        "quant_research_reports",
        f"account_name=eq.{ACCOUNT}"
        "&order=report_date.desc,research_score.desc&limit=10",
    )
    events = client.get(
        "quant_risk_events",
        f"account_name=eq.{ACCOUNT}&status=eq.OPEN"
        "&order=event_date.desc,created_at.desc&limit=100",
    )
    orders = client.get(
        "trade_orders_v13",
        f"account_name=eq.{ACCOUNT}&select=status&limit=5000",
    )
    decisions = client.get(
        "quant_decisions",
        f"account_name=eq.{ACCOUNT}"
        "&order=decision_date.desc,score.desc&limit=10",
    )

    top_ideas = [
        {
            "symbol": row.get("symbol"),
            "rating": row.get("rating"),
            "score": number(row.get("research_score")),
            "confidence": number(row.get("confidence")),
            "risk": row.get("risk_view"),
        }
        for row in reports[:5]
    ]
    latest_actions = [
        {
            "scope": row.get("decision_scope"),
            "entity": row.get("entity_key"),
            "module": row.get("module_key"),
            "action": row.get("action"),
            "score": number(row.get("score")),
        }
        for row in decisions[:5]
    ]

    research_confidence = (
        sum(number(row.get("confidence")) for row in reports) / len(reports)
        if reports
        else 0
    )

    client.upsert(
        "quant_ceo_snapshots",
        {
            "account_name": ACCOUNT,
            "snapshot_date": RUN_DATE,
            "platform_status": str(
                operational.get("pipeline_status") or "NO_DATA"
            ),
            "market_posture": str(
                directive.get("market_state") or "NO_DATA"
            ),
            "director_action": str(
                directive.get("directive") or "NO_DATA"
            ),
            "research_confidence": research_confidence,
            "system_health": number(health.get("overall_score")),
            "operational_score": number(operational.get("overall_score")),
            "equity": number(portfolio.get("equity")),
            "cash": number(portfolio.get("cash")),
            "total_return": number(portfolio.get("total_return")),
            "max_drawdown": number(portfolio.get("max_drawdown")),
            "risk_events": len(events),
            "proposed_orders": sum(
                1 for row in orders if row.get("status") == "PROPOSED"
            ),
            "approved_orders": sum(
                1 for row in orders if row.get("status") == "APPROVED"
            ),
            "filled_orders": sum(
                1 for row in orders if row.get("status") == "FILLED"
            ),
            "top_ideas": top_ideas,
            "latest_actions": latest_actions,
        },
        "account_name,snapshot_date",
    )

    print("Enterprise 3.0 CEO snapshot generated.")

if __name__ == "__main__":
    main()
