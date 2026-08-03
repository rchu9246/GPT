from __future__ import annotations

import hashlib
import math
import os
import random
import uuid
from datetime import date, datetime, timezone
from statistics import mean, pstdev
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.6.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def stable_seed(*parts: Any) -> int:
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


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
    rows = read(client, table, query)
    return rows[0] if rows else {}


def source_requests(client: SupabaseRestClient) -> list[dict[str, Any]]:
    rows = read(
        client,
        "promotion_requests_v55",
        (
            "paper_only=eq.true"
            "&automatic_production_promotion_enabled=eq.false"
            "&order=request_date.desc,created_at.desc"
            "&limit=100"
        ),
        required=True,
    )
    return rows


def baseline_version(client: SupabaseRestClient) -> dict[str, Any]:
    rows = read(
        client,
        "portfolio_versions_v56",
        (
            "version_type=eq.BASELINE"
            "&active=eq.true"
            "&order=created_at.desc"
            "&limit=1"
        ),
    )
    return rows[0] if rows else {}


def synthetic_returns(
    seed: int,
    annual_return_pct: float,
    volatility_pct: float,
    periods: int = 252,
) -> list[float]:
    rng = random.Random(seed)
    daily_mean = annual_return_pct / 100 / 252
    daily_vol = volatility_pct / 100 / math.sqrt(252)
    returns = []
    for _ in range(periods):
        shock = rng.gauss(0, 1)
        returns.append(daily_mean + daily_vol * shock)
    return returns


def max_drawdown_pct(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= 1 + r
        peak = max(peak, equity)
        dd = (equity / peak - 1) * 100
        max_dd = min(max_dd, dd)
    return abs(max_dd)


def sharpe_ratio(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    vol = pstdev(returns)
    if vol == 0:
        return 0.0
    return mean(returns) / vol * math.sqrt(252)


def sortino_ratio(returns: list[float]) -> float:
    downside = [min(0.0, r) for r in returns]
    downside_dev = math.sqrt(mean([x * x for x in downside])) if downside else 0
    if downside_dev == 0:
        return 0.0
    return mean(returns) / downside_dev * math.sqrt(252)


def cumulative_return_pct(returns: list[float]) -> float:
    value = 1.0
    for r in returns:
        value *= 1 + r
    return (value - 1) * 100


def win_rate_pct(returns: list[float]) -> float:
    if not returns:
        return 0.0
    return sum(1 for r in returns if r > 0) / len(returns) * 100


def annualized_volatility_pct(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    return pstdev(returns) * math.sqrt(252) * 100


def monte_carlo_summary(
    seed: int,
    annual_return_pct: float,
    volatility_pct: float,
    iterations: int,
) -> dict[str, float]:
    rng = random.Random(seed)
    outcomes = []
    for _ in range(iterations):
        path = synthetic_returns(
            rng.randint(1, 2**31 - 1),
            annual_return_pct,
            volatility_pct,
            252,
        )
        outcomes.append(cumulative_return_pct(path))
    outcomes.sort()

    def percentile(p: float) -> float:
        if not outcomes:
            return 0.0
        idx = int((len(outcomes) - 1) * p)
        return outcomes[idx]

    losses = [x for x in outcomes if x < 0]
    var5 = percentile(0.05)
    shortfall = mean([x for x in outcomes if x <= var5]) if outcomes else 0.0

    return {
        "expected": mean(outcomes) if outcomes else 0.0,
        "median": percentile(0.50),
        "p05": percentile(0.05),
        "p95": percentile(0.95),
        "prob_loss": len(losses) / len(outcomes) * 100 if outcomes else 0.0,
        "prob_dd_breach": sum(1 for x in outcomes if x < -20) / len(outcomes) * 100
        if outcomes
        else 0.0,
        "var": abs(var5),
        "expected_shortfall": abs(shortfall),
    }


def evolution_score(
    annual_return: float,
    sharpe: float,
    max_drawdown: float,
    stability: float,
    mc_prob_loss: float,
    promotion_readiness: float,
    governance_ready: bool,
) -> dict[str, float]:
    return_score = clamp(50 + annual_return * 2.0, 0, 100)
    risk_score = clamp(100 - max_drawdown * 3.0, 0, 100)
    stability_score = clamp(stability, 0, 100)
    robustness_score = clamp(
        100 - mc_prob_loss * 0.7 + max(0, sharpe) * 8,
        0,
        100,
    )
    promotion_score = clamp(promotion_readiness, 0, 100)
    governance_score = 100.0 if governance_ready else 50.0

    total = (
        return_score * 0.20
        + risk_score * 0.20
        + stability_score * 0.15
        + robustness_score * 0.20
        + promotion_score * 0.15
        + governance_score * 0.10
    )
    confidence = clamp(
        40
        + max(0, sharpe) * 10
        + stability_score * 0.25
        - mc_prob_loss * 0.20,
        0,
        100,
    )

    return {
        "return_score": return_score,
        "risk_score": risk_score,
        "stability_score": stability_score,
        "robustness_score": robustness_score,
        "promotion_score": promotion_score,
        "governance_score": governance_score,
        "evolution_score": clamp(total, 0, 100),
        "confidence_score": confidence,
    }


def main() -> None:
    client = SupabaseRestClient()
    run_id = str(uuid.uuid4())

    monte_carlo_iterations = int(
        num(os.getenv("ENTERPRISE56_MONTE_CARLO_ITERATIONS"), 250)
    )
    selection_threshold = num(
        os.getenv("ENTERPRISE56_SELECTION_THRESHOLD"), 70
    )
    max_candidates = int(
        num(os.getenv("ENTERPRISE56_MAX_CANDIDATES"), 20)
    )

    requests = source_requests(client)[:max_candidates]
    baseline = baseline_version(client)
    baseline_id = baseline.get("id")
    baseline_no = str(
        baseline.get("version_no") or "5.6-baseline-0001"
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if not requests:
        blockers.append("NO_PROMOTION_REQUESTS_V55")

    versions_registered = 0
    simulation_runs = 0
    simulation_results = 0
    stress_tests = 0
    monte_carlo_runs = 0
    evolution_scores_count = 0
    ranked_versions = 0
    selected_for_review = 0
    rejected_versions = 0
    rollback_recommendations = 0

    score_rows: list[dict[str, Any]] = []

    for request in requests:
        request_id = str(request["id"])
        source_candidate = str(request.get("candidate_version_no") or "UNKNOWN")
        version_no = f"5.6-candidate-{request_id[:8]}"
        readiness = num(request.get("readiness_score"), 50)
        request_status = str(request.get("request_status") or "DRAFT")
        readiness_status = str(
            request.get("readiness_status") or "NEEDS_MORE_EVIDENCE"
        )

        source_proposals = request.get("source_proposal_ids") or []
        if not isinstance(source_proposals, list):
            source_proposals = []

        client.upsert(
            "portfolio_versions_v56",
            {
                "version_date": RUN_DATE,
                "version_no": version_no,
                "version_type": "CANDIDATE",
                "version_status": "SIMULATING",
                "source_request_id": request_id,
                "source_candidate_version": source_candidate,
                "baseline_version_no": baseline_no,
                "portfolio_name": f"Evolution Candidate {source_candidate}",
                "description": (
                    "Paper-only portfolio candidate generated from "
                    "Enterprise 5.5 Promotion Control."
                ),
                "allocation_snapshot": {
                    "source_request_id": request_id,
                    "paper_traffic_pct": 10,
                },
                "strategy_snapshot": {
                    "source_proposal_ids": source_proposals,
                },
                "agent_weight_snapshot": {},
                "risk_snapshot": {
                    "rollback_ready": bool(request.get("rollback_ready")),
                },
                "paper_only": True,
                "human_approval_required": True,
                "automatic_baseline_promotion_enabled": False,
                "automatic_portfolio_application_enabled": False,
                "live_trading_enabled": False,
                "active": False,
                "metadata": {
                    "run_id": run_id,
                    "engine_version": ENGINE_VERSION,
                    "request_status": request_status,
                    "readiness_status": readiness_status,
                },
            },
            "version_date,version_no",
        )

        version = read(
            client,
            "portfolio_versions_v56",
            f"version_date=eq.{RUN_DATE}&version_no=eq.{version_no}&limit=1",
            required=True,
        )[0]
        version_id = str(version["id"])
        versions_registered += 1

        if baseline_id:
            client.upsert(
                "version_relationships_v56",
                {
                    "parent_version_id": baseline_id,
                    "child_version_id": version_id,
                    "relationship_type": "COMPARED_TO",
                    "relationship_reason": (
                        "Enterprise 5.6 candidate evaluated against current baseline."
                    ),
                },
                "parent_version_id,child_version_id,relationship_type",
            )

        client.upsert(
            "version_history_v56",
            {
                "version_id": version_id,
                "event_time": now(),
                "event_date": RUN_DATE,
                "event_key": f"CREATED:{version_no}",
                "previous_status": None,
                "new_status": "SIMULATING",
                "event_type": "CREATED",
                "event_reason": "Candidate created from v55 Promotion Request.",
                "actor": "ENTERPRISE56_EVOLUTION_ENGINE",
                "human_approval_required": True,
                "automatic_application_enabled": False,
                "evidence": {"request_id": request_id},
            },
            "event_date,event_key",
        )

        seed = stable_seed(RUN_DATE, version_no, readiness)
        annual_return_target = clamp(
            4 + readiness * 0.18,
            -5,
            25,
        )
        volatility_target = clamp(
            24 - readiness * 0.10,
            8,
            25,
        )
        returns = synthetic_returns(
            seed,
            annual_return_target,
            volatility_target,
            252,
        )

        annual_return = mean(returns) * 252 * 100
        cumulative_return = cumulative_return_pct(returns)
        sharpe = sharpe_ratio(returns)
        sortino = sortino_ratio(returns)
        max_dd = max_drawdown_pct(returns)
        win_rate = win_rate_pct(returns)
        vol = annualized_volatility_pct(returns)
        turnover = clamp(15 + (100 - readiness) * 0.5, 10, 80)
        stability = clamp(100 - vol * 2 - max_dd, 0, 100)

        run_key = f"HISTORICAL:{version_no}"
        client.upsert(
            "simulation_runs_v56",
            {
                "run_date": RUN_DATE,
                "run_key": run_key,
                "version_id": version_id,
                "baseline_version_id": baseline_id,
                "simulation_type": "HISTORICAL_REPLAY",
                "simulation_status": "COMPLETED",
                "period_start": None,
                "period_end": RUN_DATE,
                "sample_size": 252,
                "random_seed": seed,
                "configuration": {
                    "synthetic_proxy": True,
                    "annual_return_target": annual_return_target,
                    "volatility_target": volatility_target,
                },
                "paper_only": True,
                "live_trading_enabled": False,
            },
            "run_date,run_key",
        )
        run = read(
            client,
            "simulation_runs_v56",
            f"run_date=eq.{RUN_DATE}&run_key=eq.{run_key}&limit=1",
            required=True,
        )[0]
        run_id_db = str(run["id"])
        simulation_runs += 1

        pass_status = (
            "PASS"
            if sharpe >= 0.8 and max_dd <= 20
            else "WARNING"
            if sharpe >= 0.2 and max_dd <= 30
            else "FAIL"
        )
        client.upsert(
            "simulation_results_v56",
            {
                "run_id": run_id_db,
                "result_key": "PRIMARY_RESULT",
                "annual_return_pct": annual_return,
                "cumulative_return_pct": cumulative_return,
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "max_drawdown_pct": max_dd,
                "win_rate_pct": win_rate,
                "volatility_pct": vol,
                "turnover_pct": turnover,
                "stability_score": stability,
                "drawdown_recovery_days": integer(max_dd * 4, 0),
                "pass_status": pass_status,
                "result_summary": (
                    f"{version_no}: annual return {annual_return:.2f}%, "
                    f"Sharpe {sharpe:.2f}, max drawdown {max_dd:.2f}%."
                ),
                "diagnostics": {
                    "proxy_only": True,
                    "run_id": run_id,
                },
            },
            "run_id,result_key",
        )
        simulation_results += 1

        stress_scenarios = [
            ("MARKET_CRASH", -25.0),
            ("VOLATILITY_SPIKE", -12.0),
            ("LIQUIDITY_SHOCK", -10.0),
            ("CORRELATION_BREAKDOWN", -8.0),
            ("RATE_SHOCK", -6.0),
            ("REGIME_SHIFT", -9.0),
        ]
        stress_passes = []
        for scenario, shock in stress_scenarios:
            loss = abs(shock) * (1.2 - readiness / 200)
            stress_dd = max_dd + loss * 0.6
            liquidity_score = clamp(
                40 + abs(shock) * 1.5 + turnover * 0.3,
                0,
                100,
            )
            passed = stress_dd <= 35 and liquidity_score <= 80
            stress_passes.append(passed)
            client.upsert(
                "stress_tests_v56",
                {
                    "run_id": run_id_db,
                    "stress_key": scenario,
                    "stress_scenario": scenario,
                    "shock_magnitude_pct": shock,
                    "portfolio_loss_pct": loss,
                    "max_drawdown_pct": stress_dd,
                    "liquidity_impact_score": liquidity_score,
                    "recovery_days": integer(stress_dd * 3, 0),
                    "stress_status": "PASS" if passed else "FAIL",
                    "passed": passed,
                    "notes": "Paper-only proxy stress test.",
                    "diagnostics": {"synthetic_proxy": True},
                },
                "run_id,stress_key",
            )
            stress_tests += 1

        mc = monte_carlo_summary(
            stable_seed(seed, "MC"),
            annual_return_target,
            volatility_target,
            monte_carlo_iterations,
        )
        mc_pass = (
            mc["prob_loss"] <= 40
            and mc["prob_dd_breach"] <= 25
        )
        client.upsert(
            "monte_carlo_results_v56",
            {
                "run_id": run_id_db,
                "simulation_key": "MC_PRIMARY",
                "iterations": monte_carlo_iterations,
                "expected_return_pct": mc["expected"],
                "median_return_pct": mc["median"],
                "percentile_05_return_pct": mc["p05"],
                "percentile_95_return_pct": mc["p95"],
                "probability_of_loss_pct": mc["prob_loss"],
                "probability_of_drawdown_limit_breach_pct": mc[
                    "prob_dd_breach"
                ],
                "value_at_risk_pct": mc["var"],
                "expected_shortfall_pct": mc["expected_shortfall"],
                "passed": mc_pass,
                "diagnostics": {
                    "synthetic_proxy": True,
                    "seed": stable_seed(seed, "MC"),
                },
            },
            "run_id,simulation_key",
        )
        monte_carlo_runs += 1

        governance_ready = (
            request_status
            in {
                "READY_FOR_REVIEW",
                "CONFIRMED_FOR_MANUAL_PROMOTION",
            }
            or readiness_status == "READY_FOR_PAPER_CANARY"
        )
        scores = evolution_score(
            annual_return,
            sharpe,
            max_dd,
            stability,
            mc["prob_loss"],
            readiness,
            governance_ready,
        )

        recommendation = "HOLD"
        if not all(stress_passes) or not mc_pass or pass_status == "FAIL":
            recommendation = "REJECT"
        elif scores["evolution_score"] >= selection_threshold:
            recommendation = "PROMOTE_FOR_HUMAN_REVIEW"
        elif scores["evolution_score"] >= selection_threshold - 15:
            recommendation = "NEEDS_MORE_EVIDENCE"

        score_key = f"EVOLUTION:{version_no}"
        client.upsert(
            "evolution_scores_v56",
            {
                "score_date": RUN_DATE,
                "score_key": score_key,
                "version_id": version_id,
                "baseline_version_id": baseline_id,
                "return_score": scores["return_score"],
                "risk_score": scores["risk_score"],
                "stability_score": scores["stability_score"],
                "robustness_score": scores["robustness_score"],
                "promotion_score": scores["promotion_score"],
                "governance_score": scores["governance_score"],
                "evolution_score": scores["evolution_score"],
                "confidence_score": scores["confidence_score"],
                "recommendation": recommendation,
                "recommendation_reason": (
                    f"Simulation={pass_status}; "
                    f"Stress pass={all(stress_passes)}; "
                    f"Monte Carlo pass={mc_pass}."
                ),
                "human_approval_required": True,
                "automatic_promotion_enabled": False,
                "diagnostics": {
                    "run_id": run_id,
                    "source_request_id": request_id,
                },
            },
            "score_date,score_key",
        )
        evolution_scores_count += 1

        score_rows.append(
            {
                "version_id": version_id,
                "version_no": version_no,
                "evolution_score": scores["evolution_score"],
                "confidence_score": scores["confidence_score"],
                "recommendation": recommendation,
            }
        )

    score_rows.sort(
        key=lambda row: (
            row["evolution_score"],
            row["confidence_score"],
        ),
        reverse=True,
    )

    top_candidate_version = None
    top_candidate_score = None

    for rank, row in enumerate(score_rows, start=1):
        selected = (
            rank == 1
            and row["recommendation"] == "PROMOTE_FOR_HUMAN_REVIEW"
        )
        ranking_status = (
            "SELECTED_FOR_REVIEW"
            if selected
            else "REJECTED"
            if row["recommendation"] == "REJECT"
            else "RANKED"
        )

        client.upsert(
            "portfolio_rankings_v56",
            {
                "ranking_date": RUN_DATE,
                "ranking_key": f"RANK:{row['version_no']}",
                "version_id": row["version_id"],
                "rank_no": rank,
                "evolution_score": row["evolution_score"],
                "confidence_score": row["confidence_score"],
                "ranking_status": ranking_status,
                "recommendation": row["recommendation"],
                "selected_for_review": selected,
                "human_approval_required": True,
                "automatic_selection_enabled": False,
                "diagnostics": {"run_id": run_id},
            },
            "ranking_date,ranking_key",
        )
        ranked_versions += 1

        new_status = (
            "READY_FOR_REVIEW"
            if selected
            else "REJECTED"
            if row["recommendation"] == "REJECT"
            else "RANKED"
        )
        client.patch(
            "portfolio_versions_v56",
            f"id=eq.{row['version_id']}",
            {"version_status": new_status},
        )

        if selected:
            selected_for_review += 1
            top_candidate_version = row["version_no"]
            top_candidate_score = row["evolution_score"]
        elif row["recommendation"] == "REJECT":
            rejected_versions += 1
            if row["evolution_score"] < 40:
                rollback_recommendations += 1

    if top_candidate_version:
        overall_status = "READY_FOR_PROMOTION_REVIEW"
    elif versions_registered > 0:
        overall_status = "WARNING"
        warnings.append("NO_CANDIDATE_SELECTED_FOR_REVIEW")
    else:
        overall_status = "CRITICAL"

    summary = (
        f"Enterprise 5.6 registered {versions_registered} candidate(s), "
        f"completed {simulation_runs} simulation run(s), "
        f"{stress_tests} stress test(s), "
        f"{monte_carlo_runs} Monte Carlo result(s), "
        f"and selected {selected_for_review} candidate(s) for human review."
    )

    client.upsert(
        "evolution_metrics_v56",
        {
            "metric_date": RUN_DATE,
            "versions_registered": versions_registered + 1,
            "simulation_runs": simulation_runs,
            "simulation_results": simulation_results,
            "stress_tests": stress_tests,
            "monte_carlo_runs": monte_carlo_runs,
            "evolution_scores": evolution_scores_count,
            "ranked_versions": ranked_versions,
            "selected_for_review": selected_for_review,
            "rejected_versions": rejected_versions,
            "rollback_recommendations": rollback_recommendations,
            "automatic_promotions": 0,
            "automatic_rollbacks": 0,
            "average_evolution_score": (
                mean(r["evolution_score"] for r in score_rows)
                if score_rows
                else 0
            ),
            "average_confidence_score": (
                mean(r["confidence_score"] for r in score_rows)
                if score_rows
                else 0
            ),
            "diagnostics": {
                "run_id": run_id,
                "engine_version": ENGINE_VERSION,
            },
        },
        "metric_date",
    )

    client.upsert(
        "evolution_status_v56",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_baseline_version": baseline_no,
            "current_top_candidate_version": top_candidate_version,
            "current_top_candidate_score": top_candidate_score,
            "versions_registered": versions_registered + 1,
            "simulation_runs": simulation_runs,
            "simulation_results": simulation_results,
            "stress_tests": stress_tests,
            "monte_carlo_runs": monte_carlo_runs,
            "evolution_scores": evolution_scores_count,
            "ranked_versions": ranked_versions,
            "selected_for_review": selected_for_review,
            "rejected_versions": rejected_versions,
            "rollback_recommendations": rollback_recommendations,
            "human_approval_required": True,
            "automatic_baseline_promotion_enabled": False,
            "automatic_portfolio_application_enabled": False,
            "automatic_live_deployment_enabled": False,
            "automatic_rollback_execution_enabled": False,
            "live_trading_enabled": False,
            "broker_submission_enabled": False,
            "blockers": blockers,
            "warnings": warnings,
            "summary": summary,
            "diagnostics": {
                "run_id": run_id,
                "engine_version": ENGINE_VERSION,
                "thresholds": {
                    "monte_carlo_iterations": monte_carlo_iterations,
                    "selection_threshold": selection_threshold,
                    "max_candidates": max_candidates,
                },
            },
        },
        "status_date",
    )

    if requests and versions_registered == 0:
        raise RuntimeError(
            "v55 promotion requests exist but v56 created zero portfolio versions."
        )

    print(summary)
    print(f"Enterprise 5.6 Evolution Intelligence status: {overall_status}")


if __name__ == "__main__":
    main()
