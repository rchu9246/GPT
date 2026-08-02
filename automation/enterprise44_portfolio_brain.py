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
    strategies = client.get(
        "enterprise_strategies_v40",
        "enabled=eq.true&paper_approved=eq.true&limit=100",
    )
    regime_row = latest(client, "market_regimes_v40", "regime_date")
    regime = str(regime_row.get("regime") or "UNKNOWN")

    memories_captured = 0
    replays_completed = 0
    win_patterns_found = 0
    mistake_patterns_found = 0
    calibrations_generated = 0
    evolutions_proposed = 0
    blockers: list[str] = []

    for portfolio in portfolios:
        pid = str(portfolio["id"])
        account = str(portfolio.get("account_name") or "paper-main")

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
        proposal = latest(
            client,
            "rebalance_proposals_v42",
            "proposal_date",
            f"portfolio_id=eq.{pid}",
        )

        if not decision:
            blockers.append(f"portfolio:{portfolio.get('portfolio_key')}:no_decision")
            continue

        original_confidence = n(decision.get("confidence"), 50)
        action = str(decision.get("final_action") or "HOLD")
        risk_status = str(risk.get("risk_status") or "UNKNOWN")
        expected_return = n(thesis.get("expected_return_pct"))
        downside = n(thesis.get("downside_risk_pct"), n(risk.get("expected_shortfall_pct"), 4))
        source_decision_id = str(decision["id"])

        memory = client.upsert(
            "decision_memory_v44",
            {
                "memory_date": RUN_DATE,
                "portfolio_id": pid,
                "strategy_id": None,
                "source_decision_id": source_decision_id,
                "symbol": "PORTFOLIO",
                "decision_action": action,
                "original_confidence": original_confidence,
                "market_regime": regime,
                "risk_status": risk_status,
                "expected_return_pct": expected_return,
                "downside_risk_pct": downside,
                "realized_return_pct": None,
                "outcome_status": "PENDING",
                "lesson_type": None,
                "lesson_summary": "Awaiting future realized performance.",
                "feature_snapshot": {
                    "risk_score": n(risk.get("risk_score")),
                    "proposal_status": proposal.get("proposal_status"),
                    "regime": regime,
                },
                "retained_weight": 1,
            },
            "memory_date,portfolio_id,symbol,source_decision_id",
        )
        memory_id = str(memory[0]["id"]) if memory else None
        memories_captured += 1

        # Foundation replay uses expected return and risk to produce a deterministic proxy outcome.
        simulated_return = expected_return - downside * 0.35
        if action == "SELL":
            simulated_return *= -1
        if action == "HOLD":
            simulated_return *= 0.25

        mfe = max(0, simulated_return + abs(expected_return) * 0.4)
        mae = min(0, simulated_return - downside * 0.5)
        outcome_class = (
            "WIN" if simulated_return > 1
            else "LOSS" if simulated_return < -1
            else "NEUTRAL"
        )

        client.upsert(
            "trade_replay_v44",
            {
                "replay_date": RUN_DATE,
                "portfolio_id": pid,
                "source_memory_id": memory_id,
                "symbol": "PORTFOLIO",
                "original_action": action,
                "original_confidence": original_confidence,
                "original_target_weight": n(thesis.get("recommended_weight_pct")),
                "simulated_entry_price": 100,
                "simulated_exit_price": 100 * (1 + simulated_return / 100),
                "simulated_return_pct": simulated_return,
                "max_favorable_excursion_pct": mfe,
                "max_adverse_excursion_pct": mae,
                "replay_status": "COMPLETED",
                "outcome_class": outcome_class,
                "replay_notes": (
                    "Foundation replay uses expected return, downside risk and "
                    "committee action. It is not a historical market backtest."
                ),
                "diagnostics": {
                    "method": "decision_proxy_replay",
                    "expected_return": expected_return,
                    "downside": downside,
                },
            },
            "replay_date,source_memory_id,symbol",
        )
        replays_completed += 1

        lesson_type = "WIN_PATTERN" if outcome_class == "WIN" else "MISTAKE_PATTERN" if outcome_class == "LOSS" else "NEUTRAL_PATTERN"
        lesson = (
            f"{action} under {regime} produced proxy return {simulated_return:.2f}% "
            f"with confidence {original_confidence:.1f}%."
        )
        pattern_key = f"{regime.lower()}-{action.lower()}-{lesson_type.lower()}"

        existing_pattern = client.get(
            "learning_patterns_v44",
            f"pattern_date=eq.{RUN_DATE}&pattern_key=eq.{pattern_key}&portfolio_id=eq.{pid}&limit=1",
        )
        sample_count = 1
        if existing_pattern:
            sample_count = int(existing_pattern[0].get("sample_count") or 0) + 1

        success_rate = 100 if outcome_class == "WIN" else 0 if outcome_class == "LOSS" else 50
        pattern_confidence = clamp(40 + sample_count * 8 + abs(simulated_return) * 2, 0, 95)

        client.upsert(
            "learning_patterns_v44",
            {
                "pattern_date": RUN_DATE,
                "pattern_key": pattern_key,
                "pattern_type": lesson_type,
                "portfolio_id": pid,
                "strategy_id": None,
                "market_regime": regime,
                "sample_count": sample_count,
                "success_rate": success_rate,
                "average_return_pct": simulated_return,
                "average_drawdown_pct": abs(mae),
                "confidence_score": pattern_confidence,
                "pattern_status": "ACTIVE",
                "conditions": {
                    "action": action,
                    "risk_status": risk_status,
                    "regime": regime,
                },
                "lesson": lesson,
                "recommended_adjustment": {
                    "confidence_delta": 5 if outcome_class == "WIN" else -8 if outcome_class == "LOSS" else 0,
                    "weight_multiplier": 1.05 if outcome_class == "WIN" else 0.80 if outcome_class == "LOSS" else 1.0,
                },
            },
            "pattern_date,pattern_key,portfolio_id",
        )

        if outcome_class == "WIN":
            win_patterns_found += 1
        elif outcome_class == "LOSS":
            mistake_patterns_found += 1

        # Confidence calibration
        target_reliability = 80 if outcome_class == "WIN" else 30 if outcome_class == "LOSS" else 55
        calibrated = clamp(
            original_confidence * 0.70 + target_reliability * 0.30,
            35,
            95,
        )
        calibration_error = abs(original_confidence - target_reliability)
        reliability = clamp(100 - calibration_error, 0, 100)

        client.upsert(
            "confidence_calibration_v44",
            {
                "calibration_date": RUN_DATE,
                "portfolio_id": pid,
                "strategy_id": None,
                "original_confidence": original_confidence,
                "calibrated_confidence": calibrated,
                "reliability_score": reliability,
                "sample_count": sample_count,
                "win_rate": success_rate,
                "average_error": calibration_error,
                "calibration_status": "CALIBRATED",
                "calibration_curve": {
                    "original": original_confidence,
                    "target_reliability": target_reliability,
                    "calibrated": calibrated,
                },
                "rationale": (
                    f"Confidence adjusted using {outcome_class} replay feedback."
                ),
            },
            "calibration_date,portfolio_id,strategy_id",
        )
        calibrations_generated += 1

        client.patch(
            "decision_memory_v44",
            f"id=eq.{memory_id}",
            {
                "realized_return_pct": simulated_return,
                "outcome_status": outcome_class,
                "lesson_type": lesson_type,
                "lesson_summary": lesson,
                "evaluated_at": RUN_DATE + "T00:00:00Z",
            },
        )

        client.upsert(
            "learning_feedback_v44",
            {
                "feedback_date": RUN_DATE,
                "portfolio_id": pid,
                "strategy_id": None,
                "source_type": "TRADE_REPLAY",
                "source_key": memory_id,
                "feedback_type": lesson_type,
                "signal_value": simulated_return,
                "reward_value": max(0, simulated_return),
                "penalty_value": max(0, -simulated_return),
                "applied": True,
                "application_target": "CONFIDENCE_CALIBRATION",
                "details": {
                    "original_confidence": original_confidence,
                    "calibrated_confidence": calibrated,
                },
            },
            "feedback_date,source_type,source_key,feedback_type",
        )

        learning_score = clamp(
            reliability * 0.4
            + pattern_confidence * 0.3
            + max(0, 100 - n(risk.get("risk_score"))) * 0.3,
            0,
            100,
        )

        recommended_action = action
        risk_override = risk_status == "CRITICAL"
        if risk_override:
            recommended_action = "HOLD"

        client.upsert(
            "portfolio_brain_snapshots_v44",
            {
                "snapshot_date": RUN_DATE,
                "portfolio_id": pid,
                "market_regime": regime,
                "brain_status": "WARNING" if risk_override or outcome_class == "LOSS" else "PASS",
                "memory_records": 1,
                "replay_records": 1,
                "win_patterns": 1 if outcome_class == "WIN" else 0,
                "mistake_patterns": 1 if outcome_class == "LOSS" else 0,
                "calibrated_confidence": calibrated,
                "learning_score": learning_score,
                "recommended_action": recommended_action,
                "risk_override": risk_override,
                "summary": (
                    f"Portfolio Brain learned {lesson_type}; confidence "
                    f"{original_confidence:.1f}% → {calibrated:.1f}%."
                ),
                "diagnostics": {
                    "outcome_class": outcome_class,
                    "simulated_return_pct": simulated_return,
                    "memory_id": memory_id,
                },
            },
            "snapshot_date,portfolio_id",
        )

    # Strategy evolution proposals remain PAPER-only and never modify code.
    for strategy in strategies:
        sid = str(strategy["id"])
        versions = client.get(
            "enterprise_strategy_versions_v40",
            f"strategy_id=eq.{sid}&order=created_at.desc&limit=1",
        )
        current_version = str(versions[0].get("version")) if versions else "1.0.0"
        marketplace = latest(
            client,
            "quant_strategy_marketplace",
            "updated_at",
            f"strategy_key=eq.{strategy.get('strategy_key')}",
        )
        current_score = n(marketplace.get("quality_score"), 50)

        patterns = client.get(
            "learning_patterns_v44",
            f"strategy_id=is.null&order=pattern_date.desc,confidence_score.desc&limit=20",
        )
        win_count = sum(1 for row in patterns if row.get("pattern_type") == "WIN_PATTERN")
        loss_count = sum(1 for row in patterns if row.get("pattern_type") == "MISTAKE_PATTERN")
        learning_score = clamp(current_score + win_count * 3 - loss_count * 5, 0, 100)
        candidate_score = clamp(current_score * 0.8 + learning_score * 0.2, 0, 100)

        if candidate_score >= 75:
            evolution_action = "PROMOTE_FOR_PAPER_TEST"
        elif candidate_score <= 30:
            evolution_action = "RETIRE_CANDIDATE"
        else:
            evolution_action = "KEEP_CURRENT"

        candidate_version = f"{current_version}-learned-{RUN_DATE.replace('-', '')}"
        client.upsert(
            "strategy_evolution_v44",
            {
                "evolution_date": RUN_DATE,
                "strategy_id": sid,
                "current_version": current_version,
                "candidate_version": candidate_version,
                "current_score": current_score,
                "candidate_score": candidate_score,
                "learning_score": learning_score,
                "evolution_action": evolution_action,
                "paper_approved": evolution_action == "PROMOTE_FOR_PAPER_TEST",
                "live_approved": False,
                "parameter_changes": {
                    "confidence_bias": 0.05 if win_count > loss_count else -0.05 if loss_count > win_count else 0,
                    "risk_budget_multiplier": 1.05 if win_count > loss_count else 0.85 if loss_count > win_count else 1.0,
                },
                "supporting_patterns": [
                    row.get("pattern_key") for row in patterns[:5]
                ],
                "risks": [
                    "proxy replay only",
                    "requires walk-forward validation",
                    "requires PAPER approval",
                ],
                "rationale": (
                    f"Evolution proposal based on {win_count} win and "
                    f"{loss_count} mistake pattern(s)."
                ),
            },
            "evolution_date,strategy_id,candidate_version",
        )
        evolutions_proposed += 1

    overall = "WARNING" if blockers or mistake_patterns_found else "PASS"
    summary = (
        f"Processed {len(portfolios)} portfolio(s); captured {memories_captured} "
        f"memory record(s), completed {replays_completed} replay(s), found "
        f"{win_patterns_found} win and {mistake_patterns_found} mistake pattern(s), "
        f"generated {calibrations_generated} calibration(s) and "
        f"{evolutions_proposed} strategy evolution proposal(s)."
    )

    client.upsert(
        "self_learning_status_v44",
        {
            "status_date": RUN_DATE,
            "overall_status": overall,
            "portfolios_processed": len(portfolios),
            "memories_captured": memories_captured,
            "replays_completed": replays_completed,
            "win_patterns_found": win_patterns_found,
            "mistake_patterns_found": mistake_patterns_found,
            "calibrations_generated": calibrations_generated,
            "evolutions_proposed": evolutions_proposed,
            "live_learning_enabled": False,
            "live_trading_enabled": False,
            "blockers": blockers,
            "summary": summary,
        },
        "status_date",
    )

    client.insert(
        "audit_logs_v40",
        {
            "actor_type": "SYSTEM",
            "actor_key": "enterprise44-portfolio-brain",
            "action": "PORTFOLIO_BRAIN_LEARNING_COMPLETED",
            "entity_type": "SELF_LEARNING_ENGINE",
            "entity_key": RUN_DATE,
            "severity": "WARNING" if overall == "WARNING" else "INFO",
            "metadata": {
                "overall_status": overall,
                "summary": summary,
                "blockers": blockers,
            },
        },
    )

    print(summary)
    print(f"Enterprise 4.4 status: {overall}")

if __name__ == "__main__":
    main()
