from __future__ import annotations

import math
import os
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def n(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback


def safe_get(client, table: str, query: str) -> list[dict[str, Any]]:
    try:
        rows = client.get(table, query)
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        print(f"Optional source unavailable: {table}: {exc}")
        return []


def latest(client, table: str, field: str, where: str = "") -> dict[str, Any]:
    query = f"{where}&order={field}.desc&limit=1" if where else f"order={field}.desc&limit=1"
    rows = safe_get(client, table, query)
    return rows[0] if rows else {}


def label_from_plan(plan: dict[str, Any], order_count: int) -> tuple[str, float, str]:
    status = str(plan.get("plan_status") or "UNKNOWN")
    decision = str(plan.get("final_decision") or "BLOCK")

    if status == "BLOCKED":
        if decision == "BLOCK":
            return "CORRECT", 90.0, "Council blocked and execution plan was blocked."
        return "PARTIALLY_CORRECT", 55.0, "Execution layer blocked a non-block Council decision."

    if status == "APPROVED_FOR_PAPER" and order_count > 0:
        if decision in ("BUY", "STRONG_BUY", "HOLD", "REDUCE", "AVOID"):
            return "PARTIALLY_CORRECT", 65.0, "Decision produced an approved Paper execution plan."
        return "INCORRECT", 25.0, "Blocked decision unexpectedly produced an approved plan."

    return "INSUFFICIENT_DATA", 0.0, "No realized execution outcome is available yet."


def direction_correctness(direction: str, outcome_label: str) -> float:
    if outcome_label == "INSUFFICIENT_DATA":
        return 0.0
    if outcome_label == "CORRECT":
        return 100.0
    if outcome_label == "PARTIALLY_CORRECT":
        return 65.0
    if outcome_label == "INCORRECT":
        return 0.0
    return 0.0


def main() -> None:
    client = SupabaseRestClient()
    cycle_id = str(uuid.uuid4())

    client.upsert(
        "learning_cycles_v53",
        {
            "cycle_date": RUN_DATE,
            "cycle_status": "RUNNING",
            "decisions_evaluated": 0,
            "agent_votes_evaluated": 0,
            "strategies_evaluated": 0,
            "regimes_evaluated": 0,
            "proposals_generated": 0,
            "insufficient_data_count": 0,
            "average_decision_score": 0,
            "average_agent_reliability": 0,
            "average_calibration_score": 0,
            "blockers": [],
            "warnings": [],
            "summary": "Enterprise 5.3 learning cycle is running.",
            "diagnostics": {"cycle_id": cycle_id},
            "started_at": now(),
        },
        "cycle_date",
    )

    decisions = safe_get(
        client,
        "decision_council_v51",
        "order=decision_date.desc,created_at.desc&limit=100",
    )
    if not decisions:
        raise SystemExit("No decision_council_v51 records found")

    decision_scores = []
    calibration_scores = []
    agent_scores: dict[str, list[float]] = defaultdict(list)
    agent_confidences: dict[str, list[float]] = defaultdict(list)
    strategy_counts: dict[tuple[str, str], int] = defaultdict(int)

    decisions_evaluated = 0
    votes_evaluated = 0
    strategies_evaluated = 0
    regimes_evaluated = 0
    proposals_generated = 0
    observations_created = 0
    insufficient = 0
    correct = partial = incorrect = 0
    warnings = []

    for decision in decisions:
        decision_id = str(decision["id"])
        plans = safe_get(
            client,
            "execution_plans_v52",
            f"council_decision_id=eq.{decision_id}&order=created_at.desc&limit=100",
        )

        if not plans:
            label = "INSUFFICIENT_DATA"
            decision_score = 0.0
            realized_outcome = "NO_EXECUTION_PLAN"
            insufficient += 1
            plans = [None]
        else:
            plan = plans[0]
            orders = safe_get(
                client,
                "execution_orders_v52",
                f"plan_id=eq.{plan['id']}&limit=1000",
            )
            label, decision_score, realized_outcome = label_from_plan(plan, len(orders))

        if label == "CORRECT":
            correct += 1
        elif label == "PARTIALLY_CORRECT":
            partial += 1
        elif label == "INCORRECT":
            incorrect += 1

        decision_confidence = n(decision.get("final_confidence"))
        calibration_error = abs(decision_confidence - decision_score)
        calibration_score = max(0.0, 100 - calibration_error)

        client.upsert(
            "decision_outcomes_v53",
            {
                "outcome_date": RUN_DATE,
                "council_decision_id": decision_id,
                "execution_plan_id": plans[0].get("id") if plans[0] else None,
                "portfolio_id": plans[0].get("portfolio_id") if plans[0] else None,
                "original_decision": decision.get("final_decision"),
                "realized_outcome": realized_outcome,
                "outcome_label": label,
                "realized_return_pct": None,
                "realized_drawdown_pct": None,
                "realized_volatility_pct": None,
                "horizon_days": 0,
                "decision_score": decision_score,
                "confidence_calibration_error": calibration_error,
                "evidence": {
                    "decision_status": decision.get("decision_status"),
                    "plan_status": plans[0].get("plan_status") if plans[0] else None,
                    "paper_only": True,
                },
            },
            "outcome_date,council_decision_id,portfolio_id",
        )

        client.insert(
            "learning_observations_v53",
            {
                "observation_date": RUN_DATE,
                "observation_type": "DECISION",
                "source_module": "decision_council_v51",
                "source_record_id": decision_id,
                "portfolio_id": plans[0].get("portfolio_id") if plans[0] else None,
                "market_regime": decision.get("market_regime"),
                "observed_value": decision_score,
                "benchmark_value": decision_confidence,
                "outcome_label": label,
                "confidence": decision_confidence,
                "evidence": {"realized_outcome": realized_outcome},
                "notes": "Enterprise 5.3 decision evaluation.",
            },
        )
        observations_created += 1
        decisions_evaluated += 1
        decision_scores.append(decision_score)
        calibration_scores.append(calibration_score)

        selected_strategy = str(decision.get("selected_strategy") or "")
        if selected_strategy:
            strategy_counts[(selected_strategy, str(decision.get("market_regime") or "UNKNOWN"))] += 1

        votes = safe_get(
            client,
            "agent_votes_v51",
            f"session_id=eq.{decision.get('session_id')}&limit=100",
        )
        for vote in votes:
            key = str(vote.get("agent_key"))
            confidence = n(vote.get("confidence"))
            correctness = direction_correctness(
                str(vote.get("vote_direction")),
                label,
            )
            error = abs(confidence - correctness)
            veto_correct = None
            if bool(vote.get("veto")):
                veto_correct = label in ("CORRECT", "PARTIALLY_CORRECT")

            client.upsert(
                "agent_feedback_v53",
                {
                    "feedback_date": RUN_DATE,
                    "agent_key": key,
                    "session_id": decision.get("session_id"),
                    "vote_id": vote.get("id"),
                    "vote_direction": vote.get("vote_direction"),
                    "vote_confidence": confidence,
                    "outcome_label": label,
                    "correctness_score": correctness,
                    "calibration_error": error,
                    "veto_was_correct": veto_correct,
                    "regime_context": decision.get("market_regime"),
                    "feedback_summary": (
                        f"Agent {key} received {correctness:.2f} correctness "
                        f"with calibration error {error:.2f}."
                    ),
                    "evidence": {
                        "council_decision_id": decision_id,
                        "final_decision": decision.get("final_decision"),
                    },
                },
                "feedback_date,vote_id",
            )
            votes_evaluated += 1
            agent_scores[key].append(correctness)
            agent_confidences[key].append(confidence)

    registry = safe_get(
        client,
        "agent_registry_v51",
        "enabled=eq.true&agent_key=neq.DECISION_COUNCIL&order=execution_order.asc&limit=100",
    )

    reliability_values = []
    for agent in registry:
        key = str(agent["agent_key"])
        scores = agent_scores.get(key, [])
        confidences = agent_confidences.get(key, [])
        evidence_count = len(scores)
        current_weight = n(agent.get("voting_weight"), 1)

        if evidence_count == 0:
            reliability = 50.0
            avg_confidence = 0.0
            calibration_error = 50.0
            proposed_weight = current_weight
            reason = "Insufficient evidence; retain current voting weight."
            status = "INSUFFICIENT_DATA"
        else:
            reliability = mean(scores)
            avg_confidence = mean(confidences)
            calibration_error = abs(avg_confidence - reliability)
            status = (
                "WELL_CALIBRATED" if calibration_error <= 10
                else "OVERCONFIDENT" if avg_confidence > reliability
                else "UNDERCONFIDENT"
            )
            adjustment_factor = max(-0.10, min(0.10, (reliability - 50) / 500))
            proposed_weight = max(0.25, min(2.0, current_weight * (1 + adjustment_factor)))
            reason = (
                f"Reliability {reliability:.2f}, confidence {avg_confidence:.2f}, "
                f"calibration error {calibration_error:.2f}; proposal only."
            )

        calibration_score = max(0.0, 100 - calibration_error)
        reliability_values.append(reliability)

        client.upsert(
            "confidence_calibration_v53",
            {
                "calibration_date": RUN_DATE,
                "subject_type": "AGENT",
                "subject_key": key,
                "observations": evidence_count,
                "average_confidence": avg_confidence,
                "observed_accuracy": reliability,
                "calibration_error": calibration_error,
                "calibration_status": status,
                "suggested_adjustment": proposed_weight - current_weight,
                "evidence": {"scores": scores},
            },
            "calibration_date,subject_type,subject_key",
        )

        client.upsert(
            "agent_weight_adjustments_v53",
            {
                "proposal_date": RUN_DATE,
                "agent_key": key,
                "current_weight": current_weight,
                "proposed_weight": proposed_weight,
                "adjustment_pct": (
                    0 if current_weight == 0
                    else (proposed_weight - current_weight) / current_weight * 100
                ),
                "evidence_count": evidence_count,
                "reliability_score": reliability,
                "calibration_score": calibration_score,
                "proposal_status": "PROPOSED",
                "adjustment_reason": reason,
                "evidence": {
                    "average_confidence": avg_confidence,
                    "calibration_status": status,
                },
                "auto_apply_enabled": False,
            },
            "proposal_date,agent_key",
        )
        proposals_generated += 1

    for (strategy_key, regime), selections in strategy_counts.items():
        client.upsert(
            "strategy_outcomes_v53",
            {
                "outcome_date": RUN_DATE,
                "strategy_key": strategy_key,
                "portfolio_id": None,
                "market_regime": regime,
                "selections": selections,
                "approvals": selections,
                "rejections": 0,
                "realized_return_pct": None,
                "max_drawdown_pct": None,
                "volatility_pct": None,
                "win_rate": 0,
                "quality_score": 50,
                "outcome_label": "INSUFFICIENT_DATA",
                "evidence": {"source": "decision_council_v51"},
            },
            "outcome_date,strategy_key,portfolio_id,market_regime",
        )
        strategies_evaluated += 1
        insufficient += 1

    regime = latest(client, "market_regime_ai_v46", "regime_date")
    if regime:
        predicted = str(regime.get("market_regime") or "UNKNOWN")
        confidence = n(regime.get("regime_confidence"), 0)
        client.upsert(
            "regime_outcomes_v53",
            {
                "outcome_date": RUN_DATE,
                "regime_date": regime.get("regime_date") or RUN_DATE,
                "predicted_regime": predicted,
                "predicted_confidence": confidence,
                "observed_regime": "UNKNOWN",
                "regime_match": None,
                "accuracy_score": 0,
                "realized_market_return_pct": None,
                "realized_market_volatility_pct": None,
                "outcome_label": "INSUFFICIENT_DATA",
                "evidence": {"source_record": regime.get("id")},
            },
            "outcome_date,regime_date,predicted_regime",
        )
        regimes_evaluated = 1
        insufficient += 1

    average_decision = mean(decision_scores) if decision_scores else 0
    average_reliability = mean(reliability_values) if reliability_values else 0
    average_calibration = mean(calibration_scores) if calibration_scores else 0

    overall_status = (
        "WARNING" if insufficient > 0
        else "PASS"
    )
    summary = (
        f"Enterprise 5.3 evaluated {decisions_evaluated} decision(s), "
        f"{votes_evaluated} Agent vote(s), generated {proposals_generated} "
        f"weight proposal(s), with {insufficient} insufficient-data item(s)."
    )

    client.patch(
        "learning_cycles_v53",
        f"cycle_date=eq.{RUN_DATE}",
        {
            "cycle_status": overall_status,
            "decisions_evaluated": decisions_evaluated,
            "agent_votes_evaluated": votes_evaluated,
            "strategies_evaluated": strategies_evaluated,
            "regimes_evaluated": regimes_evaluated,
            "proposals_generated": proposals_generated,
            "insufficient_data_count": insufficient,
            "average_decision_score": average_decision,
            "average_agent_reliability": average_reliability,
            "average_calibration_score": average_calibration,
            "blockers": [],
            "warnings": (
                ["REALIZED_MARKET_AND_TRADE_OUTCOMES_NOT_AVAILABLE"]
                if insufficient else []
            ),
            "summary": summary,
            "diagnostics": {
                "cycle_id": cycle_id,
                "correct": correct,
                "partial": partial,
                "incorrect": incorrect,
            },
            "completed_at": now(),
        },
    )

    client.upsert(
        "learning_metrics_v53",
        {
            "metric_date": RUN_DATE,
            "total_observations": observations_created,
            "correct_decisions": correct,
            "partial_decisions": partial,
            "incorrect_decisions": incorrect,
            "insufficient_data": insufficient,
            "agent_feedback_records": votes_evaluated,
            "weight_proposals": proposals_generated,
            "strategy_outcomes": strategies_evaluated,
            "regime_outcomes": regimes_evaluated,
            "average_decision_score": average_decision,
            "average_agent_accuracy": average_reliability,
            "average_calibration_error": (
                100 - average_calibration if calibration_scores else 0
            ),
            "diagnostics": {
                "automatic_updates": False,
                "model_retraining": False,
            },
        },
        "metric_date",
    )

    client.upsert(
        "learning_status_v53",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_cycle_id": cycle_id,
            "decisions_evaluated": decisions_evaluated,
            "agent_votes_evaluated": votes_evaluated,
            "strategies_evaluated": strategies_evaluated,
            "regimes_evaluated": regimes_evaluated,
            "proposals_generated": proposals_generated,
            "observations_created": observations_created,
            "insufficient_data_count": insufficient,
            "average_decision_score": average_decision,
            "average_agent_reliability": average_reliability,
            "average_calibration_score": average_calibration,
            "automatic_weight_updates_enabled": False,
            "automatic_model_retraining_enabled": False,
            "live_trading_enabled": False,
            "blockers": [],
            "warnings": (
                ["REALIZED_MARKET_AND_TRADE_OUTCOMES_NOT_AVAILABLE"]
                if insufficient else []
            ),
            "summary": summary,
            "diagnostics": {
                "cycle_id": cycle_id,
                "paper_only": True,
            },
        },
        "status_date",
    )

    print(summary)
    print(f"Enterprise 5.3 Continuous Learning status: {overall_status}")


if __name__ == "__main__":
    main()
