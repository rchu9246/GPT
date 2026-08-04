from __future__ import annotations

import argparse
import math
import os
from datetime import date, datetime, timezone
from statistics import mean, pstdev
from typing import Any, Iterable

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "9.2.0"


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


def boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {
        "true", "t", "1", "yes", "y",
        "pass", "passed", "success", "completed", "ready",
    }


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
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


def pass_rate(
    rows: list[dict[str, Any]],
    *,
    status_fields: tuple[str, ...],
    boolean_fields: tuple[str, ...],
) -> float | None:
    if not rows:
        return None

    passed = 0
    for row in rows:
        is_pass = any(
            boolean(row.get(field))
            for field in boolean_fields
            if field in row
        )
        if not is_pass:
            is_pass = any(
                str(row.get(field) or "").upper()
                in {"PASS", "PASSED", "SUCCESS", "COMPLETED", "READY"}
                for field in status_fields
                if field in row
            )
        passed += 1 if is_pass else 0

    return passed / len(rows)


def normalize_dispersion(values: list[float]) -> float:
    if len(values) <= 1:
        return 50.0
    mu = mean(values)
    if abs(mu) <= 1e-9:
        return 40.0
    cv = abs(pstdev(values) / mu)
    return clamp(100.0 - cv * 120.0)


def normalize_drawdown(value: float | None) -> float:
    if value is None:
        return 55.0
    return clamp(105.0 - abs(value) * 2.0)


def normalize_volatility(value: float | None) -> float:
    if value is None:
        return 55.0
    return clamp(100.0 - abs(value) * 2.0)


def normalize_sharpe(value: float | None) -> float:
    if value is None:
        return 55.0
    return clamp(30.0 + value * 30.0)


def data_completeness(
    values: dict[str, Any],
) -> tuple[float, dict[str, bool]]:
    missing = {
        key: value is None
        for key, value in values.items()
    }
    completeness = clamp(
        100.0
        * sum(1 for flag in missing.values() if not flag)
        / max(1, len(missing))
    )
    return completeness, missing


def extract_candidate_metrics(
    ranking: dict[str, Any],
    version: dict[str, Any],
    simulations: list[dict[str, Any]],
    stress_tests: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    merged.update(version)
    merged.update(ranking)

    latest_sim = simulations[0] if simulations else {}

    sharpe = number(first_present(
        merged,
        ["sharpe_ratio", "sharpe", "risk_adjusted_return"],
        first_present(latest_sim, ["sharpe_ratio", "sharpe"], None),
    ))
    sortino = number(first_present(
        merged,
        ["sortino_ratio", "sortino"],
        first_present(latest_sim, ["sortino_ratio", "sortino"], None),
    ))
    drawdown = number(first_present(
        merged,
        ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
        first_present(
            latest_sim,
            ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
            None,
        ),
    ))
    volatility = number(first_present(
        merged,
        ["volatility", "annualized_volatility", "volatility_pct"],
        first_present(
            latest_sim,
            ["volatility", "annualized_volatility"],
            None,
        ),
    ))
    win_rate = number(first_present(
        merged,
        ["win_rate", "winning_rate", "hit_rate"],
        first_present(latest_sim, ["win_rate", "winning_rate"], None),
    ))
    profit_factor = number(first_present(
        merged,
        ["profit_factor", "payoff_ratio"],
        first_present(latest_sim, ["profit_factor", "payoff_ratio"], None),
    ))

    simulation_returns = [
        value
        for row in simulations
        for value in [
            number(first_present(
                row,
                ["total_return", "return_pct", "annual_return", "cagr"],
                None,
            ))
        ]
        if value is not None
    ]

    regime_scores = [
        value
        for row in regime_rows
        for value in [
            number(first_present(
                row,
                [
                    "confidence_score",
                    "regime_score",
                    "stability_score",
                    "performance_score",
                ],
                None,
            ))
        ]
        if value is not None
    ]

    simulation_rate = pass_rate(
        simulations,
        status_fields=("status", "simulation_status"),
        boolean_fields=("passed", "success", "simulation_passed"),
    )
    stress_rate = pass_rate(
        stress_tests,
        status_fields=("status", "stress_status"),
        boolean_fields=("passed", "success", "stress_passed"),
    )

    walk_forward_rate = pass_rate(
        simulations,
        status_fields=(
            "walk_forward_status",
            "validation_status",
            "oos_status",
        ),
        boolean_fields=(
            "walk_forward_passed",
            "validation_passed",
            "out_of_sample_passed",
        ),
    )

    regime_consistency = (
        mean(regime_scores)
        if regime_scores
        else None
    )

    values_for_completeness = {
        "sharpe": sharpe,
        "sortino": sortino,
        "drawdown": drawdown,
        "volatility": volatility,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "simulation_rate": simulation_rate,
        "stress_rate": stress_rate,
        "walk_forward_rate": walk_forward_rate,
        "regime_consistency": regime_consistency,
    }
    completeness, missing_flags = data_completeness(
        values_for_completeness
    )

    return {
        "sharpe": sharpe,
        "sortino": sortino,
        "drawdown": drawdown,
        "volatility": volatility,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "simulation_rate": simulation_rate,
        "stress_rate": stress_rate,
        "walk_forward_rate": walk_forward_rate,
        "regime_consistency": regime_consistency,
        "simulation_return_dispersion": normalize_dispersion(
            simulation_returns
        ),
        "simulation_count": len(simulations),
        "stress_count": len(stress_tests),
        "regime_count": len(regime_rows),
        "data_completeness": completeness,
        "missing_flags": missing_flags,
        "previous_confidence": number(
            ranking.get("confidence_score"),
            50.0,
        ) or 50.0,
    }


def calculate_confidence(
    metrics: dict[str, Any],
) -> dict[str, Any]:
    simulation_component = (
        50.0
        if metrics["simulation_rate"] is None
        else metrics["simulation_rate"] * 100.0
    )
    stress_component = (
        50.0
        if metrics["stress_rate"] is None
        else metrics["stress_rate"] * 100.0
    )
    walk_forward_component = (
        50.0
        if metrics["walk_forward_rate"] is None
        else metrics["walk_forward_rate"] * 100.0
    )
    regime_component = (
        50.0
        if metrics["regime_consistency"] is None
        else clamp(metrics["regime_consistency"])
    )

    risk_stability = clamp(
        0.35 * normalize_drawdown(metrics["drawdown"])
        + 0.25 * normalize_volatility(metrics["volatility"])
        + 0.25 * normalize_sharpe(metrics["sharpe"])
        + 0.15 * normalize_sharpe(metrics["sortino"])
    )

    evidence_density = clamp(
        (
            metrics["simulation_count"]
            + metrics["stress_count"]
            + metrics["regime_count"]
        ) * 7.5
    )

    evidence_consistency = clamp(
        0.25 * simulation_component
        + 0.20 * stress_component
        + 0.20 * walk_forward_component
        + 0.15 * regime_component
        + 0.20 * metrics["simulation_return_dispersion"]
    )

    uncertainty_penalty = 0.0
    if metrics["data_completeness"] < 40:
        uncertainty_penalty += 15.0
    elif metrics["data_completeness"] < 70:
        uncertainty_penalty += 6.0

    if metrics["simulation_count"] == 0:
        uncertainty_penalty += 6.0
    if metrics["stress_count"] == 0:
        uncertainty_penalty += 6.0
    if metrics["walk_forward_rate"] is None:
        uncertainty_penalty += 5.0
    if metrics["regime_consistency"] is None:
        uncertainty_penalty += 4.0

    confidence_score = clamp(
        0.32 * evidence_consistency
        + 0.22 * risk_stability
        + 0.16 * evidence_density
        + 0.15 * metrics["data_completeness"]
        + 0.15 * metrics["previous_confidence"]
        - uncertainty_penalty
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if confidence_score < 40:
        blockers.append("CONFIDENCE_BELOW_40")
    elif confidence_score < 60:
        warnings.append("CONFIDENCE_BELOW_60")

    if simulation_component < 60:
        blockers.append("SIMULATION_PASS_RATE_BELOW_60")
    if stress_component < 60:
        blockers.append("STRESS_PASS_RATE_BELOW_60")
    if walk_forward_component < 55:
        blockers.append("WALK_FORWARD_BELOW_55")
    if metrics["data_completeness"] < 40:
        blockers.append("DATA_COMPLETENESS_BELOW_40")

    if metrics["regime_consistency"] is None:
        warnings.append("REGIME_EVIDENCE_MISSING")
    elif regime_component < 55:
        warnings.append("REGIME_CONSISTENCY_BELOW_55")

    if not blockers and confidence_score >= 60:
        recommendation = "CONFIDENCE_READY"
    elif confidence_score >= 45:
        recommendation = "CONFIDENCE_REVIEW_REQUIRED"
    else:
        recommendation = "CONFIDENCE_REJECT"

    return {
        "confidence_score": round(confidence_score, 4),
        "simulation_component": round(simulation_component, 4),
        "stress_component": round(stress_component, 4),
        "walk_forward_component": round(
            walk_forward_component,
            4,
        ),
        "regime_component": round(regime_component, 4),
        "risk_stability": round(risk_stability, 4),
        "evidence_density": round(evidence_density, 4),
        "evidence_consistency": round(evidence_consistency, 4),
        "uncertainty_penalty": round(uncertainty_penalty, 4),
        "blockers": blockers,
        "warnings": warnings,
        "confidence_recommendation": recommendation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GPT Quant V9 Confidence Engine v2.0"
    )
    parser.add_argument("--ranking-id", default="")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

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

    diagnostics: list[dict[str, Any]] = []
    updated = 0

    for ranking in rankings:
        ranking_id = str(ranking["id"])
        version_id = ranking.get("version_id")
        source_version_no = str(
            first_present(
                ranking,
                ["version_no", "source_version_no"],
                f"UNKNOWN-{ranking_id[:8]}",
            )
        )

        version_rows: list[dict[str, Any]] = []
        if version_id:
            version_rows = read(
                client,
                "portfolio_versions_v56",
                f"id=eq.{version_id}&limit=1",
            )
        if not version_rows:
            version_rows = read(
                client,
                "portfolio_versions_v56",
                f"version_no=eq.{source_version_no}&limit=1",
            )
        version = version_rows[0] if version_rows else {}

        simulations: list[dict[str, Any]] = []
        for table in (
            "simulation_runs_v56",
            "simulation_results_v56",
        ):
            query = (
                f"version_id=eq.{version_id}"
                "&order=created_at.desc&limit=100"
                if version_id
                else "order=created_at.desc&limit=100"
            )
            simulations = read(client, table, query)
            if simulations:
                break

        stress_query = (
            f"version_id=eq.{version_id}"
            "&order=created_at.desc&limit=100"
            if version_id
            else "order=created_at.desc&limit=100"
        )
        stress_tests = read(
            client,
            "stress_tests_v56",
            stress_query,
        )

        regime_rows: list[dict[str, Any]] = []
        for table in (
            "market_regime_results_v56",
            "market_regime_scores_v56",
            "market_regime_history",
        ):
            query = (
                f"version_id=eq.{version_id}"
                "&order=created_at.desc&limit=100"
                if version_id
                else "order=created_at.desc&limit=100"
            )
            regime_rows = read(client, table, query)
            if regime_rows:
                break

        metrics = extract_candidate_metrics(
            ranking,
            version,
            simulations,
            stress_tests,
            regime_rows,
        )
        result = calculate_confidence(metrics)

        metadata = ranking.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        client.patch(
            "portfolio_rankings_v56",
            f"id=eq.{ranking_id}",
            {
                "confidence_score": result["confidence_score"],
                "metadata": {
                    **metadata,
                    "confidence_engine_version": ENGINE_VERSION,
                    "confidence_components": {
                        key: value
                        for key, value in result.items()
                        if key not in {
                            "confidence_score",
                            "blockers",
                            "warnings",
                            "confidence_recommendation",
                        }
                    },
                    "confidence_blockers": result["blockers"],
                    "confidence_warnings": result["warnings"],
                    "confidence_recommendation": (
                        result["confidence_recommendation"]
                    ),
                    "confidence_metrics": metrics,
                    "confidence_updated_at": now(),
                },
            },
        )

        diagnostics.append({
            "ranking_id": ranking_id,
            "source_version_no": source_version_no,
            "rank_no": integer(ranking.get("rank_no"), 999),
            **metrics,
            **result,
        })
        updated += 1

        print(
            f"{source_version_no}: "
            f"confidence={result['confidence_score']:.2f}, "
            f"recommendation={result['confidence_recommendation']}"
        )

    status_rows = read(
        client,
        "evolution_status_v56",
        f"status_date=eq.{RUN_DATE}&limit=1",
    )
    if status_rows:
        status = status_rows[0]
        existing = status.get("diagnostics") or {}
        if not isinstance(existing, dict):
            existing = {}

        client.patch(
            "evolution_status_v56",
            f"status_date=eq.{RUN_DATE}",
            {
                "overall_status": status.get("overall_status") or "WARNING",
                "diagnostics": {
                    **existing,
                    "gpt_quant_v9_confidence_engine_version": ENGINE_VERSION,
                    "confidence_rankings_updated": updated,
                    "average_confidence_score": round(
                        mean(
                            row["confidence_score"]
                            for row in diagnostics
                        ),
                        4,
                    ),
                    "confidence_score_details": diagnostics,
                    "confidence_updated_at": now(),
                },
            },
        )

    print(
        f"GPT Quant V9 Confidence Engine complete: "
        f"updated={updated}"
    )
    print("Automatic promotion: false")
    print("Live trading: false")
    print("Broker submission: false")


if __name__ == "__main__":
    main()
