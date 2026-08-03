from __future__ import annotations

import math
import os
from datetime import date
from statistics import mean, pstdev
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())


def n(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def latest(
    client: SupabaseRestClient,
    table: str,
    field: str,
    where: str = "",
) -> dict[str, Any]:
    query = (
        f"{where}&order={field}.desc&limit=1"
        if where
        else f"order={field}.desc&limit=1"
    )
    rows = client.get(table, query)
    return rows[0] if rows else {}


def safe_get(
    client: SupabaseRestClient,
    table: str,
    query: str,
) -> list[dict[str, Any]]:
    try:
        rows = client.get(table, query)
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        print(f"Optional source unavailable: {table}: {exc}")
        return []


def classify_regime(
    trend_score: float,
    volatility_score: float,
    stress_score: float,
    recovery_score: float,
    benchmark_return: float,
) -> tuple[str, str, str]:
    if stress_score >= 80 and benchmark_return <= -3:
        return "CRASH", "RISK_OFF", "CAPITAL_PRESERVATION"

    if recovery_score >= 70 and benchmark_return > 0:
        return "RECOVERY", "EARLY_TRANSITION", "NEUTRAL"

    if trend_score >= 70 and benchmark_return >= 2:
        return "TRENDING_UP", "STABLE", "RISK_ON"

    if trend_score <= 30 and benchmark_return <= -2:
        return "TRENDING_DOWN", "STABLE", "DEFENSIVE"

    if volatility_score >= 75 and abs(benchmark_return) < 2:
        return "HIGH_VOLATILITY", "REVERSAL_RISK", "RISK_OFF"

    if trend_score >= 60 and volatility_score >= 60:
        return "BREAKOUT", "CONFIRMED_TRANSITION", "RISK_ON"

    if volatility_score >= 55:
        return "CHOPPY", "STABLE", "DEFENSIVE"

    if volatility_score <= 30 and abs(benchmark_return) < 1:
        return "LOW_VOLATILITY", "STABLE", "NEUTRAL"

    return "SIDEWAYS", "STABLE", "NEUTRAL"


def main() -> None:
    client = SupabaseRestClient()

    performance_rows = safe_get(
        client,
        "performance_daily_v46",
        "order=performance_date.asc&limit=500",
    )
    base_regime = latest(client, "market_regime_v46", "regime_date")
    risk_status = latest(client, "risk_governor_status_v41", "status_date")
    portfolio_health = safe_get(
        client,
        "portfolio_health_v46",
        f"health_date=eq.{RUN_DATE}&limit=100",
    )

    returns = [
        n(row.get("daily_return_pct"))
        for row in performance_rows
    ]
    recent_returns = returns[-20:]
    shorter_returns = returns[-5:]

    benchmark_return = sum(recent_returns)
    short_return = sum(shorter_returns)

    realized_volatility = (
        pstdev(recent_returns) * math.sqrt(252)
        if len(recent_returns) >= 2
        else n(base_regime.get("realized_volatility_pct"))
    )

    trend_score = clamp(
        50
        + benchmark_return * 6
        + short_return * 4
    )

    volatility_score = clamp(
        realized_volatility * 2.5
    )

    average_health = (
        mean([n(row.get("health_score"), 50) for row in portfolio_health])
        if portfolio_health
        else 50
    )

    risk_score = n(risk_status.get("overall_risk_score"))
    active_breakers = int(n(risk_status.get("active_breakers")))
    critical_events = int(n(risk_status.get("open_critical_events")))

    stress_score = clamp(
        risk_score * 0.65
        + max(0, 65 - average_health) * 1.2
        + active_breakers * 15
        + critical_events * 10
    )

    previous_rows = safe_get(
        client,
        "market_regime_ai_v46",
        f"regime_date=lt.{RUN_DATE}&order=regime_date.desc&limit=5",
    )
    previous_stress = (
        mean([n(row.get("stress_score")) for row in previous_rows])
        if previous_rows
        else stress_score
    )

    recovery_score = clamp(
        max(0, previous_stress - stress_score) * 2
        + max(0, short_return) * 10
        + max(0, average_health - 50)
    )

    breadth_score = clamp(
        n(base_regime.get("breadth_score"), 50)
    )
    liquidity_score = clamp(
        n(base_regime.get("liquidity_score"), average_health)
    )

    market_regime, transition_state, posture = classify_regime(
        trend_score=trend_score,
        volatility_score=volatility_score,
        stress_score=stress_score,
        recovery_score=recovery_score,
        benchmark_return=benchmark_return,
    )

    if trend_score >= 60:
        trend_state = "UP"
    elif trend_score <= 40:
        trend_state = "DOWN"
    else:
        trend_state = "FLAT"

    if volatility_score >= 70:
        volatility_state = "HIGH"
    elif volatility_score <= 30:
        volatility_state = "LOW"
    else:
        volatility_state = "NORMAL"

    liquidity_state = (
        "STRONG" if liquidity_score >= 70
        else "WEAK" if liquidity_score <= 35
        else "NORMAL"
    )
    breadth_state = (
        "BROAD" if breadth_score >= 65
        else "NARROW" if breadth_score <= 35
        else "MIXED"
    )
    risk_state = (
        "CRITICAL" if stress_score >= 80
        else "ELEVATED" if stress_score >= 55
        else "NORMAL"
    )

    preferred: list[str]
    avoided: list[str]

    if market_regime in ("TRENDING_UP", "BREAKOUT"):
        preferred = ["TREND_FOLLOWING", "MOMENTUM"]
        avoided = ["SHORT_BIAS", "AGGRESSIVE_MEAN_REVERSION"]
    elif market_regime in ("CRASH", "TRENDING_DOWN"):
        preferred = ["DEFENSIVE", "CASH", "LOW_VOLATILITY"]
        avoided = ["LEVERAGED_LONG", "HIGH_BETA"]
    elif market_regime == "RECOVERY":
        preferred = ["QUALITY", "MOMENTUM", "RECOVERY"]
        avoided = ["MAX_DEFENSIVE"]
    else:
        preferred = ["MEAN_REVERSION", "MARKET_NEUTRAL", "LOW_TURNOVER"]
        avoided = ["LEVERAGED_TREND"]

    confidence = clamp(
        50
        + abs(trend_score - 50) * 0.55
        + abs(volatility_score - 50) * 0.20
        + abs(stress_score - 50) * 0.20
    )

    rationale = (
        f"Regime {market_regime}; 20-period return "
        f"{benchmark_return:.2f}%, volatility score "
        f"{volatility_score:.1f}, stress score "
        f"{stress_score:.1f}, portfolio health "
        f"{average_health:.1f}."
    )

    client.upsert(
        "market_regime_ai_v46",
        {
            "regime_date": RUN_DATE,
            "market_regime": market_regime,
            "trend_state": trend_state,
            "volatility_state": volatility_state,
            "liquidity_state": liquidity_state,
            "breadth_state": breadth_state,
            "risk_state": risk_state,
            "transition_state": transition_state,
            "regime_confidence": confidence,
            "trend_score": trend_score,
            "volatility_score": volatility_score,
            "liquidity_score": liquidity_score,
            "breadth_score": breadth_score,
            "stress_score": stress_score,
            "recovery_score": recovery_score,
            "recommended_posture": posture,
            "preferred_strategy_styles": preferred,
            "avoided_strategy_styles": avoided,
            "rationale": rationale,
            "features": {
                "benchmark_return_pct": benchmark_return,
                "short_return_pct": short_return,
                "realized_volatility_pct": realized_volatility,
                "average_portfolio_health": average_health,
                "risk_governor_score": risk_score,
            },
            "evidence": {
                "performance_samples": len(recent_returns),
                "portfolio_health_samples": len(portfolio_health),
                "active_breakers": active_breakers,
                "critical_events": critical_events,
                "base_regime_v46": base_regime.get("market_regime"),
                "engine_version": "4.6.5",
            },
        },
        "regime_date",
    )

    print(
        f"Enterprise 4.6.5 Market Regime AI: {market_regime}; "
        f"confidence {confidence:.1f}%; posture {posture}."
    )


if __name__ == "__main__":
    main()
