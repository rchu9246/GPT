from __future__ import annotations

import math
import os
from datetime import date
from statistics import mean
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


def json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def score_regime_fit(
    market_regime: str,
    preferred: list[str],
    avoided: list[str],
) -> float:
    if market_regime in preferred:
        return 95.0
    if market_regime in avoided:
        return 15.0
    if market_regime == "UNKNOWN":
        return 45.0
    return 60.0


def score_performance(
    analytics: dict[str, Any],
    rating: dict[str, Any],
) -> float:
    edge = n(analytics.get("edge_score"), 50)
    stability = n(analytics.get("stability_score"), 50)
    consistency = n(analytics.get("consistency_score"), 50)
    overall = n(rating.get("overall_score"), 50)
    accuracy = n(rating.get("prediction_accuracy"), 50)

    return clamp(
        edge * 0.30
        + stability * 0.20
        + consistency * 0.15
        + overall * 0.20
        + accuracy * 0.15
    )


def score_learning(
    analytics: dict[str, Any],
    rating: dict[str, Any],
) -> float:
    speed = n(analytics.get("learning_speed"), 0)
    calibration = n(rating.get("calibration_score"), 50)
    sample_count = int(n(rating.get("sample_count"), 0))
    sample_score = clamp(sample_count * 5)

    return clamp(
        speed * 0.35
        + calibration * 0.35
        + sample_score * 0.30
    )


def score_risk(
    catalog: dict[str, Any],
    portfolio_health: dict[str, Any],
    risk_status: dict[str, Any],
) -> float:
    base_risk = n(catalog.get("base_risk_score"), 50)
    portfolio_risk_quality = n(portfolio_health.get("risk_score"), 50)
    overall_risk = n(risk_status.get("overall_risk_score"), 0)
    active_breakers = int(n(risk_status.get("active_breakers"), 0))
    critical_events = int(n(risk_status.get("open_critical_events"), 0))

    score = (
        (100 - base_risk) * 0.35
        + portfolio_risk_quality * 0.40
        + (100 - overall_risk) * 0.25
        - active_breakers * 20
        - critical_events * 10
    )
    return clamp(score)


def main() -> None:
    client = SupabaseRestClient()

    portfolios = client.get(
        "enterprise_portfolios_v40",
        "lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100",
    )
    catalog = client.get(
        "strategy_catalog_v47",
        "enabled=eq.true&paper_approved=eq.true&live_approved=eq.false"
        "&order=priority.asc&limit=100",
    )
    regime_row = latest(client, "market_regime_ai_v46", "regime_date")
    risk_status = latest(client, "risk_governor_status_v41", "status_date")
    analytics_rows = safe_get(
        client,
        "strategy_analytics_v46",
        "order=analytics_date.desc&limit=1000",
    )
    rating_rows = safe_get(
        client,
        "strategy_rating_v45",
        "order=rating_date.desc&limit=1000",
    )

    market_regime = str(regime_row.get("market_regime") or "UNKNOWN")
    regime_confidence = n(regime_row.get("regime_confidence"), 50)
    preferred_styles = json_list(regime_row.get("preferred_strategy_styles"))
    avoided_styles = json_list(regime_row.get("avoided_strategy_styles"))

    latest_analytics: dict[str, dict[str, Any]] = {}
    for row in analytics_rows:
        key = str(row.get("strategy_key") or "")
        if key and key not in latest_analytics:
            latest_analytics[key] = row

    latest_ratings: dict[str, dict[str, Any]] = {}
    for row in rating_rows:
        key = str(row.get("strategy_key") or "")
        if key and key not in latest_ratings:
            latest_ratings[key] = row

    total_scores = 0
    critical_findings = 0
    warning_findings = 0
    all_composite_scores: list[float] = []
    all_confidence_scores: list[float] = []

    for portfolio in portfolios:
        portfolio_id = str(portfolio["id"])
        health = latest(
            client,
            "portfolio_health_v46",
            "health_date",
            f"portfolio_id=eq.{portfolio_id}",
        )

        scored_rows: list[dict[str, Any]] = []

        for item in catalog:
            strategy_key = str(item["strategy_key"])
            analytics = latest_analytics.get(strategy_key, {})
            rating = latest_ratings.get(strategy_key, {})

            preferred_regimes = json_list(item.get("preferred_regimes"))
            avoided_regimes = json_list(item.get("avoided_regimes"))

            regime_fit = score_regime_fit(
                market_regime,
                preferred_regimes,
                avoided_regimes,
            )

            style = str(item.get("strategy_family") or "")
            if style in preferred_styles:
                regime_fit = clamp(regime_fit + 10)
            if style in avoided_styles:
                regime_fit = clamp(regime_fit - 20)

            performance_score = score_performance(analytics, rating)
            learning_score = score_learning(analytics, rating)
            risk_score = score_risk(item, health, risk_status)
            stability_score = n(analytics.get("stability_score"), 50)
            liquidity_score = n(health.get("liquidity_score"), 50)
            diversification_score = n(
                health.get("diversification_score"),
                50,
            )

            confidence_score = clamp(
                regime_confidence * 0.35
                + performance_score * 0.25
                + learning_score * 0.20
                + stability_score * 0.20
            )

            composite_score = clamp(
                performance_score * 0.25
                + risk_score * 0.20
                + regime_fit * 0.25
                + learning_score * 0.10
                + stability_score * 0.08
                + liquidity_score * 0.06
                + diversification_score * 0.06
            )

            disqualifications: list[str] = []
            if int(n(risk_status.get("active_breakers"))) > 0:
                if strategy_key not in ("DEFENSIVE", "CASH"):
                    disqualifications.append("ACTIVE_CIRCUIT_BREAKER")
            if market_regime == "CRASH":
                if strategy_key not in ("DEFENSIVE", "CASH"):
                    disqualifications.append("CRASH_REGIME")
            if market_regime in avoided_regimes:
                disqualifications.append("AVOIDED_MARKET_REGIME")
            if str(item.get("default_risk_level")) == "HIGH":
                if n(health.get("health_score"), 50) < 50:
                    disqualifications.append(
                        "PORTFOLIO_HEALTH_TOO_LOW_FOR_HIGH_RISK"
                    )

            eligible = not disqualifications

            scored_rows.append(
                {
                    "score_date": RUN_DATE,
                    "portfolio_id": portfolio_id,
                    "strategy_catalog_id": item["id"],
                    "strategy_key": strategy_key,
                    "market_regime": market_regime,
                    "performance_score": performance_score,
                    "risk_score": risk_score,
                    "regime_fit_score": regime_fit,
                    "learning_score": learning_score,
                    "stability_score": stability_score,
                    "liquidity_score": liquidity_score,
                    "diversification_score": diversification_score,
                    "confidence_score": confidence_score,
                    "composite_score": composite_score,
                    "rank": 0,
                    "eligible": eligible,
                    "disqualification_reasons": disqualifications,
                    "diagnostics": {
                        "market_regime_confidence": regime_confidence,
                        "portfolio_health_status": health.get(
                            "health_status"
                        ),
                        "source_strategy_analytics_v46": bool(analytics),
                        "source_strategy_rating_v45": bool(rating),
                        "engine_version": "4.7.1",
                    },
                }
            )

        scored_rows.sort(
            key=lambda row: (
                not bool(row["eligible"]),
                -float(row["composite_score"]),
                -float(row["confidence_score"]),
            )
        )

        for rank, row in enumerate(scored_rows, start=1):
            row["rank"] = rank
            client.upsert(
                "strategy_scores_v47",
                row,
                "score_date,portfolio_id,strategy_key",
            )
            total_scores += 1
            all_composite_scores.append(float(row["composite_score"]))
            all_confidence_scores.append(float(row["confidence_score"]))

            if not row["eligible"]:
                warning_findings += 1
            if (
                row["strategy_key"] == "CASH"
                and row["rank"] == 1
                and market_regime == "CRASH"
            ):
                critical_findings += 1

    eligible_rows = safe_get(
        client,
        "strategy_scores_v47",
        f"score_date=eq.{RUN_DATE}&eligible=eq.true&limit=1000",
    )
    if not eligible_rows:
        critical_findings += 1

    if critical_findings > 0:
        overall_status = "CRITICAL"
    elif warning_findings > 0 or not portfolios or not catalog:
        overall_status = "WARNING"
    else:
        overall_status = "PASS"

    summary = (
        f"Scored {total_scores} portfolio-strategy combination(s) "
        f"for {len(portfolios)} portfolio(s) across "
        f"{len(catalog)} catalog strategy(s); regime "
        f"{market_regime}."
    )

    client.upsert(
        "strategy_engine_status_v47",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "market_regime": market_regime,
            "portfolios_processed": len(portfolios),
            "strategies_scored": total_scores,
            "recommendations_generated": 0,
            "backtests_processed": 0,
            "selections_created": 0,
            "average_confidence": (
                mean(all_confidence_scores)
                if all_confidence_scores
                else 0
            ),
            "average_composite_score": (
                mean(all_composite_scores)
                if all_composite_scores
                else 0
            ),
            "critical_findings": critical_findings,
            "warning_findings": warning_findings,
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
            "paper_mode_enabled": True,
            "blockers": (
                ["NO_ELIGIBLE_STRATEGIES"]
                if not eligible_rows
                else []
            ),
            "highlights": [
                f"Market regime: {market_regime}",
                f"Strategies scored: {total_scores}",
                f"Eligible scores: {len(eligible_rows)}",
            ],
            "summary": summary,
            "diagnostics": {
                "engine_version": "4.7.1",
                "market_regime_confidence": regime_confidence,
                "catalog_size": len(catalog),
            },
        },
        "status_date",
    )

    print(summary)
    print(f"Enterprise 4.7.1 Strategy Scoring status: {overall_status}")


if __name__ == "__main__":
    main()
