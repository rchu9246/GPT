"""GPT Quant V20 Institutional Edition aggregator.

Builds:
- performance attribution
- system health score
- institutional executive report

The process reads existing V13-V19 PAPER data and does not place orders.
"""
from __future__ import annotations

import math
import os
from datetime import date
from typing import Any
from urllib.parse import quote

import requests

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")

if not URL or not KEY:
    raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}
UPSERT = {
    **HEADERS,
    "Prefer": "resolution=merge-duplicates,return=representation",
}

def api(table: str, query: str = "") -> str:
    return f"{URL}/rest/v1/{table}" + (f"?{query}" if query else "")

def get_rows(table: str, query: str = "") -> list[dict[str, Any]]:
    response = requests.get(api(table, query), headers=HEADERS, timeout=45)
    response.raise_for_status()
    return response.json()

def upsert_rows(table: str, payload: Any, conflict: str) -> list[dict[str, Any]]:
    response = requests.post(
        api(table, f"on_conflict={quote(conflict)}"),
        headers=UPSERT,
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()

def number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

signals = get_rows(
    "signals",
    "select=trade_date,total_score,trend_score,momentum_score,risk_score"
    "&order=trade_date.desc&limit=500",
)
orders = get_rows(
    "trade_orders_v13",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&select=status,side,notional,created_at&order=created_at.desc&limit=1000",
)
positions = get_rows(
    "paper_positions_v13",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&select=symbol,market_value,unrealized_pnl&limit=1000",
)
account_rows = get_rows(
    "paper_accounts_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
risk_rows = get_rows(
    "risk_snapshots_v19",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=snapshot_date.desc&limit=1",
)
allocations = get_rows(
    "hedge_fund_allocations_v19",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=allocation_date.desc,strategy_weight.desc&limit=20",
)
committee = get_rows(
    "ai_committee_decisions_v18",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=decision_date.desc,committee_score.desc&limit=100",
)
snapshots = get_rows(
    "paper_equity_snapshots_v13",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=snapshot_date.asc&limit=365",
)

report_date = (
    str(signals[0]["trade_date"])
    if signals
    else date.today().isoformat()
)

account = account_rows[0] if account_rows else {}
equity = number(account.get("equity"))
cash = number(account.get("cash"))
market_value = sum(number(row.get("market_value")) for row in positions)
unrealized = sum(number(row.get("unrealized_pnl")) for row in positions)

latest_signal_date = str(signals[0]["trade_date"]) if signals else None
latest_signals = [
    row for row in signals
    if latest_signal_date and str(row.get("trade_date")) == latest_signal_date
]
avg_score = (
    sum(number(row.get("total_score")) for row in latest_signals)
    / max(1, len(latest_signals))
)
avg_trend = (
    sum(number(row.get("trend_score")) for row in latest_signals)
    / max(1, len(latest_signals))
)
avg_momentum = (
    sum(number(row.get("momentum_score")) for row in latest_signals)
    / max(1, len(latest_signals))
)
avg_risk = (
    sum(number(row.get("risk_score")) for row in latest_signals)
    / max(1, len(latest_signals))
)

equity_values = [
    number(row.get("equity"))
    for row in snapshots
    if number(row.get("equity")) > 0
]
total_return = 0.0
if len(equity_values) >= 2 and equity_values[0] > 0:
    total_return = equity_values[-1] / equity_values[0] - 1

# Attribution is intentionally transparent and additive for operational review.
components = [
    (
        "MARKET_BETA",
        total_return * 0.35,
        market_value / equity if equity else 0,
        "Exposure-based market contribution proxy.",
    ),
    (
        "STOCK_SELECTION_ALPHA",
        total_return * 0.30,
        avg_score / 100,
        "Contribution proxy from average signal quality.",
    ),
    (
        "MOMENTUM_FACTOR",
        total_return * 0.15,
        avg_momentum / 100,
        "Contribution proxy from momentum factor exposure.",
    ),
    (
        "TREND_FACTOR",
        total_return * 0.15,
        avg_trend / 100,
        "Contribution proxy from trend factor exposure.",
    ),
    (
        "CASH_DRAG",
        -abs(total_return) * (cash / equity if equity else 0) * 0.05,
        cash / equity if equity else 0,
        "Estimated cash drag or protection effect.",
    ),
]

for component, contribution, exposure, detail in components:
    upsert_rows(
        "performance_attribution_v20",
        {
            "account_name": ACCOUNT,
            "attribution_date": report_date,
            "component": component,
            "contribution": contribution * 100,
            "exposure": exposure * 100,
            "detail": detail,
        },
        "account_name,attribution_date,component",
    )

risk = risk_rows[0] if risk_rows else {}
risk_status = str(risk.get("risk_status") or "NO_DATA")
proposed = sum(1 for row in orders if row.get("status") == "PROPOSED")
approved = sum(1 for row in orders if row.get("status") == "APPROVED")
filled = sum(1 for row in orders if row.get("status") == "FILLED")

health = 0.0
health += 20 if signals else 0
health += 20 if account_rows else 0
health += 20 if risk_rows else 0
health += 20 if allocations else 0
health += 20 if committee else 0

data_status = "PASS" if signals else "FAIL"
signal_status = "PASS" if latest_signals else "WARN"
execution_status = (
    "PASS"
    if filled or proposed or approved
    else "IDLE"
)
portfolio_status = "PASS" if account_rows else "FAIL"
strategy_status = "PASS" if allocations and committee else "WARN"

headline = (
    "Institutional platform operational"
    if health >= 80
    else "Institutional platform requires attention"
)

executive_summary = (
    f"System health {health:.0f}/100. Equity {equity:.2f}, "
    f"cash {cash:.2f}, positions {len(positions)}, "
    f"latest average score {avg_score:.1f}, average risk {avg_risk:.1f}. "
    f"Orders: {proposed} proposed, {approved} approved, {filled} filled."
)

actions = []
if not signals:
    actions.append("Run market-data and signal workflows.")
if proposed:
    actions.append(f"Review {proposed} proposed PAPER orders.")
if approved:
    actions.append(f"Fill or reject {approved} approved PAPER orders.")
if risk_status not in {"PASS", "NO_DATA"}:
    actions.append(f"Review risk status: {risk_status}.")
if not actions:
    actions.append("Continue daily institutional workflow and monitor risk.")

upsert_rows(
    "institutional_reports_v20",
    {
        "account_name": ACCOUNT,
        "report_date": report_date,
        "system_health": health,
        "data_status": data_status,
        "signal_status": signal_status,
        "execution_status": execution_status,
        "portfolio_status": portfolio_status,
        "risk_status": risk_status,
        "strategy_status": strategy_status,
        "headline": headline,
        "executive_summary": executive_summary,
        "action_items": " ".join(actions),
    },
    "account_name,report_date",
)

print(headline)
print(executive_summary)
print(" ".join(actions))
