from __future__ import annotations

import argparse
import math
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.6.1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def num(value: Any, default: float = 0.0) -> float:
    try:
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
        "true", "t", "1", "yes", "y", "pass", "passed", "success"
    }


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def first_present(row: dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
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


def normalize_return(value: float) -> float:
    # 0% => 35, 10% => 55, 20% => 75, 30% => 95
    return clamp(35.0 + value * 2.0)


def normalize_sharpe(value: float) -> float:
    # Sharpe 0 => 30, 1 => 60, 2 => 90
    return clamp(30.0 + value * 30.0)


def normalize_drawdown(value: float) -> float:
    dd = abs(value)
    # 5% => 95, 10% => 85, 20% => 65, 30% => 45
    return clamp(105.0 - dd * 2.0)


def normalize_win_rate(value: float) -> float:
    rate = value * 100.0 if 0 <= value <= 1 else value
    # 40 => 40, 50 => 60, 60 => 80, 70 => 100
    return clamp(rate * 2.0 - 40.0)


def normalize_profit_factor(value: float) -> float:
    # 1.0 => 40, 1.5 => 65, 2.0 => 90
    return clamp(40.0 + (value - 1.0) * 50.0)


def extract_metrics(
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
        first_present(latest_sim, ["total_return", "return_pct", "annual_return", "cagr"], 0),
    ))
    sharpe = num(first_present(
        merged,
        ["sharpe_ratio", "sharpe", "risk_adjusted_return"],
        first_present(latest_sim, ["sharpe_ratio", "sharpe"], 0),
    ))
    max_drawdown = num(first_present(
        merged,
        ["max_drawdown", "maximum_drawdown", "drawdown_pct"],
        first_present(latest_sim, ["max_drawdown", "maximum_drawdown"], 100),
    ))
    win_rate = num(first_present(
        merged,
        ["win_rate", "winning_rate", "hit_rate"],
        first_present(latest_sim, ["win_rate", "winning_rate"], 0),
    ))
    profit_factor = num(first_present(
        merged,
        ["profit_factor", "payoff_ratio"],
        first_present(latest_sim, ["profit_factor"], 1),
    ))
    volatility = num(first_present(
        merged,
        ["volatility", "annualized_volatility", "volatility_pct"],
        first_present(latest_sim, ["volatility", "annualized_volatility"], 30),
    ))
    sortino = num(first_present(
        merged,
        ["sortino_ratio", "sortino"],
        first_present(latest_sim, ["sortino_ratio", "sortino"], 0),
    ))

    simulation_pass = any(
        boolean(first_present(row, ["passed", "success", "simulation_passed"], False))
        or str(first_present(row, ["status", "simulation_status"], "")).upper()
        in {"PASS", "PASSED", "SUCCESS", "COMPLETED"}
        for row in simulation_rows
    )
    stress_pass = any(
        boolean(first_present(row, ["passed", "success", "stress_passed"], False))
        or str(first_present(row, ["status", "stress_status"], "")).upper()
        in {"PASS", "PASSED", "SUCCESS", "COMPLETED"}
        for row in stress_rows
    )

    simulation_count = len(simulation_rows)
    stress_count = len(stress_rows)

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "volatility": volatility,
        "simulation_pass": simulation_pass,
        "stress_pass": stress_pass,
        "simulation_count": simulation_count,
        "stress_count": stress_count,
    }


def score_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    return_score = clamp(
        0.55 * normalize_return(metrics["total_return"])
        + 0.30 * normalize_sharpe(metrics["sharpe"])
        + 0.15 * normalize_profit_factor(metrics["profit_factor"])
    )

    risk_score = clamp(
        0.65 * normalize_drawdown(metrics["max_drawdown"])
        + 0.20 * clamp(100.0 - abs(metrics["volatility"]) * 2.0)
        + 0.15 * normalize_sharpe(metrics["sortino"])
    )

    stability_score = clamp(
        0.55 * normalize_win_rate(metrics["win_rate"])
        + 0.25 * normalize_profit_factor(metrics["profit_factor"])
        + 0.20 * normalize_sharpe(metrics["sharpe"])
    )

    evidence_count = metrics["simulation_count"] + metrics["stress_count"]
    evidence_score = clamp(evidence_count * 10.0, 0, 80)
    robustness_score = clamp(
        evidence_score
        + (10 if metrics["simulation_pass"] else 0)
        + (10 if metrics["stress_pass"] else 0)
    )

    complexity_penalty = 0.0
    if metrics["simulation_count"] == 0:
        complexity_penalty += 10
    if metrics["stress_count"] == 0:
        complexity_penalty += 10
    if metrics["max_drawdown"] > 25:
        complexity_penalty += 10
    if metrics["profit_factor"] < 1:
        complexity_penalty += 10

    evolution_score = clamp(
        0.30 * return_score
        + 0.25 * risk_score
        + 0.20 * stability_score
        + 0.25 * robustness_score
        - complexity_penalty
    )

    confidence_score = clamp(
        0.35 * robustness_score
        + 0.25 * stability_score
        + 0.20 * risk_score
        + 0.20 * min(evidence_count * 12.5, 100)
    )

    return {
        "return_score": round(return_score, 4),
        "risk_score": round(risk_score, 4),
        "stability_score": round(stability_score, 4),
        "robustness_score": round(robustness_score, 4),
        "complexity_penalty": round(complexity_penalty, 4),
        "evolution_score": round(evolution_score, 4),
        "confidence_score": round(confidence_score, 4),
    }


def recommendation(
    *,
    rank_no: int,
    scores: dict[str, float],
    metrics: dict[str, Any],
) -> tuple[str, bool, list[str]]:
    blockers: list[str] = []

    if rank_no != 1:
        blockers.append("TOP_RANK_REQUIRED")
    if scores["evolution_score"] < 70:
        blockers.append("EVOLUTION_SCORE_BELOW_70")
    if scores["confidence_score"] < 60:
        blockers.append("CONFIDENCE_SCORE_BELOW_60")
    if abs(metrics["max_drawdown"]) > 20:
        blockers.append("MAX_DRAWDOWN_ABOVE_20")
    if not metrics["simulation_pass"]:
        blockers.append("SIMULATION_NOT_PASSED")
    if not metrics["stress_pass"]:
        blockers.append("STRESS_TEST_NOT_PASSED")

    promote = not blockers
    if promote:
        return "PROMOTE_FOR_HUMAN_REVIEW", True, []

    if rank_no <= 3 and scores["evolution_score"] >= 55:
        return "REVIEW_REQUIRED", False, blockers

    return "REJECT", False, blockers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise 5.6.1 Evolution Score Optimizer"
    )
    parser.add_argument(
        "--ranking-id",
        default="",
        help="Optional portfolio_rankings_v56 UUID; empty evaluates latest rankings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
    )
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

    optimized = 0
    promoted = 0
    score_rows: list[dict[str, Any]] = []

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
        rank_no = integer(ranking.get("rank_no"), 999)

        version_rows = (
            read(
                client,
                "portfolio_versions_v56",
                f"id=eq.{version_id}&limit=1",
            )
            if version_id
            else read(
                client,
                "portfolio_versions_v56",
                f"version_no=eq.{source_version_no}&limit=1",
            )
        )
        version = version_rows[0] if version_rows else {}

        simulation_rows = []
        for table in ("simulation_runs_v56", "simulation_results_v56"):
            simulation_rows = read(
                client,
                table,
                (
                    f"version_id=eq.{version_id}&order=created_at.desc&limit=20"
                    if version_id
                    else "order=created_at.desc&limit=20"
                ),
            )
            if simulation_rows:
                break

        stress_rows = read(
            client,
            "stress_tests_v56",
            (
                f"version_id=eq.{version_id}&order=created_at.desc&limit=20"
                if version_id
                else "order=created_at.desc&limit=20"
            ),
        )

        metrics = extract_metrics(
            ranking,
            version,
            simulation_rows,
            stress_rows,
        )
        scores = score_metrics(metrics)
        rec, selected, blockers = recommendation(
            rank_no=rank_no,
            scores=scores,
            metrics=metrics,
        )

        patch_payload = {
            "evolution_score": scores["evolution_score"],
            "confidence_score": scores["confidence_score"],
            "recommendation": rec,
            "selected_for_review": selected,
        }

        client.patch(
            "portfolio_rankings_v56",
            f"id=eq.{ranking_id}",
            patch_payload,
        )

        optimized += 1
        promoted += 1 if selected else 0
        score_rows.append(
            {
                "ranking_id": ranking_id,
                "source_version_no": source_version_no,
                "rank_no": rank_no,
                **metrics,
                **scores,
                "recommendation": rec,
                "selected_for_review": selected,
                "blockers": blockers,
            }
        )

        print(
            f"{source_version_no}: rank={rank_no}, "
            f"evolution={scores['evolution_score']:.2f}, "
            f"confidence={scores['confidence_score']:.2f}, "
            f"recommendation={rec}"
        )

    status_rows = read(
        client,
        "evolution_status_v56",
        f"status_date=eq.{RUN_DATE}&limit=1",
    )
    status = status_rows[0] if status_rows else {}

    status_payload: dict[str, Any] = {
        "overall_status": (
            "READY_FOR_PROMOTION"
            if promoted > 0
            else "WARNING"
        ),
        "diagnostics": {
            **(status.get("diagnostics") or {}),
            "optimizer_engine_version": ENGINE_VERSION,
            "rankings_optimized": optimized,
            "promotion_recommendations": promoted,
            "score_details": score_rows,
            "optimized_at": now(),
        },
    }

    # Only update fields known to exist on the existing v56 status table.
    client.patch(
        "evolution_status_v56",
        f"status_date=eq.{RUN_DATE}",
        status_payload,
    )

    if promoted == 0:
        print(
            "No candidate satisfied all promotion evidence requirements. "
            "Scores were not artificially inflated."
        )

    print(
        f"Enterprise 5.6.1 complete: optimized={optimized}, "
        f"promoted_for_human_review={promoted}"
    )


if __name__ == "__main__":
    main()
