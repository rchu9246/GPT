from __future__ import annotations

import math
import os
from datetime import date
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

def n(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def main() -> None:
    client = SupabaseRestClient()
    strategies = client.get(
        "enterprise_strategies_v40",
        "enabled=eq.true&paper_approved=eq.true&limit=100",
    )

    feedback = client.get(
        "learning_feedback_v45",
        "order=feedback_date.desc&limit=5000",
    )
    memories = client.get(
        "decision_memory_v45",
        "outcome_status=neq.OPEN&order=decision_date.desc&limit=5000",
    )

    ratings = 0

    # Foundation rating distributes portfolio-level learning evidence to all
    # approved PAPER strategies. Later releases can attach strategy_id directly.
    wins = sum(1 for row in memories if row.get("outcome_status") == "WIN")
    losses = sum(1 for row in memories if row.get("outcome_status") == "LOSS")
    neutrals = sum(1 for row in memories if row.get("outcome_status") == "NEUTRAL")
    sample_count = wins + losses + neutrals
    win_rate = wins / sample_count * 100 if sample_count else 0

    returns = [n(row.get("actual_return_pct")) for row in feedback]
    errors = [abs(n(row.get("prediction_error_pct"))) for row in feedback]
    confidences = [n(row.get("confidence_after"), 50) for row in feedback]

    avg_return = sum(returns) / len(returns) if returns else 0
    avg_error = sum(errors) / len(errors) if errors else 50
    avg_confidence = sum(confidences) / len(confidences) if confidences else 50
    prediction_accuracy = clamp(100 - avg_error * 10, 0, 100)
    calibration = clamp(100 - abs(avg_confidence - win_rate), 0, 100)

    for strategy in strategies:
        key = str(strategy.get("strategy_key") or strategy["id"])
        marketplace = client.get(
            "quant_strategy_marketplace",
            f"strategy_key=eq.{key}&order=updated_at.desc&limit=1",
        )
        quality = n(marketplace[0].get("quality_score"), 50) if marketplace else 50
        risk_adjusted = clamp(quality + avg_return * 3 - losses * 2, 0, 100)

        overall = clamp(
            win_rate * 0.35
            + prediction_accuracy * 0.25
            + calibration * 0.15
            + risk_adjusted * 0.25,
            0,
            100,
        )

        if sample_count < 5:
            status = "INSUFFICIENT_DATA"
            action = "COLLECT_MORE_DATA"
        elif overall >= 75:
            status = "PROMISING"
            action = "PROMOTE_FOR_PAPER_REVIEW"
        elif overall <= 30:
            status = "WEAK"
            action = "REVIEW_OR_RETIRE"
        else:
            status = "STABLE"
            action = "KEEP_PAPER"

        client.upsert(
            "strategy_rating_v45",
            {
                "rating_date": RUN_DATE,
                "strategy_id": strategy["id"],
                "strategy_key": key,
                "sample_count": sample_count,
                "wins": wins,
                "losses": losses,
                "neutrals": neutrals,
                "win_rate": win_rate,
                "prediction_accuracy": prediction_accuracy,
                "average_return_pct": avg_return,
                "average_confidence": avg_confidence,
                "calibration_score": calibration,
                "risk_adjusted_score": risk_adjusted,
                "overall_score": overall,
                "rating_status": status,
                "recommended_action": action,
                "diagnostics": {
                    "foundation_mode": True,
                    "quality_score": quality,
                    "portfolio_level_feedback": True,
                },
            },
            "rating_date,strategy_key",
        )
        ratings += 1

    current_status = client.get(
        "learning_cycle_status_v45",
        f"status_date=eq.{RUN_DATE}&limit=1",
    )
    if current_status:
        client.patch(
            "learning_cycle_status_v45",
            f"status_date=eq.{RUN_DATE}",
            {"strategy_ratings": ratings},
        )

    print(f"Enterprise 4.5 generated {ratings} strategy rating(s).")

if __name__ == "__main__":
    main()
