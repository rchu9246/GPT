from __future__ import annotations

import argparse
import math
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "9.3.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        parsed = float(value)
        if math.isnan(parsed) or math.isinf(parsed):
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def first_present(
    row: dict[str, Any],
    names: Iterable[str],
    default: Any = None,
) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def read(
    client: SupabaseRestClient,
    table: str,
    query: str,
    *,
    required: bool = False,
) -> list[dict[str, Any]]:
    try:
        rows = client.get(table, query)
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        if required:
            raise
        print(f"Optional source unavailable: {table}: {exc}")
        return []


def deterministic_id(*parts: Any) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join(str(part) for part in parts),
        )
    )


def extract_confidence_detail(
    status: dict[str, Any],
    ranking_id: str,
) -> dict[str, Any]:
    diagnostics = status.get("diagnostics") or {}
    details = diagnostics.get("confidence_score_details") or []
    if not isinstance(details, list):
        return {}
    for detail in details:
        if str(detail.get("ranking_id") or "") == ranking_id:
            return detail
    return {}


def extract_risk_metrics(
    ranking: dict[str, Any],
    confidence_detail: dict[str, Any],
) -> dict[str, float | None]:
    return {
        "max_drawdown": number(first_present(
            confidence_detail,
            ["drawdown", "max_drawdown"],
            first_present(
                ranking,
                ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
                None,
            ),
        )),
        "volatility": number(first_present(
            confidence_detail,
            ["volatility"],
            first_present(
                ranking,
                ["volatility", "annualized_volatility", "volatility_pct"],
                None,
            ),
        )),
        "sharpe": number(first_present(
            confidence_detail,
            ["sharpe"],
            first_present(
                ranking,
                ["sharpe_ratio", "sharpe"],
                None,
            ),
        )),
        "risk_stability": number(
            confidence_detail.get("risk_stability"),
            None,
        ),
        "data_completeness": number(
            confidence_detail.get("data_completeness"),
            None,
        ),
    }


def calculate_position(
    *,
    ranking: dict[str, Any],
    population: int,
    max_single_weight: float,
    total_risk_budget: float,
    risk_metrics: dict[str, float | None],
) -> dict[str, Any]:
    rank_no = integer(ranking.get("rank_no"), population)
    evolution = number(ranking.get("evolution_score"), 0.0) or 0.0
    confidence = number(ranking.get("confidence_score"), 0.0) or 0.0
    recommendation = str(ranking.get("recommendation") or "REJECT")
    selected = ranking.get("selected_for_review") is True

    evolution_multiplier = clamp(evolution / 100.0)
    confidence_multiplier = clamp(confidence / 100.0)

    if population <= 1:
        rank_multiplier = 1.0
    else:
        rank_multiplier = clamp(
            (population - rank_no + 1) / population,
            0.10,
            1.0,
        )

    drawdown = risk_metrics["max_drawdown"]
    if drawdown is None:
        drawdown_multiplier = 0.70
    else:
        drawdown_multiplier = clamp(
            1.0 - abs(drawdown) / 40.0,
            0.20,
            1.0,
        )

    volatility = risk_metrics["volatility"]
    if volatility is None:
        volatility_multiplier = 0.70
    else:
        volatility_multiplier = clamp(
            1.0 - abs(volatility) / 60.0,
            0.20,
            1.0,
        )

    risk_stability = risk_metrics["risk_stability"]
    if risk_stability is None:
        stability_multiplier = 0.60
    else:
        stability_multiplier = clamp(risk_stability / 100.0)

    completeness = risk_metrics["data_completeness"]
    if completeness is None:
        completeness_multiplier = 0.60
    else:
        completeness_multiplier = clamp(completeness / 100.0)

    governance_multiplier = 1.0
    blockers: list[str] = []
    warnings: list[str] = []

    if recommendation == "REJECT":
        governance_multiplier = 0.0
        blockers.append("RECOMMENDATION_REJECT")
    elif recommendation == "REVIEW_REQUIRED":
        governance_multiplier = 0.35
        warnings.append("REVIEW_REQUIRED")
    elif recommendation in {
        "PROMOTE_FOR_HUMAN_REVIEW",
        "CONFIDENCE_READY",
    }:
        governance_multiplier = 0.75

    if not selected and recommendation == "PROMOTE_FOR_HUMAN_REVIEW":
        warnings.append("NOT_SELECTED_FOR_REVIEW")

    raw_score = (
        0.26 * evolution_multiplier
        + 0.24 * confidence_multiplier
        + 0.14 * rank_multiplier
        + 0.12 * drawdown_multiplier
        + 0.08 * volatility_multiplier
        + 0.08 * stability_multiplier
        + 0.08 * completeness_multiplier
    )

    base_weight = max_single_weight * raw_score
    final_weight = (
        base_weight
        * governance_multiplier
        * total_risk_budget
    )

    if confidence < 20:
        warnings.append("VERY_LOW_CONFIDENCE")
        final_weight *= 0.25
    elif confidence < 40:
        warnings.append("LOW_CONFIDENCE")
        final_weight *= 0.50
    elif confidence < 60:
        warnings.append("CONFIDENCE_BELOW_TARGET")
        final_weight *= 0.75

    if evolution < 50:
        warnings.append("LOW_EVOLUTION_SCORE")
        final_weight *= 0.50
    elif evolution < 70:
        warnings.append("EVOLUTION_BELOW_TARGET")
        final_weight *= 0.75

    final_weight = clamp(final_weight, 0.0, max_single_weight)

    if final_weight <= 0:
        sizing_status = "BLOCKED"
    elif final_weight < max_single_weight * 0.25:
        sizing_status = "MINIMAL"
    elif final_weight < max_single_weight * 0.60:
        sizing_status = "REDUCED"
    else:
        sizing_status = "NORMAL"

    return {
        "rank_no": rank_no,
        "evolution_score": round(evolution, 4),
        "confidence_score": round(confidence, 4),
        "recommendation": recommendation,
        "selected_for_review": selected,
        "evolution_multiplier": round(evolution_multiplier, 6),
        "confidence_multiplier": round(confidence_multiplier, 6),
        "rank_multiplier": round(rank_multiplier, 6),
        "drawdown_multiplier": round(drawdown_multiplier, 6),
        "volatility_multiplier": round(volatility_multiplier, 6),
        "stability_multiplier": round(stability_multiplier, 6),
        "completeness_multiplier": round(completeness_multiplier, 6),
        "governance_multiplier": round(governance_multiplier, 6),
        "raw_score": round(raw_score, 6),
        "base_weight": round(base_weight, 6),
        "final_position_size": round(final_weight, 6),
        "sizing_status": sizing_status,
        "blockers": blockers,
        "warnings": warnings,
        "risk_metrics": risk_metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GPT Quant V9 Position Sizing Engine v1.0"
    )
    parser.add_argument("--ranking-id", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--max-single-weight",
        type=float,
        default=0.10,
    )
    parser.add_argument(
        "--total-risk-budget",
        type=float,
        default=1.00,
    )
    args = parser.parse_args()

    if not 0 < args.max_single_weight <= 0.25:
        raise ValueError(
            "max-single-weight must be greater than 0 and <= 0.25"
        )
    if not 0 < args.total_risk_budget <= 1.0:
        raise ValueError(
            "total-risk-budget must be greater than 0 and <= 1.0"
        )

    client = SupabaseRestClient()

    ranking_query = (
        f"id=eq.{args.ranking_id}&limit=1"
        if args.ranking_id
        else f"order=ranking_date.desc,rank_no.asc&limit={args.limit}"
    )

    rankings = read(
        client,
        "portfolio_rankings_v56",
        ranking_query,
        required=True,
    )
    if not rankings:
        raise RuntimeError("No portfolio_rankings_v56 rows found.")

    status_rows = read(
        client,
        "evolution_status_v56",
        "order=status_date.desc&limit=1",
        required=True,
    )
    if not status_rows:
        raise RuntimeError("evolution_status_v56 is empty.")
    status = status_rows[0]

    population = len(rankings)
    results: list[dict[str, Any]] = []

    for ranking in rankings:
        ranking_id = str(ranking["id"])
        source_version_no = str(first_present(
            ranking,
            ["source_version_no", "version_no"],
            f"UNKNOWN-{ranking_id[:8]}",
        ))

        confidence_detail = extract_confidence_detail(
            status,
            ranking_id,
        )
        risk_metrics = extract_risk_metrics(
            ranking,
            confidence_detail,
        )

        result = calculate_position(
            ranking=ranking,
            population=population,
            max_single_weight=args.max_single_weight,
            total_risk_budget=args.total_risk_budget,
            risk_metrics=risk_metrics,
        )

        result_id = deterministic_id(
            "gpt-quant-v9-position-sizing",
            RUN_DATE,
            ranking_id,
        )

        client.upsert(
            "gpt_quant_v9_position_sizing_results",
            {
                "id": result_id,
                "sizing_date": RUN_DATE,
                "ranking_id": ranking_id,
                "source_version_no": source_version_no,
                "rank_no": result["rank_no"],
                "evolution_score": result["evolution_score"],
                "confidence_score": result["confidence_score"],
                "recommendation": result["recommendation"],
                "selected_for_review": result["selected_for_review"],
                "max_single_weight": args.max_single_weight,
                "total_risk_budget": args.total_risk_budget,
                "raw_score": result["raw_score"],
                "base_weight": result["base_weight"],
                "final_position_size": result["final_position_size"],
                "sizing_status": result["sizing_status"],
                "blockers": result["blockers"],
                "warnings": result["warnings"],
                "components": {
                    "evolution_multiplier": result["evolution_multiplier"],
                    "confidence_multiplier": result["confidence_multiplier"],
                    "rank_multiplier": result["rank_multiplier"],
                    "drawdown_multiplier": result["drawdown_multiplier"],
                    "volatility_multiplier": result["volatility_multiplier"],
                    "stability_multiplier": result["stability_multiplier"],
                    "completeness_multiplier": result[
                        "completeness_multiplier"
                    ],
                    "governance_multiplier": result[
                        "governance_multiplier"
                    ],
                },
                "risk_metrics": result["risk_metrics"],
                "paper_only": True,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
                "engine_version": ENGINE_VERSION,
                "calculated_at": now(),
            },
            "sizing_date,ranking_id",
        )

        results.append({
            "ranking_id": ranking_id,
            "source_version_no": source_version_no,
            **result,
        })

        print(
            f"{source_version_no}: "
            f"position={result['final_position_size']:.4%}, "
            f"status={result['sizing_status']}"
        )

    diagnostics = status.get("diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    status_filter = (
        f"id=eq.{status['id']}"
        if status.get("id") is not None
        else f"status_date=eq.{status['status_date']}"
    )

    client.patch(
        "evolution_status_v56",
        status_filter,
        {
            "overall_status": status.get("overall_status") or "WARNING",
            "diagnostics": {
                **diagnostics,
                "gpt_quant_v9_position_sizing_engine_version": ENGINE_VERSION,
                "position_sizing_results": results,
                "position_sizing_max_single_weight": (
                    args.max_single_weight
                ),
                "position_sizing_total_risk_budget": (
                    args.total_risk_budget
                ),
                "position_sizing_updated_at": now(),
                "position_sizing_paper_only": True,
                "position_sizing_live_trading_enabled": False,
            },
        },
    )

    print(
        f"GPT Quant V9 Position Sizing complete: "
        f"results={len(results)}"
    )
    print("Paper only: true")
    print("Live trading: false")
    print("Broker submission: false")


if __name__ == "__main__":
    main()
