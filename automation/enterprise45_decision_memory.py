from __future__ import annotations

import math
import os
from datetime import date, timedelta
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
OUTCOME_HORIZON_DAYS = int(os.environ.get("ENTERPRISE45_OUTCOME_DAYS", "1"))

def n(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

def latest(client: SupabaseRestClient, table: str, field: str, where: str = "") -> dict[str, Any]:
    query = f"{where}&order={field}.desc&limit=1" if where else f"order={field}.desc&limit=1"
    rows = client.get(table, query)
    return rows[0] if rows else {}

def main() -> None:
    client = SupabaseRestClient()
    portfolios = client.get(
        "enterprise_portfolios_v40",
        "lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100",
    )
    regime_row = latest(client, "market_regimes_v40", "regime_date")
    regime = str(regime_row.get("regime") or "UNKNOWN")
    captured = 0
    blockers: list[str] = []

    due_date = (
        date.fromisoformat(RUN_DATE) + timedelta(days=OUTCOME_HORIZON_DAYS)
    ).isoformat()

    for portfolio in portfolios:
        pid = str(portfolio["id"])

        decision = latest(
            client,
            "explainable_decisions_v43",
            "decision_date",
            f"portfolio_id=eq.{pid}",
        )
        thesis = latest(
            client,
            "investment_theses_v43",
            "thesis_date",
            f"portfolio_id=eq.{pid}",
        )
        risk = latest(
            client,
            "portfolio_risk_v41",
            "risk_date",
            f"portfolio_id=eq.{pid}",
        )
        compat = latest(
            client,
            "compat_portfolios_v40",
            "latest_snapshot_date",
            f"portfolio_id=eq.{pid}",
        )

        if not decision:
            blockers.append(f"portfolio:{portfolio.get('portfolio_key')}:no_v43_decision")
            continue

        baseline_equity = n(
            compat.get("latest_equity"),
            n(portfolio.get("starting_cash"), 1_000_000),
        )

        source_decision_id = str(decision["id"])
        source_thesis_id = str(thesis["id"]) if thesis.get("id") else None
        recommendation = str(decision.get("final_action") or "HOLD")
        confidence = n(decision.get("confidence"), 50)

        supporting = decision.get("supporting_reasons")
        if not isinstance(supporting, list):
            supporting = []

        rationale = str(decision.get("explanation") or "")
        if supporting:
            rationale = f"{rationale} Supporting: {' | '.join(str(x) for x in supporting[:3])}"

        client.upsert(
            "decision_memory_v45",
            {
                "decision_date": RUN_DATE,
                "portfolio_id": pid,
                "strategy_id": None,
                "source_decision_id": source_decision_id,
                "source_thesis_id": source_thesis_id,
                "symbol": "PORTFOLIO",
                "recommendation": recommendation,
                "confidence": confidence,
                "rationale": rationale or "Enterprise 4.3 committee decision.",
                "market_regime": regime,
                "risk_status": str(risk.get("risk_status") or "UNKNOWN"),
                "expected_return_pct": n(thesis.get("expected_return_pct")),
                "downside_risk_pct": n(
                    thesis.get("downside_risk_pct"),
                    n(risk.get("expected_shortfall_pct"), 0),
                ),
                "baseline_equity": baseline_equity,
                "baseline_date": RUN_DATE,
                "evaluation_due_date": due_date,
                "realized_return_pct": None,
                "outcome_status": "OPEN",
                "learning_score": 0,
                "lesson_summary": "Awaiting evaluation.",
                "feature_snapshot": {
                    "portfolio_key": portfolio.get("portfolio_key"),
                    "risk_score": n(risk.get("risk_score")),
                    "market_regime": regime,
                    "approved_for_paper": bool(decision.get("approved_for_paper")),
                    "approved_for_live": False,
                },
            },
            "decision_date,portfolio_id,symbol,source_decision_id",
        )
        captured += 1

    print(f"Enterprise 4.5 captured {captured} decision memory record(s).")
    if blockers:
        print(f"Blockers: {blockers}")

if __name__ == "__main__":
    main()
