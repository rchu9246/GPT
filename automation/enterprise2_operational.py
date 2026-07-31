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

def latest(client: SupabaseRestClient, table: str, field: str) -> dict[str, Any] | None:
    rows = client.get(
        table,
        f"account_name=eq.{ACCOUNT}&order={field}.desc&limit=1",
    )
    return rows[0] if rows else None

def main() -> None:
    client = SupabaseRestClient()
    issues: list[str] = []

    prices = client.get("daily_prices", "select=trade_date&order=trade_date.desc&limit=1")
    signals = client.get("signals", "select=trade_date&order=trade_date.desc&limit=1")
    orders = client.get(
        "trade_orders_v13",
        f"account_name=eq.{ACCOUNT}&select=status&limit=5000",
    )
    positions = client.get(
        "paper_positions_v13",
        f"account_name=eq.{ACCOUNT}&select=symbol&limit=5000",
    )
    risk = latest(client, "risk_snapshots_v19", "snapshot_date")
    portfolio = latest(client, "quant_portfolio_snapshots", "snapshot_date")
    health = latest(client, "quant_system_health", "health_date")

    latest_data_date = str(prices[0]["trade_date"]) if prices else None
    latest_signal_date = str(signals[0]["trade_date"]) if signals else None

    data_status = "PASS" if latest_data_date else "FAIL"
    signal_status = "PASS" if latest_signal_date else "FAIL"
    proposed = sum(1 for row in orders if row.get("status") == "PROPOSED")
    approved = sum(1 for row in orders if row.get("status") == "APPROVED")
    filled = sum(1 for row in orders if row.get("status") == "FILLED")
    orders_status = "PASS" if orders else "IDLE"
    portfolio_status = "PASS" if portfolio or positions else "WARN"
    risk_status = str((risk or {}).get("risk_status") or "NO_DATA")
    report_rows = client.get(
        "quant_reports",
        f"account_name=eq.{ACCOUNT}&order=report_date.desc&limit=1",
    )
    reports_status = "PASS" if report_rows else "WARN"

    scores = {
        "data": 100 if data_status == "PASS" else 0,
        "signals": 100 if signal_status == "PASS" else 0,
        "orders": 100 if orders_status in {"PASS", "IDLE"} else 0,
        "portfolio": 100 if portfolio_status == "PASS" else 60,
        "risk": 100 if risk_status in {"PASS", "NO_DATA"} else 40,
        "reports": 100 if reports_status == "PASS" else 60,
    }
    overall = sum(scores.values()) / len(scores)

    if data_status != "PASS":
        issues.append("Market data missing")
    if signal_status != "PASS":
        issues.append("Signals missing")
    if risk_status not in {"PASS", "NO_DATA"}:
        issues.append(f"Risk status: {risk_status}")
    if reports_status != "PASS":
        issues.append("Enterprise report not generated")

    pipeline_status = "HEALTHY" if overall >= 85 else "DEGRADED" if overall >= 60 else "CRITICAL"

    client.upsert(
        "quant_operational_status",
        {
            "account_name": ACCOUNT,
            "status_date": RUN_DATE,
            "pipeline_status": pipeline_status,
            "data_freshness_status": data_status,
            "signals_status": signal_status,
            "orders_status": orders_status,
            "portfolio_status": portfolio_status,
            "risk_status": risk_status,
            "reports_status": reports_status,
            "overall_score": overall,
            "latest_data_date": latest_data_date,
            "latest_signal_date": latest_signal_date,
            "proposed_orders": proposed,
            "approved_orders": approved,
            "filled_orders": filled,
            "open_positions": len(positions),
            "issues": issues,
        },
        "account_name,status_date",
    )

    # Centralized risk checks
    limits = {
        row["limit_key"]: row
        for row in client.get(
            "quant_risk_limits",
            f"account_name=eq.{ACCOUNT}&enabled=eq.true",
        )
    }
    max_drawdown = abs(number((portfolio or {}).get("max_drawdown")))
    equity = number((portfolio or {}).get("equity"))
    var95 = number((portfolio or {}).get("var_95"))
    var_pct = var95 / equity * 100 if equity else 0
    gross = number((portfolio or {}).get("gross_exposure_pct"))

    checks = [
        ("MAX_DRAWDOWN_PCT", max_drawdown),
        ("VAR_95_PCT", var_pct),
        ("MAX_GROSS_EXPOSURE_PCT", gross),
    ]

    risk_events = []
    for key, metric in checks:
        limit = limits.get(key)
        if not limit:
            continue
        hard = number(limit.get("limit_value"))
        warn = number(limit.get("warning_value"), hard)
        severity = None
        if metric >= hard:
            severity = "CRITICAL"
        elif metric >= warn:
            severity = "WARNING"
        if severity:
            event = {
                "account_name": ACCOUNT,
                "event_date": RUN_DATE,
                "event_type": key,
                "severity": severity,
                "metric_value": metric,
                "limit_value": hard,
                "entity_type": "PORTFOLIO",
                "entity_key": ACCOUNT,
                "message": f"{key} metric {metric:.2f} reached {severity.lower()} level.",
                "details": {"warning_value": warn},
            }
            client.insert("quant_risk_events", event)
            risk_events.append(event)

    latest_decisions = client.get(
        "quant_decisions",
        f"account_name=eq.{ACCOUNT}&order=decision_date.desc,score.desc&limit=20",
    )
    top_action = next(
        (
            row for row in latest_decisions
            if row.get("decision_scope") == "PORTFOLIO"
        ),
        None,
    )

    headline = (
        "Operational platform healthy"
        if pipeline_status == "HEALTHY"
        else "Operational attention required"
    )
    market_view = (
        f"Latest data {latest_data_date or 'missing'}, "
        f"latest signals {latest_signal_date or 'missing'}."
    )
    portfolio_view = (
        f"{len(positions)} open positions, "
        f"{proposed} proposed, {approved} approved, {filled} filled orders."
    )
    risk_view = (
        "No active centralized risk events."
        if not risk_events
        else f"{len(risk_events)} centralized risk event(s) require review."
    )
    action_plan = (
        str(top_action.get("rationale"))
        if top_action
        else "Run the full daily master cycle and review proposed PAPER orders."
    )

    client.upsert(
        "quant_daily_briefs",
        {
            "account_name": ACCOUNT,
            "brief_date": RUN_DATE,
            "brief_type": "CEO_DAILY",
            "headline": headline,
            "summary": (
                f"Operational score {overall:.0f}/100. "
                f"Pipeline status {pipeline_status}."
            ),
            "market_view": market_view,
            "portfolio_view": portfolio_view,
            "risk_view": risk_view,
            "action_plan": action_plan,
            "payload": {
                "scores": scores,
                "issues": issues,
                "risk_events": risk_events,
            },
        },
        "account_name,brief_date,brief_type",
    )

    client.upsert(
        "quant_reports",
        {
            "account_name": ACCOUNT,
            "report_date": RUN_DATE,
            "report_type": "OPERATIONAL_DAILY",
            "report_version": "2.1.0",
            "headline": headline,
            "executive_summary": (
                f"Operational score {overall:.0f}/100. {portfolio_view}"
            ),
            "action_items": action_plan,
            "payload": {
                "market_view": market_view,
                "risk_view": risk_view,
                "issues": issues,
            },
        },
        "account_name,report_date,report_type,report_version",
    )

    print(f"Enterprise 2.1 operational score: {overall:.1f}")
    print(headline)
    print(action_plan)

if __name__ == "__main__":
    main()
