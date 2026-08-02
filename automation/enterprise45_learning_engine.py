from __future__ import annotations

import math
import os
from datetime import date, datetime, timezone
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
WIN_THRESHOLD = float(os.environ.get("ENTERPRISE45_WIN_THRESHOLD", "0.25"))
LOSS_THRESHOLD = float(os.environ.get("ENTERPRISE45_LOSS_THRESHOLD", "-0.25"))

def n(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def latest(client: SupabaseRestClient, table: str, field: str, where: str = "") -> dict[str, Any]:
    query = f"{where}&order={field}.desc&limit=1" if where else f"order={field}.desc&limit=1"
    rows = client.get(table, query)
    return rows[0] if rows else {}

def classify(recommendation: str, realized_return: float) -> str:
    signed_return = realized_return
    if recommendation == "SELL":
        signed_return *= -1
    elif recommendation == "HOLD":
        signed_return = -abs(realized_return) * 0.20

    if signed_return >= WIN_THRESHOLD:
        return "WIN"
    if signed_return <= LOSS_THRESHOLD:
        return "LOSS"
    return "NEUTRAL"

def main() -> None:
    client = SupabaseRestClient()
    open_rows = client.get(
        "decision_memory_v45",
        f"outcome_status=eq.OPEN&evaluation_due_date=lte.{RUN_DATE}&order=decision_date.asc&limit=500",
    )

    evaluated = wins = losses = neutrals = feedback_count = 0
    blockers: list[str] = []

    for memory in open_rows:
        memory_id = str(memory["id"])
        portfolio_id = str(memory["portfolio_id"])

        compat = latest(
            client,
            "compat_portfolios_v40",
            "latest_snapshot_date",
            f"portfolio_id=eq.{portfolio_id}",
        )
        current_equity = n(compat.get("latest_equity"))
        baseline_equity = n(memory.get("baseline_equity"))

        if baseline_equity <= 0 or current_equity <= 0:
            blockers.append(f"decision:{memory_id}:missing_equity")
            continue

        realized_return = (current_equity / baseline_equity - 1) * 100
        recommendation = str(memory.get("recommendation") or "HOLD")
        outcome = classify(recommendation, realized_return)

        if outcome == "WIN":
            wins += 1
            target_confidence = 80
            reward, penalty = abs(realized_return), 0
            score_delta = min(8, 2 + abs(realized_return))
        elif outcome == "LOSS":
            losses += 1
            target_confidence = 30
            reward, penalty = 0, abs(realized_return)
            score_delta = -min(10, 3 + abs(realized_return))
        else:
            neutrals += 1
            target_confidence = 55
            reward, penalty = 0.25, 0.25
            score_delta = 0

        confidence_before = n(memory.get("confidence"), 50)
        confidence_after = clamp(
            confidence_before * 0.75 + target_confidence * 0.25,
            35,
            95,
        )
        confidence_delta = confidence_after - confidence_before
        expected_return = n(memory.get("expected_return_pct"))
        prediction_error = realized_return - expected_return

        lesson = (
            f"{recommendation} under {memory.get('market_regime')} was {outcome}; "
            f"expected {expected_return:.2f}%, actual {realized_return:.2f}%, "
            f"error {prediction_error:.2f}%."
        )

        client.upsert(
            "learning_feedback_v45",
            {
                "feedback_date": RUN_DATE,
                "decision_memory_id": memory_id,
                "portfolio_id": portfolio_id,
                "strategy_id": memory.get("strategy_id"),
                "prediction": recommendation,
                "expected_return_pct": expected_return,
                "actual_return_pct": realized_return,
                "prediction_error_pct": prediction_error,
                "outcome_status": outcome,
                "reward_value": reward,
                "penalty_value": penalty,
                "confidence_before": confidence_before,
                "confidence_after": confidence_after,
                "confidence_delta": confidence_delta,
                "strategy_score_delta": score_delta,
                "lesson": lesson,
                "evidence": {
                    "baseline_equity": baseline_equity,
                    "current_equity": current_equity,
                    "baseline_date": memory.get("baseline_date"),
                    "evaluation_date": RUN_DATE,
                },
            },
            "feedback_date,decision_memory_id",
        )

        learning_score = clamp(
            50 + score_delta * 4 - abs(prediction_error) * 0.5,
            0,
            100,
        )

        client.patch(
            "decision_memory_v45",
            f"id=eq.{memory_id}",
            {
                "realized_return_pct": realized_return,
                "outcome_status": outcome,
                "learning_score": learning_score,
                "lesson_summary": lesson,
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        evaluated += 1
        feedback_count += 1

    open_count = len(client.get(
        "decision_memory_v45",
        "outcome_status=eq.OPEN&select=id&limit=1000",
    ))

    overall = "WARNING" if blockers or losses else "PASS"
    summary = (
        f"Evaluated {evaluated} decision(s): {wins} win(s), {losses} loss(es), "
        f"{neutrals} neutral(s); {open_count} open decision(s)."
    )

    client.upsert(
        "learning_cycle_status_v45",
        {
            "status_date": RUN_DATE,
            "overall_status": overall,
            "decisions_captured": 0,
            "decisions_evaluated": evaluated,
            "open_decisions": open_count,
            "wins": wins,
            "losses": losses,
            "neutrals": neutrals,
            "feedback_records": feedback_count,
            "strategy_ratings": 0,
            "live_learning_enabled": False,
            "live_trading_enabled": False,
            "blockers": blockers,
            "summary": summary,
        },
        "status_date",
    )

    print(summary)
    if blockers:
        print(f"Blockers: {blockers}")

if __name__ == "__main__":
    main()
