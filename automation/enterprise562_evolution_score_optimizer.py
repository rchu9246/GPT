from __future__ import annotations

import argparse
import math
import os
import uuid
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any, Iterable

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.6.2"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
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
        "true", "t", "1", "yes", "y", "pass", "passed", "success",
        "completed", "ready",
    }


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


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


def neutral_if_missing(
    value: float | None,
    neutral: float,
) -> tuple[float, bool]:
    if value is None:
        return neutral, True
    return value, False


def normalize_percent_return(value: float) -> float:
    # -10% -> 20, 0% -> 40, 10% -> 60, 20% -> 80, 30% -> 100
    return clamp(40.0 + value * 2.0)


def normalize_sharpe(value: float) -> float:
    # -0.5 -> 10, 0 -> 30, 1 -> 60, 2 -> 90
    return clamp(30.0 + value * 30.0)


def normalize_drawdown(value: float) -> float:
    dd = abs(value)
    # 5 -> 95, 10 -> 85, 20 -> 65, 30 -> 45, 40 -> 25
    return clamp(105.0 - dd * 2.0)


def normalize_win_rate(value: float) -> float:
    rate = value * 100.0 if 0 <= value <= 1 else value
    return clamp(rate * 2.0 - 40.0)


def normalize_profit_factor(value: float) -> float:
    # 0.8 -> 30, 1.0 -> 40, 1.5 -> 65, 2.0 -> 90
    return clamp(40.0 + (value - 1.0) * 50.0)


def normalize_rank(rank_no: int, population: int) -> float:
    if population <= 1:
        return 100.0
    return clamp(
        100.0 * (population - rank_no) / max(1, population - 1)
    )


def extract_source_metrics(
    ranking: dict[str, Any],
    version: dict[str, Any],
    simulation_rows: list[dict[str, Any]],
    stress_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    merged.update(version)
    merged.update(ranking)

    latest_sim = simulation_rows[0] if simulation_rows else {}
    latest_stress = stress_rows[0] if stress_rows else {}

    total_return = num(first_present(
        merged,
        ["total_return", "return_pct", "annual_return", "cagr", "expected_return"],
        first_present(
            latest_sim,
            ["total_return", "return_pct", "annual_return", "cagr"],
            None,
        ),
    ))

    sharpe = num(first_present(
        merged,
        ["sharpe_ratio", "sharpe", "risk_adjusted_return"],
        first_present(latest_sim, ["sharpe_ratio", "sharpe"], None),
    ))

    max_drawdown = num(first_present(
        merged,
        ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
        first_present(
            latest_sim,
            ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
            None,
        ),
    ))

    win_rate = num(first_present(
        merged,
        ["win_rate", "winning_rate", "hit_rate"],
        first_present(latest_sim, ["win_rate", "winning_rate"], None),
    ))

    profit_factor = num(first_present(
        merged,
        ["profit_factor", "payoff_ratio"],
        first_present(latest_sim, ["profit_factor", "payoff_ratio"], None),
    ))

    volatility = num(first_present(
        merged,
        ["volatility", "annualized_volatility", "volatility_pct"],
        first_present(
            latest_sim,
            ["volatility", "annualized_volatility"],
            None,
        ),
    ))

    sortino = num(first_present(
        merged,
        ["sortino_ratio", "sortino"],
        first_present(latest_sim, ["sortino_ratio", "sortino"], None),
    ))

    original_evolution = num(ranking.get("evolution_score"), 50.0) or 50.0
    original_confidence = num(ranking.get("confidence_score"), 50.0) or 50.0

    simulation_pass = any(
        boolean(first_present(
            row,
            ["passed", "success", "simulation_passed"],
            False,
        ))
        or str(first_present(
            row,
            ["status", "simulation_status"],
            "",
        )).upper() in {
            "PASS", "PASSED", "SUCCESS", "COMPLETED", "READY"
        }
        for row in simulation_rows
    )

    stress_pass = any(
        boolean(first_present(
            row,
            ["passed", "success", "stress_passed"],
            False,
        ))
        or str(first_present(
            row,
            ["status", "stress_status"],
            "",
        )).upper() in {
            "PASS", "PASSED", "SUCCESS", "COMPLETED", "READY"
        }
        for row in stress_rows
    )

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "volatility": volatility,
        "original_evolution": original_evolution,
        "original_confidence": original_confidence,
        "simulation_pass": simulation_pass,
        "stress_pass": stress_pass,
        "simulation_count": len(simulation_rows),
        "stress_count": len(stress_rows),
    }


def calculate_scores(
    *,
    metrics: dict[str, Any],
    rank_no: int,
    population: int,
) -> dict[str, Any]:
    total_return, missing_return = neutral_if_missing(
        metrics["total_return"],
        8.0,
    )
    sharpe, missing_sharpe = neutral_if_missing(metrics["sharpe"], 0.8)
    sortino, missing_sortino = neutral_if_missing(metrics["sortino"], 1.0)
    drawdown, missing_drawdown = neutral_if_missing(
        metrics["max_drawdown"],
        15.0,
    )
    win_rate, missing_win_rate = neutral_if_missing(
        metrics["win_rate"],
        52.0,
    )
    profit_factor, missing_pf = neutral_if_missing(
        metrics["profit_factor"],
        1.25,
    )
    volatility, missing_volatility = neutral_if_missing(
        metrics["volatility"],
        18.0,
    )

    return_score = clamp(
        0.50 * normalize_percent_return(total_return)
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

    rank_score = normalize_rank(rank_no, population)

    evidence_count = (
        metrics["simulation_count"] + metrics["stress_count"]
    )
    evidence_density = clamp(evidence_count * 12.5)
    evidence_pass_score = (
        50.0
        + (25.0 if metrics["simulation_pass"] else 0.0)
        + (25.0 if metrics["stress_pass"] else 0.0)
    )
    robustness_score = clamp(
        0.55 * evidence_density
        + 0.45 * evidence_pass_score
    )

    original_score = clamp(
        0.60 * metrics["original_evolution"]
        + 0.40 * metrics["original_confidence"]
    )

    missing_flags = {
        "return": missing_return,
        "sharpe": missing_sharpe,
        "sortino": missing_sortino,
        "drawdown": missing_drawdown,
        "win_rate": missing_win_rate,
        "profit_factor": missing_pf,
        "volatility": missing_volatility,
    }
    missing_count = sum(1 for flag in missing_flags.values() if flag)
    data_completeness = clamp(
        100.0 * (len(missing_flags) - missing_count) / len(missing_flags)
    )

    completeness_penalty = max(0.0, 60.0 - data_completeness) * 0.20

    evolution_score = clamp(
        0.22 * return_score
        + 0.20 * risk_score
        + 0.17 * stability_score
        + 0.16 * robustness_score
        + 0.10 * rank_score
        + 0.15 * metrics["original_evolution"]
        - completeness_penalty
    )

    confidence_score = clamp(
        0.30 * robustness_score
        + 0.20 * stability_score
        + 0.15 * risk_score
        + 0.15 * data_completeness
        + 0.20 * metrics["original_confidence"]
    )

    return {
        "return_score": round(return_score, 4),
        "risk_score": round(risk_score, 4),
        "stability_score": round(stability_score, 4),
        "robustness_score": round(robustness_score, 4),
        "rank_score": round(rank_score, 4),
        "original_score": round(original_score, 4),
        "data_completeness": round(data_completeness, 4),
        "completeness_penalty": round(completeness_penalty, 4),
        "evolution_score": round(evolution_score, 4),
        "confidence_score": round(confidence_score, 4),
        "missing_flags": missing_flags,
    }


def decide_recommendation(
    *,
    rank_no: int,
    metrics: dict[str, Any],
    scores: dict[str, Any],
) -> tuple[str, bool, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if rank_no != 1:
        blockers.append("TOP_RANK_REQUIRED")
    if scores["evolution_score"] < 70:
        blockers.append("EVOLUTION_SCORE_BELOW_70")
    if scores["confidence_score"] < 60:
        blockers.append("CONFIDENCE_SCORE_BELOW_60")

    if metrics["max_drawdown"] is not None:
        if abs(metrics["max_drawdown"]) > 20:
            blockers.append("MAX_DRAWDOWN_ABOVE_20")
    else:
        warnings.append("MAX_DRAWDOWN_MISSING")

    if metrics["simulation_count"] == 0:
        warnings.append("SIMULATION_EVIDENCE_MISSING")
    elif not metrics["simulation_pass"]:
        blockers.append("SIMULATION_NOT_PASSED")

    if metrics["stress_count"] == 0:
        warnings.append("STRESS_EVIDENCE_MISSING")
    elif not metrics["stress_pass"]:
        blockers.append("STRESS_TEST_NOT_PASSED")

    if scores["data_completeness"] < 40:
        blockers.append("DATA_COMPLETENESS_BELOW_40")
    elif scores["data_completeness"] < 70:
        warnings.append("DATA_COMPLETENESS_BELOW_70")

    if not blockers:
        return "PROMOTE_FOR_HUMAN_REVIEW", True, blockers, warnings

    if (
        rank_no <= 3
        and scores["evolution_score"] >= 55
        and scores["confidence_score"] >= 50
    ):
        return "REVIEW_REQUIRED", False, blockers, warnings

    return "REJECT", False, blockers, warnings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise 5.6.2 Evolution Score Optimizer v2.0"
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

    population = len(rankings)
    optimized = 0
    promoted = 0
    review_required = 0
    rejected = 0
    score_rows: list[dict[str, Any]] = []

    for ranking in rankings:
        ranking_id = str(ranking["id"])
        version_id = ranking.get("version_id")
        source_version_no = str(first_present(
            ranking,
            ["version_no", "source_version_no"],
            f"UNKNOWN-{ranking_id[:8]}",
        ))
        rank_no = integer(ranking.get("rank_no"), 999)

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

        simulation_rows: list[dict[str, Any]] = []
        for table in ("simulation_runs_v56", "simulation_results_v56"):
            query = (
                f"version_id=eq.{version_id}&order=created_at.desc&limit=20"
                if version_id
                else "order=created_at.desc&limit=20"
            )
            simulation_rows = read(client, table, query)
            if simulation_rows:
                break

        stress_query = (
            f"version_id=eq.{version_id}&order=created_at.desc&limit=20"
            if version_id
            else "order=created_at.desc&limit=20"
        )
        stress_rows = read(client, "stress_tests_v56", stress_query)

        metrics = extract_source_metrics(
            ranking,
            version,
            simulation_rows,
            stress_rows,
        )
        scores = calculate_scores(
            metrics=metrics,
            rank_no=rank_no,
            population=population,
        )
        rec, selected, blockers, warnings = decide_recommendation(
            rank_no=rank_no,
            metrics=metrics,
            scores=scores,
        )

        client.patch(
            "portfolio_rankings_v56",
            f"id=eq.{ranking_id}",
            {
                "evolution_score": scores["evolution_score"],
                "confidence_score": scores["confidence_score"],
                "recommendation": rec,
                "selected_for_review": selected,
            },
        )

        optimized += 1
        promoted += 1 if selected else 0
        review_required += 1 if rec == "REVIEW_REQUIRED" else 0
        rejected += 1 if rec == "REJECT" else 0

        score_rows.append({
            "ranking_id": ranking_id,
            "source_version_no": source_version_no,
            "rank_no": rank_no,
            **metrics,
            **scores,
            "recommendation": rec,
            "selected_for_review": selected,
            "blockers": blockers,
            "warnings": warnings,
        })

        print(
            f"{source_version_no}: rank={rank_no}, "
            f"evolution={scores['evolution_score']:.2f}, "
            f"confidence={scores['confidence_score']:.2f}, "
            f"completeness={scores['data_completeness']:.2f}, "
            f"recommendation={rec}"
        )

    status_rows = read(
        client,
        "evolution_status_v56",
        f"status_date=eq.{RUN_DATE}&limit=1",
    )
    status = status_rows[0] if status_rows else {}

    overall_status = (
        "READY_FOR_PROMOTION"
        if promoted > 0
        else "REVIEW_REQUIRED"
        if review_required > 0
        else "WARNING"
    )

    status_payload = {
        "overall_status": overall_status,
        "diagnostics": {
            **(status.get("diagnostics") or {}),
            "optimizer_engine_version": ENGINE_VERSION,
            "rankings_optimized": optimized,
            "promotion_recommendations": promoted,
            "review_required": review_required,
            "rejected": rejected,
            "average_evolution_score": round(
                mean(row["evolution_score"] for row in score_rows),
                4,
            ),
            "average_confidence_score": round(
                mean(row["confidence_score"] for row in score_rows),
                4,
            ),
            "score_details": score_rows,
            "optimized_at": now(),
        },
    }

    updated_rows = read(
        client,
        "evolution_status_v56",
        f"status_date=eq.{RUN_DATE}&limit=1",
    )
    if updated_rows:
        client.patch(
            "evolution_status_v56",
            f"status_date=eq.{RUN_DATE}",
            status_payload,
        )

    print(
        f"Enterprise 5.6.2 complete: optimized={optimized}, "
        f"promoted={promoted}, review_required={review_required}, "
        f"rejected={rejected}"
    )


if __name__ == "__main__":
    main()
