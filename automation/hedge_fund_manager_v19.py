"""GPT Quant V19 Hedge Fund Edition.

Deterministic hedge-fund style allocator built on the existing PAPER portfolio.

Features:
- market regime classification
- multi-strategy allocation
- inverse-volatility risk parity weights
- Kelly-fraction position cap
- 95% / 99% parametric VaR
- expected shortfall proxy
- max drawdown, volatility and Sharpe estimates
- portfolio-level risk status and daily hedge-fund report

No live broker integration.
"""
from __future__ import annotations

import math
import os
import statistics
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

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

config_rows = get_rows(
    "autotrader_configs_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not config_rows:
    raise SystemExit("No autotrader config")
config = config_rows[0]

account_rows = get_rows(
    "paper_accounts_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not account_rows:
    raise SystemExit("No paper account")
account = account_rows[0]

snapshots = get_rows(
    "paper_equity_snapshots_v13",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&order=snapshot_date.asc&limit=365",
)
signals = get_rows(
    "signals",
    "select=trade_date,total_score,trend_score,momentum_score,"
    "risk_score,confidence&order=trade_date.desc&limit=500",
)
positions = get_rows(
    "paper_positions_v13",
    f"account_name=eq.{quote(ACCOUNT)}&select=symbol,market_value&limit=1000",
)

report_date = (
    str(signals[0]["trade_date"])
    if signals
    else date.today().isoformat()
)

equity = number(account.get("equity"), number(account.get("cash")))
cash = number(account.get("cash"))
gross_exposure_value = sum(abs(number(row.get("market_value"))) for row in positions)
net_exposure_value = sum(number(row.get("market_value")) for row in positions)
gross_exposure_pct = gross_exposure_value / equity * 100 if equity else 0
net_exposure_pct = net_exposure_value / equity * 100 if equity else 0

equity_values = [number(row.get("equity")) for row in snapshots if number(row.get("equity")) > 0]
returns = []
for index in range(1, len(equity_values)):
    previous = equity_values[index - 1]
    current = equity_values[index]
    if previous > 0:
        returns.append(current / previous - 1)

window = returns[-20:]
mean_return = statistics.fmean(window) if window else 0.0
volatility = statistics.pstdev(window) if len(window) >= 2 else 0.0
sharpe = (
    mean_return / volatility * math.sqrt(252)
    if volatility > 0
    else 0.0
)

peak = 0.0
max_drawdown = 0.0
for value in equity_values:
    peak = max(peak, value)
    if peak > 0:
        max_drawdown = min(max_drawdown, value / peak - 1)

var_95 = 1.645 * volatility * equity
var_99 = 2.326 * volatility * equity
expected_shortfall_95 = 2.063 * volatility * equity

latest_date = str(signals[0]["trade_date"]) if signals else report_date
latest_signals = [row for row in signals if str(row.get("trade_date")) == latest_date]
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

if avg_score >= 60 and avg_trend >= 55 and avg_risk <= 45:
    regime = "BULL"
elif avg_score < 35 or avg_risk >= 65:
    regime = "BEAR"
elif avg_momentum < 30 and avg_trend < 40:
    regime = "DEFENSIVE"
else:
    regime = "SIDEWAYS"

strategies = {
    "TREND_FOLLOWING": {
        "expected_return": clamp(avg_trend / 100 * 0.18, 0.01, 0.18),
        "expected_volatility": clamp((avg_risk + 20) / 100 * 0.22, 0.06, 0.30),
    },
    "MOMENTUM": {
        "expected_return": clamp(avg_momentum / 100 * 0.20, 0.01, 0.20),
        "expected_volatility": clamp((avg_risk + 25) / 100 * 0.25, 0.07, 0.32),
    },
    "QUALITY_DEFENSIVE": {
        "expected_return": clamp(avg_score / 100 * 0.12, 0.01, 0.12),
        "expected_volatility": clamp((avg_risk + 5) / 100 * 0.14, 0.04, 0.18),
    },
    "CASH_BUFFER": {
        "expected_return": 0.015,
        "expected_volatility": 0.005,
    },
}

regime_bias = {
    "BULL": {
        "TREND_FOLLOWING": 1.30,
        "MOMENTUM": 1.30,
        "QUALITY_DEFENSIVE": 0.80,
        "CASH_BUFFER": 0.45,
    },
    "SIDEWAYS": {
        "TREND_FOLLOWING": 0.90,
        "MOMENTUM": 0.85,
        "QUALITY_DEFENSIVE": 1.20,
        "CASH_BUFFER": 1.00,
    },
    "DEFENSIVE": {
        "TREND_FOLLOWING": 0.60,
        "MOMENTUM": 0.55,
        "QUALITY_DEFENSIVE": 1.40,
        "CASH_BUFFER": 1.60,
    },
    "BEAR": {
        "TREND_FOLLOWING": 0.40,
        "MOMENTUM": 0.35,
        "QUALITY_DEFENSIVE": 1.25,
        "CASH_BUFFER": 2.20,
    },
}[regime]

raw_weights = {}
for name, metrics in strategies.items():
    inverse_vol = 1 / max(metrics["expected_volatility"], 0.001)
    raw_weights[name] = inverse_vol * regime_bias[name]

total_raw = sum(raw_weights.values()) or 1.0
weights = {name: value / total_raw for name, value in raw_weights.items()}

kelly_cap = number(config.get("kelly_fraction_cap"), 0.25)
for name, metrics in strategies.items():
    variance = metrics["expected_volatility"] ** 2
    kelly = (
        metrics["expected_return"] / variance
        if variance > 0
        else 0
    )
    capped = clamp(kelly_cap * kelly, 0, 1)
    weights[name] *= max(0.15, capped)

weight_total = sum(weights.values()) or 1.0
weights = {name: value / weight_total for name, value in weights.items()}

for name, weight in weights.items():
    metrics = strategies[name]
    risk_contribution = weight * metrics["expected_volatility"]
    upsert_rows(
        "hedge_fund_allocations_v19",
        {
            "account_name": ACCOUNT,
            "allocation_date": report_date,
            "strategy_name": name,
            "strategy_weight": weight * 100,
            "expected_return": metrics["expected_return"] * 100,
            "expected_volatility": metrics["expected_volatility"] * 100,
            "risk_contribution": risk_contribution * 100,
            "regime": regime,
            "allocation_reason": (
                f"Inverse-volatility allocation adjusted for {regime} "
                f"regime and capped Kelly fraction."
            ),
        },
        "account_name,allocation_date,strategy_name",
    )

var_limit_pct = number(config.get("var_limit_pct"), 3)
var_pct = var_95 / equity * 100 if equity else 0
risk_status = "PASS"
risk_message = "Portfolio risk is within configured limits."

if var_pct > var_limit_pct:
    risk_status = "REDUCE_RISK"
    risk_message = (
        f"95% daily VaR {var_pct:.2f}% exceeds limit "
        f"{var_limit_pct:.2f}%."
    )
elif max_drawdown <= -0.15:
    risk_status = "DRAWDOWN_ALERT"
    risk_message = (
        f"Maximum drawdown {max_drawdown * 100:.2f}% requires review."
    )
elif gross_exposure_pct > number(config.get("max_gross_exposure_pct"), 100):
    risk_status = "EXPOSURE_ALERT"
    risk_message = "Gross exposure exceeds configured limit."

upsert_rows(
    "risk_snapshots_v19",
    {
        "account_name": ACCOUNT,
        "snapshot_date": report_date,
        "equity": equity,
        "cash": cash,
        "gross_exposure": gross_exposure_pct,
        "net_exposure": net_exposure_pct,
        "daily_var_95": var_95,
        "daily_var_99": var_99,
        "expected_shortfall_95": expected_shortfall_95,
        "max_drawdown": max_drawdown * 100,
        "volatility_20d": volatility * math.sqrt(252) * 100,
        "sharpe_20d": sharpe,
        "risk_status": risk_status,
        "risk_message": risk_message,
    },
    "account_name,snapshot_date",
)

target_cash_pct = weights["CASH_BUFFER"] * 100
recommended_gross = min(
    number(config.get("max_gross_exposure_pct"), 100),
    100 - target_cash_pct,
)
recommended_net = min(
    number(config.get("max_net_exposure_pct"), 85),
    recommended_gross,
)

portfolio_style = (
    "AGGRESSIVE_GROWTH"
    if regime == "BULL"
    else "CAPITAL_PRESERVATION"
    if regime in {"BEAR", "DEFENSIVE"}
    else "BALANCED"
)

cro_message = (
    f"{risk_status}: VaR95 {var_pct:.2f}%, "
    f"max drawdown {max_drawdown * 100:.2f}%, "
    f"gross exposure {gross_exposure_pct:.1f}%."
)
pm_message = (
    f"Regime {regime}; allocate across "
    f"{', '.join(f'{name} {weight*100:.1f}%' for name, weight in weights.items())}."
)
execution_plan = (
    "Reduce exposure and prioritize cash/quality allocations."
    if risk_status != "PASS"
    else "Maintain risk-parity allocation and review proposed PAPER orders."
)

upsert_rows(
    "hedge_fund_reports_v19",
    {
        "account_name": ACCOUNT,
        "report_date": report_date,
        "market_regime": regime,
        "portfolio_style": portfolio_style,
        "target_cash_pct": target_cash_pct,
        "recommended_gross_exposure": recommended_gross,
        "recommended_net_exposure": recommended_net,
        "chief_risk_officer_message": cro_message,
        "portfolio_manager_message": pm_message,
        "execution_plan": execution_plan,
    },
    "account_name,report_date",
)

print(pm_message)
print(cro_message)
print(execution_plan)
# Phase 3.7.18.6 compatibility entrypoint.
#
# hedge_fund_manager_v19.py is a legacy top-level executable. Enterprise 3.0
# Stable loads this module via importlib, so the existing hedge/risk logic already
# executes during module loading. The orchestrator then requires a callable
# main(). Without main(), the stage is marked failed after V19 logic completes.
#
# This no-op main() satisfies the compatibility contract without re-running
# regime allocation, VaR / drawdown checks, hedge sizing, or PAPER order review.
def main() -> None:
    return None
