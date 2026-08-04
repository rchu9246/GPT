from __future__ import annotations

import argparse
import math
import os
from datetime import date, datetime, timezone
from statistics import mean, pstdev
from typing import Any, Iterable

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.6.3"


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
        "true", "t", "1", "yes", "y", "pass", "passed",
        "success", "completed", "ready",
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


def rank_percentile(rank_no: int, population: int) -> float:
    if population <= 1:
        return 100.0
    return clamp(
        100.0 * (population - rank_no) / max(1, population - 1)
    )


def zscore_percentile(value: float, values: list[float]) -> float:
    if len(values) <= 1:
        return 50.0
    sigma = pstdev(values)
    if sigma <= 1e-9:
        return 50.0
    z = (value - mean(values)) / sigma
    # Smooth normal-like mapping without scipy.
    return clamp(50.0 + 22.0 * z)


def normalize_return(value: float) -> float:
    return clamp(40.0 + value * 2.0)


def normalize_sharpe(value: float) -> float:
    return clamp(30.0 + value * 30.0)


def normalize_drawdown(value: float) -> float:
    return clamp(105.0 - abs(value) * 2.0)


def normalize_win_rate(value: float) -> float:
    rate = value * 100.0 if 0 <= value <= 1 else value
    return clamp(rate * 2.0 - 40.0)


def normalize_profit_factor(value: float) -> float:
    return clamp(40.0 + (value - 1.0) * 50.0)


def value_or_neutral(
    value: float | None,
    neutral: float,
) -> tuple[float, bool]:
    if value is None:
        return neutral, True
    return value, False


def extract_metrics(
    ranking: dict[str, Any],
    version: dict[str, Any],
    simulations: list[dict[str, Any]],
    stress_tests: list[dict[str, Any]],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    merged.update(version)
    merged.update(ranking)

    latest_sim = simulations[0] if simulations else {}

    total_return = number(first_present(
        merged,
        ["total_return", "return_pct", "annual_return", "cagr", "expected_return"],
        first_present(
            latest_sim,
            ["total_return", "return_pct", "annual_return", "cagr"],
            None,
        ),
    ))

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

    max_drawdown = number(first_present(
        merged,
        ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
        first_present(
            latest_sim,
            ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
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

    volatility = number(first_present(
        merged,
        ["volatility", "annualized_volatility", "volatility_pct"],
        first_present(
            latest_sim,
            ["volatility", "annualized_volatility"],
            None,
        ),
    ))

    simulation_passes = sum(
        1 for row in simulations
        if boolean(first_present(
            row,
            ["passed", "success", "simulation_passed"],
            False,
        ))
        or str(first_present(
            row,
            ["status", "simulation_status"],
            "",
        )).upper() in {"PASS", "PASSED", "SUCCESS", "COMPLETED", "READY"}
    )

    stress_passes = sum(
        1 for row in stress_tests
        if boolean(first_present(
            row,
            ["passed", "success", "stress_passed"],
            False,
        ))
        or str(first_present(
            row,
            ["status", "stress_status"],
            "",
        )).upper() in {"PASS", "PASSED", "SUCCESS", "COMPLETED", "READY"}
    )

    simulation_pass_rate = (
        simulation_passes / len(simulations)
        if simulations
        else None
    )
    stress_pass_rate = (
        stress_passes / len(stress_tests)
        if stress_tests
        else None
    )

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "volatility": volatility,
        "simulation_count": len(simulations),
        "stress_count": len(stress_tests),
        "simulation_pass_rate": simulation_pass_rate,
        "stress_pass_rate": stress_pass_rate,
        "original_evolution": number(ranking.get("evolution_score"), 50.0) or 50.0,
        "original_confidence": number(ranking.get("confidence_score"), 50.0) or 50.0,
    }


def base_scores(metrics: dict[str, Any]) -> dict[str, Any]:
    total_return, miss_return = value_or_neutral(metrics["total_return"], 8.0)
    sharpe, miss_sharpe = value_or_neutral(metrics["sharpe"], 0.8)
    sortino, miss_sortino = value_or_neutral(metrics["sortino"], 1.0)
    drawdown, miss_drawdown = value_or_neutral(metrics["max_drawdown"], 15.0)
    win_rate, miss_win_rate = value_or_neutral(metrics["win_rate"], 52.0)
    profit_factor, miss_pf = value_or_neutral(metrics["profit_factor"], 1.25)
    volatility, miss_vol = value_or_neutral(metrics["volatility"], 18.0)

    return_score = clamp(
        0.50 * normalize_return(total_return)
        + 0.30 * normalize_sharpe(sharpe)
        + 0.20 * normalize_profit_factor(profit_factor)
    )

    risk_score = clamp(
        0.55 * normalize_drawdown(drawdown)
        + 0.25 * clamp(100.0 - abs(volatility) * 2.0)
        + 0.20 * normalize_sharpe(sortino)
    )

    stability_score = clamp(
        0.45 * normalize_win_rate(win_rate)
        + 0.30 * normalize_profit_factor(profit_factor)
        + 0.25 * normalize_sharpe(sharpe)
    )

    simulation_rate = metrics["simulation_pass_rate"]
    stress_rate = metrics["stress_pass_rate"]

    simulation_component = (
        50.0 if simulation_rate is None else 100.0 * simulation_rate
    )
    stress_component = (
        50.0 if stress_rate is None else 100.0 * stress_rate
    )

    evidence_density = clamp(
        (metrics["simulation_count"] + metrics["stress_count"]) * 10.0
    )

    robustness_score = clamp(
        0.35 * simulation_component
        + 0.35 * stress_component
        + 0.30 * evidence_density
    )

    missing_flags = {
        "return": miss_return,
        "sharpe": miss_sharpe,
        "sortino": miss_sortino,
        "drawdown": miss_drawdown,
        "win_rate": miss_win_rate,
        "profit_factor": miss_pf,
        "volatility": miss_vol,
    }

    completeness = clamp(
        100.0
        * sum(1 for missing in missing_flags.values() if not missing)
        / len(missing_flags)
    )

    return {
        "return_score": return_score,
        "risk_score": risk_score,
        "stability_score": stability_score,
        "robustness_score": robustness_score,
        "data_completeness": completeness,
        "missing_flags": missing_flags,
    }


def calibrate(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    absolute_values: list[float] = []

    for record in records:
        base = record["base"]
        metrics = record["metrics"]
        rank_score = rank_percentile(
            record["rank_no"],
            len(records),
        )

        absolute = clamp(
            0.22 * base["return_score"]
            + 0.20 * base["risk_score"]
            + 0.18 * base["stability_score"]
            + 0.17 * base["robustness_score"]
            + 0.08 * rank_score
            + 0.15 * metrics["original_evolution"]
        )
        record["absolute_evolution"] = absolute
        record["rank_score"] = rank_score
        absolute_values.append(absolute)

    for record in records:
        base = record["base"]
        metrics = record["metrics"]
        relative = zscore_percentile(
            record["absolute_evolution"],
            absolute_values,
        )

        # Final score is still majority absolute evidence.
        evolution_score = clamp(
            0.72 * record["absolute_evolution"]
            + 0.28 * relative
        )

        candidate_specific_evidence = clamp(
            0.30 * base["robustness_score"]
            + 0.25 * base["data_completeness"]
            + 0.20 * base["stability_score"]
            + 0.15 * base["risk_score"]
            + 0.10 * relative
        )

        uncertainty_penalty = 0.0
        if base["data_completeness"] < 40:
            uncertainty_penalty += 12.0
        elif base["data_completeness"] < 70:
            uncertainty_penalty += 5.0

        if metrics["simulation_count"] == 0:
            uncertainty_penalty += 5.0
        if metrics["stress_count"] == 0:
            uncertainty_penalty += 5.0

        confidence_score = clamp(
            0.55 * candidate_specific_evidence
            + 0.25 * metrics["original_confidence"]
            + 0.20 * relative
            - uncertainty_penalty
        )

        record["relative_score"] = relative
        record["evolution_score"] = round(evolution_score, 4)
        record["confidence_score"] = round(confidence_score, 4)
        record["uncertainty_penalty"] = round(uncertainty_penalty, 4)

    return records


def recommendation(
    record: dict[str, Any],
) -> tuple[str, bool, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    metrics = record["metrics"]
    base = record["base"]

    if record["rank_no"] != 1:
        blockers.append("TOP_RANK_REQUIRED")

    if record["evolution_score"] < 70:
        blockers.append("EVOLUTION_SCORE_BELOW_70")

    if record["confidence_score"] < 60:
        blockers.append("CONFIDENCE_SCORE_BELOW_60")

    if metrics["max_drawdown"] is not None:
        if abs(metrics["max_drawdown"]) > 20:
            blockers.append("MAX_DRAWDOWN_ABOVE_20")
    else:
        warnings.append("MAX_DRAWDOWN_MISSING")

    if metrics["simulation_count"] == 0:
        warnings.append("SIMULATION_EVIDENCE_MISSING")
    elif (metrics["simulation_pass_rate"] or 0) < 0.60:
        blockers.append("SIMULATION_PASS_RATE_BELOW_60")

    if metrics["stress_count"] == 0:
        warnings.append("STRESS_EVIDENCE_MISSING")
    elif (metrics["stress_pass_rate"] or 0) < 0.60:
        blockers.append("STRESS_PASS_RATE_BELOW_60")

    if base["data_completeness"] < 40:
        blockers.append("DATA_COMPLETENESS_BELOW_40")
    elif base["data_completeness"] < 70:
        warnings.append("DATA_COMPLETENESS_BELOW_70")

    if not blockers:
        return "PROMOTE_FOR_HUMAN_REVIEW", True, blockers, warnings

    if (
        record["rank_no"] <= 3
        and record["evolution_score"] >= 55
        and record["confidence_score"] >= 50
    ):
        return "REVIEW_REQUIRED", False, blockers, warnings

    return "REJECT", False, blockers, warnings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise 5.6.3 Evolution Score Optimizer v3.0"
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

    records: list[dict[str, Any]] = []

    for ranking in rankings:
        ranking_id = str(ranking["id"])
        version_id = ranking.get("version_id")
        source_version_no = str(first_present(
            ranking,
            ["version_no", "source_version_no"],
            f"UNKNOWN-{ranking_id[:8]}",
        ))

        version_rows = []
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
        for table in ("simulation_runs_v56", "simulation_results_v56"):
            simulation_query = (
                f"version_id=eq.{version_id}&order=created_at.desc&limit=50"
                if version_id
                else "order=created_at.desc&limit=50"
            )
            simulations = read(client, table, simulation_query)
            if simulations:
                break

        stress_query = (
            f"version_id=eq.{version_id}&order=created_at.desc&limit=50"
            if version_id
            else "order=created_at.desc&limit=50"
        )
        stress_tests = read(
            client,
            "stress_tests_v56",
            stress_query,
        )

        metrics = extract_metrics(
            ranking,
            version,
            simulations,
            stress_tests,
        )

        records.append({
            "ranking": ranking,
            "ranking_id": ranking_id,
            "source_version_no": source_version_no,
            "rank_no": integer(ranking.get("rank_no"), 999),
            "metrics": metrics,
            "base": base_scores(metrics),
        })

    records = calibrate(records)

    promoted = 0
    review_required = 0
    rejected = 0

    for record in records:
        rec, selected, blockers, warnings = recommendation(record)

        client.patch(
            "portfolio_rankings_v56",
            f"id=eq.{record['ranking_id']}",
            {
                "evolution_score": record["evolution_score"],
                "confidence_score": record["confidence_score"],
                "recommendation": rec,
                "selected_for_review": selected,
            },
        )

        record["recommendation"] = rec
        record["selected_for_review"] = selected
        record["blockers"] = blockers
        record["warnings"] = warnings

        promoted += 1 if selected else 0
        review_required += 1 if rec == "REVIEW_REQUIRED" else 0
        rejected += 1 if rec == "REJECT" else 0

        print(
            f"{record['source_version_no']}: "
            f"rank={record['rank_no']}, "
            f"absolute={record['absolute_evolution']:.2f}, "
            f"relative={record['relative_score']:.2f}, "
            f"evolution={record['evolution_score']:.2f}, "
            f"confidence={record['confidence_score']:.2f}, "
            f"recommendation={rec}"
        )

    status_rows = read(
        client,
        "evolution_status_v56",
        f"status_date=eq.{RUN_DATE}&limit=1",
    )

    if status_rows:
        status = status_rows[0]

        overall_status = (
            "READY_FOR_PROMOTION"
            if promoted > 0
            else "REVIEW_REQUIRED"
            if review_required > 0
            else "WARNING"
        )

        diagnostic_records = []
        for record in records:
            diagnostic_records.append({
                "ranking_id": record["ranking_id"],
                "source_version_no": record["source_version_no"],
                "rank_no": record["rank_no"],
                "absolute_evolution": round(
                    record["absolute_evolution"], 4
                ),
                "relative_score": round(record["relative_score"], 4),
                "evolution_score": record["evolution_score"],
                "confidence_score": record["confidence_score"],
                "uncertainty_penalty": record["uncertainty_penalty"],
                "data_completeness": round(
                    record["base"]["data_completeness"], 4
                ),
                "return_score": round(
                    record["base"]["return_score"], 4
                ),
                "risk_score": round(
                    record["base"]["risk_score"], 4
                ),
                "stability_score": round(
                    record["base"]["stability_score"], 4
                ),
                "robustness_score": round(
                    record["base"]["robustness_score"], 4
                ),
                "recommendation": record["recommendation"],
                "selected_for_review": record["selected_for_review"],
                "blockers": record["blockers"],
                "warnings": record["warnings"],
                "missing_flags": record["base"]["missing_flags"],
            })

        client.patch(
            "evolution_status_v56",
            f"status_date=eq.{RUN_DATE}",
            {
                "overall_status": overall_status,
                "diagnostics": {
                    **(status.get("diagnostics") or {}),
                    "optimizer_engine_version": ENGINE_VERSION,
                    "scoring_model": "absolute_plus_relative_calibration",
                    "rankings_optimized": len(records),
                    "promotion_recommendations": promoted,
                    "review_required": review_required,
                    "rejected": rejected,
                    "average_evolution_score": round(
                        mean(
                            record["evolution_score"]
                            for record in records
                        ),
                        4,
                    ),
                    "average_confidence_score": round(
                        mean(
                            record["confidence_score"]
                            for record in records
                        ),
                        4,
                    ),
                    "score_details": diagnostic_records,
                    "optimized_at": now(),
                },
            },
        )

    if promoted == 0:
        print(
            "No candidate met the evidence-based promotion threshold. "
            "No artificial promotion was performed."
        )

    print(
        f"Enterprise 5.6.3 complete: optimized={len(records)}, "
        f"promoted={promoted}, review_required={review_required}, "
        f"rejected={rejected}"
    )


if __name__ == "__main__":
    main()
