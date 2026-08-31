"""GPT Quant V22 Autonomous Trading Director.

Combines V18-V21 outputs into one top-level PAPER trading directive:
BUY, HOLD, REDUCE, EXIT, or CASH.

The engine does not approve, fill, or submit live orders.
"""
from __future__ import annotations

import math
import os
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

def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))

config_rows = get_rows(
    "autotrader_configs_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not config_rows:
    raise SystemExit("No autotrader config")
config = config_rows[0]

if not bool(config.get("director_enabled", True)):
    raise SystemExit("Trading Director disabled")
if bool(config.get("kill_switch")):
    raise SystemExit("Kill switch enabled")
if str(config.get("mode")) != "PAPER":
    raise SystemExit("V22 supports PAPER mode only")

account_rows = get_rows(
    "paper_accounts_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not account_rows:
    raise SystemExit("No paper account")
account = account_rows[0]

council_rows = get_rows(
    "council_reports_v21",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=report_date.desc&limit=1",
)
risk_rows = get_rows(
    "risk_snapshots_v19",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=snapshot_date.desc&limit=1",
)
fund_rows = get_rows(
    "cio_reports_v18",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=report_date.desc&limit=1",
)
institutional_rows = get_rows(
    "institutional_reports_v20",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=report_date.desc&limit=1",
)
hedge_rows = get_rows(
    "hedge_fund_reports_v19",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=report_date.desc&limit=1",
)
snapshots = get_rows(
    "paper_equity_snapshots_v13",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=snapshot_date.asc&limit=365",
)
signals = get_rows(
    "signals",
    "select=trade_date,total_score,trend_score,momentum_score,risk_score"
    "&order=trade_date.desc&limit=500",
)

council = council_rows[0] if council_rows else {}
risk = risk_rows[0] if risk_rows else {}
fund = fund_rows[0] if fund_rows else {}
institutional = institutional_rows[0] if institutional_rows else {}
hedge = hedge_rows[0] if hedge_rows else {}

directive_date = (
    str(council.get("report_date"))
    if council.get("report_date")
    else str(signals[0]["trade_date"])
    if signals
    else str(risk.get("snapshot_date"))
)

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
    sum(number(row.get("risk_score"), 50) for row in latest_signals)
    / max(1, len(latest_signals))
)

market_opportunity = clamp(
    0.40 * avg_score
    + 0.30 * avg_trend
    + 0.30 * avg_momentum
)
market_risk = clamp(avg_risk)
market_liquidity = 70 if latest_signals else 20
market_breadth = clamp(number(council.get("average_consensus"), avg_score))

if market_opportunity >= 65 and market_risk <= 45:
    market_state = "BULL"
elif market_risk >= 75:
    market_state = "CRASH_RISK"
elif market_risk >= 65 or market_opportunity < 30:
    market_state = "BEAR"
elif market_opportunity < 45:
    market_state = "CORRECTION"
else:
    market_state = "NEUTRAL"

market_confidence = clamp(
    100 - abs(market_opportunity - market_breadth)
)

upsert_rows(
    "market_state_v22",
    {
        "account_name": ACCOUNT,
        "state_date": directive_date,
        "market_state": market_state,
        "opportunity_score": market_opportunity,
        "risk_score": market_risk,
        "liquidity_score": market_liquidity,
        "breadth_score": market_breadth,
        "confidence": market_confidence,
        "rationale": (
            f"Opportunity {market_opportunity:.1f}, risk {market_risk:.1f}, "
            f"breadth {market_breadth:.1f}, liquidity {market_liquidity:.1f}."
        ),
    },
    "account_name,state_date",
)

equity_values = [
    number(row.get("equity"))
    for row in snapshots
    if number(row.get("equity")) > 0
]
peak = 0.0
drawdown = 0.0
for value in equity_values:
    peak = max(peak, value)
    if peak > 0:
        drawdown = min(drawdown, value / peak - 1)

drawdown_pct = abs(drawdown * 100)
risk_status = str(risk.get("risk_status") or "NO_DATA")
council_posture = str(council.get("market_posture") or "NO_DATA")
fund_regime = str(fund.get("market_regime") or "NO_DATA")
institutional_health = number(institutional.get("system_health"), 0)
council_consensus = number(council.get("average_consensus"), 0)
buy_decisions = number(council.get("buy_decisions"), 0)
vetoed_decisions = number(council.get("vetoed_decisions"), 0)

components = [
    (
        "MARKET_STATE",
        market_opportunity,
        0.25,
        f"{market_state}: opportunity {market_opportunity:.1f}.",
    ),
    (
        "COUNCIL",
        council_consensus,
        0.25,
        f"{council_posture}: {buy_decisions:.0f} BUY, "
        f"{vetoed_decisions:.0f} VETOED.",
    ),
    (
        "RISK",
        clamp(100 - market_risk),
        0.25,
        f"{risk_status}: risk-adjusted score {100-market_risk:.1f}.",
    ),
    (
        "SYSTEM_HEALTH",
        institutional_health,
        0.15,
        f"Institutional health {institutional_health:.1f}/100.",
    ),
    (
        "PORTFOLIO_DRAWDOWN",
        clamp(100 - drawdown_pct * 5),
        0.10,
        f"Current maximum observed drawdown {drawdown_pct:.2f}%.",
    ),
]

director_score = sum(score * weight for _, score, weight, _ in components)
risk_gate = "PASS"

drawdown_stop = number(config.get("director_drawdown_stop_pct"), 12)
if drawdown_pct >= drawdown_stop:
    risk_gate = "BLOCK"
elif risk_status in {"REDUCE_RISK", "DRAWDOWN_ALERT", "EXPOSURE_ALERT"}:
    risk_gate = "CAUTION"
elif market_state == "CRASH_RISK":
    risk_gate = "BLOCK"

buy_threshold = number(config.get("director_buy_threshold"), 65)
reduce_threshold = number(config.get("director_reduce_threshold"), 35)
max_deploy_pct = number(config.get("director_max_deploy_pct"), 20)
min_cash_pct = number(config.get("director_min_cash_pct"), 25)

directive = "HOLD"
deploy_pct = 0.0
reduce_pct = 0.0
target_cash_pct = min_cash_pct

if risk_gate == "BLOCK":
    directive = "CASH" if market_state == "CRASH_RISK" else "EXIT"
    target_cash_pct = 90 if market_state == "CRASH_RISK" else 70
    reduce_pct = 100 if directive == "EXIT" else 70
elif director_score >= buy_threshold and buy_decisions > 0:
    directive = "BUY"
    deploy_pct = clamp(
        (director_score - buy_threshold)
        / max(1, 100 - buy_threshold)
        * max_deploy_pct,
        5,
        max_deploy_pct,
    )
    target_cash_pct = max(min_cash_pct, 100 - deploy_pct - 60)
elif director_score <= reduce_threshold or risk_gate == "CAUTION":
    directive = "REDUCE"
    reduce_pct = clamp((reduce_threshold - director_score) + 10, 10, 40)
    target_cash_pct = max(50, min_cash_pct)
else:
    directive = "HOLD"
    target_cash_pct = max(
        min_cash_pct,
        number(fund.get("target_cash_pct"), min_cash_pct),
    )

confidence = clamp(
    0.55 * abs(director_score - 50) * 2
    + 0.25 * market_confidence
    + 0.20 * institutional_health
)

council_alignment = (
    "ALIGNED"
    if (
        directive == "BUY" and buy_decisions > 0
        or directive in {"REDUCE", "EXIT", "CASH"} and vetoed_decisions > 0
    )
    else "MIXED"
)

portfolio_action = {
    "BUY": f"Deploy up to {deploy_pct:.1f}% of equity through approved PAPER orders.",
    "HOLD": "Maintain current allocation and monitor new signals.",
    "REDUCE": f"Reduce gross exposure by approximately {reduce_pct:.1f}%.",
    "EXIT": "Exit risk positions through reviewed PAPER sell orders.",
    "CASH": "Preserve capital and raise cash aggressively.",
}[directive]

rationale = (
    f"Director score {director_score:.1f}; market {market_state}; "
    f"risk gate {risk_gate}; council {council_posture}; "
    f"fund regime {fund_regime}; drawdown {drawdown_pct:.2f}%."
)

upsert_rows(
    "trading_directives_v22",
    {
        "account_name": ACCOUNT,
        "directive_date": directive_date,
        "directive": directive,
        "confidence": confidence,
        "target_cash_pct": target_cash_pct,
        "deploy_capital_pct": deploy_pct,
        "reduce_exposure_pct": reduce_pct,
        "market_state": market_state,
        "risk_gate": risk_gate,
        "council_alignment": council_alignment,
        "portfolio_action": portfolio_action,
        "rationale": rationale,
    },
    "account_name,directive_date",
)

for component, score, weight, explanation in components:
    upsert_rows(
        "director_reasoning_v22",
        {
            "account_name": ACCOUNT,
            "directive_date": directive_date,
            "component": component,
            "component_status": (
                "PASS" if score >= 60 else "WARN" if score >= 40 else "FAIL"
            ),
            "score": score,
            "weight": weight * 100,
            "contribution": score * weight,
            "explanation": explanation,
        },
        "account_name,directive_date,component",
    )

print(f"Directive: {directive}")
print(f"Confidence: {confidence:.1f}")
print(portfolio_action)
print(rationale)
