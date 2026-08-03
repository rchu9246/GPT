from __future__ import annotations

import math
import os
import uuid
from collections import Counter
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


def latest(client, table: str, field: str, where: str = "") -> dict[str, Any]:
    query = f"{where}&order={field}.desc&limit=1" if where else f"order={field}.desc&limit=1"
    try:
        rows = client.get(table, query)
        return rows[0] if rows else {}
    except Exception as exc:
        print(f"Optional source unavailable: {table}: {exc}")
        return {}


def direction_score(direction: str) -> float:
    return {
        "STRONG_BUY": 100,
        "BUY": 80,
        "HOLD": 55,
        "REDUCE": 35,
        "AVOID": 15,
        "BLOCK": 0,
    }.get(direction, 50)


def market_vote(client) -> dict[str, Any]:
    row = latest(client, "market_regime_ai_v46", "regime_date")
    regime = str(row.get("market_regime") or "UNKNOWN")
    confidence = n(row.get("regime_confidence"), 50)
    posture = str(row.get("recommended_posture") or "NEUTRAL")

    if regime == "CRASH":
        direction = "BLOCK"
    elif posture in ("RISK_OFF", "CAPITAL_PRESERVATION"):
        direction = "REDUCE"
    elif regime in ("TRENDING_UP", "BREAKOUT", "RECOVERY"):
        direction = "BUY"
    elif regime in ("LOW_VOLATILITY", "SIDEWAYS"):
        direction = "HOLD"
    else:
        direction = "HOLD"

    return {
        "agent_key": "MARKET_AGENT",
        "vote": f"Market regime {regime}, posture {posture}",
        "vote_direction": direction,
        "confidence": confidence,
        "risk_level": "CRITICAL" if regime == "CRASH" else "MEDIUM",
        "veto": regime == "CRASH",
        "supporting_factors": [regime, posture],
        "opposing_factors": [],
        "evidence": row,
        "explanation": f"Market Agent classified the environment as {regime}.",
    }


def risk_vote(client) -> dict[str, Any]:
    row = latest(client, "risk_governor_status_v41", "status_date")
    status = str(row.get("overall_status") or "UNKNOWN")
    active = int(n(row.get("active_breakers"), 0))
    critical = int(n(row.get("open_critical_events"), 0))
    risk_score = n(row.get("overall_risk_score"), 50)
    confidence = max(0, min(100, 100 - risk_score))

    veto = status == "CRITICAL" or active > 0 or critical > 0
    direction = "BLOCK" if veto else "REDUCE" if status == "WARNING" else "BUY"

    return {
        "agent_key": "RISK_AGENT",
        "vote": f"Risk status {status}, active breakers {active}",
        "vote_direction": direction,
        "confidence": confidence,
        "risk_level": "CRITICAL" if veto else "HIGH" if status == "WARNING" else "LOW",
        "veto": veto,
        "supporting_factors": [f"risk_status:{status}"],
        "opposing_factors": row.get("blockers", []),
        "evidence": row,
        "explanation": f"Risk Agent evaluated portfolio risk as {status}.",
    }


def strategy_vote(client) -> dict[str, Any]:
    status = latest(client, "strategy_engine_status_v47", "status_date")
    scores = []
    try:
        scores = client.get(
            "strategy_scores_v47",
            f"score_date=eq.{RUN_DATE}&eligible=eq.true&order=rank.asc&limit=20",
        )
    except Exception:
        pass

    top = scores[0] if scores else {}
    score = n(top.get("composite_score"), n(status.get("average_composite_score"), 50))
    confidence = n(top.get("confidence_score"), n(status.get("average_confidence"), 50))
    key = str(top.get("strategy_key") or "UNAVAILABLE")

    direction = "BUY" if score >= 70 else "HOLD" if score >= 50 else "AVOID"

    return {
        "agent_key": "STRATEGY_AGENT",
        "vote": f"Top strategy {key} with score {score:.2f}",
        "vote_direction": direction,
        "confidence": confidence,
        "risk_level": "MEDIUM",
        "veto": False,
        "supporting_factors": [key, f"score:{score:.2f}"],
        "opposing_factors": [],
        "evidence": {"status": status, "top_score": top},
        "explanation": f"Strategy Agent selected {key} as the leading eligible strategy.",
        "selected_strategy": key,
    }


def optimizer_vote(client) -> dict[str, Any]:
    run = latest(
        client,
        "optimization_runs_v49",
        "run_date",
        "run_key=eq.PORTFOLIO_OPTIMIZER",
    )
    allocation = latest(client, "allocation_engine_status_v48", "status_date")
    status = str(run.get("status") or allocation.get("overall_status") or "UNKNOWN")
    confidence = n(run.get("objective_score"), n(allocation.get("average_confidence_score"), 50))
    gross = n(allocation.get("average_gross_exposure_pct"), 0)
    cash = n(allocation.get("average_cash_weight_pct"), 100)

    direction = "BLOCK" if status == "CRITICAL" else "REDUCE" if status == "WARNING" else "BUY"

    return {
        "agent_key": "OPTIMIZER_AGENT",
        "vote": f"Optimizer status {status}, gross {gross:.2f}%, cash {cash:.2f}%",
        "vote_direction": direction,
        "confidence": confidence,
        "risk_level": "HIGH" if status == "CRITICAL" else "MEDIUM",
        "veto": status == "CRITICAL",
        "supporting_factors": [f"gross:{gross:.2f}", f"cash:{cash:.2f}"],
        "opposing_factors": allocation.get("blockers", []),
        "evidence": {"run": run, "allocation": allocation},
        "explanation": f"Optimizer Agent recommends gross exposure {gross:.2f}% and cash {cash:.2f}%.",
        "recommended_exposure_pct": gross,
        "recommended_cash_pct": cash,
    }


def learning_vote(client) -> dict[str, Any]:
    row = latest(client, "learning_cycle_status_v45", "status_date")
    status = str(row.get("overall_status") or "UNKNOWN")
    wins = int(n(row.get("wins"), 0))
    losses = int(n(row.get("losses"), 0))
    total = wins + losses
    confidence = 50 if total == 0 else max(0, min(100, wins / total * 100))

    direction = "BUY" if confidence >= 65 else "HOLD" if confidence >= 45 else "REDUCE"

    return {
        "agent_key": "LEARNING_AGENT",
        "vote": f"Learning status {status}, wins {wins}, losses {losses}",
        "vote_direction": direction,
        "confidence": confidence,
        "risk_level": "MEDIUM",
        "veto": False,
        "supporting_factors": [f"wins:{wins}"],
        "opposing_factors": [f"losses:{losses}"],
        "evidence": row,
        "explanation": "Learning Agent contributed historical outcome and calibration context.",
    }


def main() -> None:
    client = SupabaseRestClient()
    session_key = "DAILY_MULTI_AGENT_COUNCIL"
    cycle = latest(client, "operating_state_v50", "state_date")
    cycle_id = cycle.get("current_cycle_id")
    market = latest(client, "market_regime_ai_v46", "regime_date")
    market_regime = str(market.get("market_regime") or "UNKNOWN")

    registry = client.get(
        "agent_registry_v51",
        "enabled=eq.true&agent_key=neq.DECISION_COUNCIL&order=execution_order.asc&limit=20",
    )

    session_payload = {
        "session_date": RUN_DATE,
        "cycle_id": cycle_id,
        "session_key": session_key,
        "session_status": "RUNNING",
        "market_regime": market_regime,
        "portfolio_count": 0,
        "agents_expected": len(registry),
        "agents_completed": 0,
        "consensus_score": 0,
        "conflict_count": 0,
        "final_confidence": 0,
        "blockers": [],
        "warnings": [],
        "summary": "Enterprise 5.1 council session is running.",
        "started_at": now(),
    }
    client.upsert(
        "council_sessions_v51",
        session_payload,
        "session_date,session_key",
    )
    sessions = client.get(
        "council_sessions_v51",
        f"session_date=eq.{RUN_DATE}&session_key=eq.{session_key}&limit=1",
    )
    session_id = str(sessions[0]["id"])

    vote_builders = {
        "MARKET_AGENT": market_vote,
        "RISK_AGENT": risk_vote,
        "STRATEGY_AGENT": strategy_vote,
        "OPTIMIZER_AGENT": optimizer_vote,
        "LEARNING_AGENT": learning_vote,
    }

    votes = []
    warnings = []
    blockers = []

    for agent in registry:
        key = str(agent["agent_key"])
        builder = vote_builders.get(key)
        if not builder:
            if agent.get("required"):
                blockers.append(f"MISSING_AGENT_IMPLEMENTATION:{key}")
            else:
                warnings.append(f"MISSING_AGENT_IMPLEMENTATION:{key}")
            continue

        try:
            vote = builder(client)
            weight = n(agent.get("voting_weight"), 1)
            vote["weighted_score"] = direction_score(vote["vote_direction"]) * weight
            client.upsert(
                "agent_votes_v51",
                {
                    "session_id": session_id,
                    "agent_key": key,
                    "portfolio_id": None,
                    "vote": vote["vote"],
                    "vote_direction": vote["vote_direction"],
                    "confidence": vote["confidence"],
                    "weighted_score": vote["weighted_score"],
                    "risk_level": vote["risk_level"],
                    "veto": vote["veto"],
                    "supporting_factors": vote["supporting_factors"],
                    "opposing_factors": vote["opposing_factors"],
                    "evidence": vote["evidence"],
                },
                "session_id,agent_key,portfolio_id",
            )
            client.insert(
                "agent_explanations_v51",
                {
                    "session_id": session_id,
                    "agent_key": key,
                    "portfolio_id": None,
                    "explanation": vote["explanation"],
                    "rationale": {
                        "vote_direction": vote["vote_direction"],
                        "confidence": vote["confidence"],
                    },
                    "source_records": [agent.get("source_table")],
                },
            )
            votes.append({**vote, "weight": weight})
            client.patch(
                "agent_registry_v51",
                f"agent_key=eq.{key}",
                {"health_status": "PASS"},
            )
        except Exception as exc:
            client.patch(
                "agent_registry_v51",
                f"agent_key=eq.{key}",
                {"health_status": "FAILED"},
            )
            if agent.get("required"):
                blockers.append(f"{key}:{exc}")
            else:
                warnings.append(f"{key}:{exc}")

    vetoes = [v for v in votes if v.get("veto")]
    directions = [v["vote_direction"] for v in votes]
    distribution = dict(Counter(directions))

    positive = sum(
        v["confidence"] * v["weight"]
        for v in votes
        if v["vote_direction"] in ("STRONG_BUY", "BUY")
    )
    total_weighted_conf = sum(v["confidence"] * v["weight"] for v in votes)
    approval_ratio = 0 if total_weighted_conf == 0 else positive / total_weighted_conf * 100

    weighted_numerator = sum(
        direction_score(v["vote_direction"]) * v["confidence"] * v["weight"]
        for v in votes
    )
    weighted_denominator = sum(v["confidence"] * v["weight"] for v in votes)
    consensus_value = 50 if weighted_denominator == 0 else weighted_numerator / weighted_denominator

    majority_direction = Counter(directions).most_common(1)[0][0] if directions else "BLOCK"
    majority_count = Counter(directions).most_common(1)[0][1] if directions else 0
    consensus_score = 0 if not votes else majority_count / len(votes) * 100
    final_confidence = mean([v["confidence"] for v in votes]) if votes else 0

    conflict_count = len(set(directions)) - 1 if directions else 0
    conflicts = []
    if conflict_count > 0:
        conflict_summary = f"Agents produced {len(set(directions))} distinct vote directions."
        conflict = {
            "conflict_type": "DIRECTION_DISAGREEMENT",
            "agents_involved": [v["agent_key"] for v in votes],
            "severity": "WARNING",
            "conflict_summary": conflict_summary,
            "resolution": "Resolved by weighted consensus with risk veto precedence.",
            "resolved": True,
        }
        client.insert(
            "agent_conflicts_v51",
            {"session_id": session_id, "portfolio_id": None, **conflict},
        )
        conflicts.append(conflict)

    if blockers or vetoes:
        final_decision = "BLOCK"
        decision_status = "BLOCKED"
    elif consensus_value >= 85:
        final_decision = "STRONG_BUY"
        decision_status = "APPROVED_FOR_PAPER"
    elif consensus_value >= 65:
        final_decision = "BUY"
        decision_status = "APPROVED_FOR_PAPER"
    elif consensus_value >= 45:
        final_decision = "HOLD"
        decision_status = "WARNING" if conflict_count else "APPROVED_FOR_PAPER"
    elif consensus_value >= 25:
        final_decision = "REDUCE"
        decision_status = "REDUCED"
    else:
        final_decision = "AVOID"
        decision_status = "REDUCED"

    optimizer = next((v for v in votes if v["agent_key"] == "OPTIMIZER_AGENT"), {})
    strategy = next((v for v in votes if v["agent_key"] == "STRATEGY_AGENT"), {})

    rationale = (
        f"Council decision {final_decision}; weighted consensus value "
        f"{consensus_value:.2f}; majority {majority_direction}; "
        f"vetoes {len(vetoes)}; conflicts {conflict_count}."
    )

    client.upsert(
        "decision_council_v51",
        {
            "session_id": session_id,
            "decision_date": RUN_DATE,
            "cycle_id": cycle_id,
            "market_regime": market_regime,
            "final_decision": final_decision,
            "final_confidence": final_confidence,
            "consensus_score": consensus_score,
            "approval_ratio": approval_ratio,
            "veto_count": len(vetoes),
            "selected_strategy": strategy.get("selected_strategy"),
            "recommended_exposure_pct": n(optimizer.get("recommended_exposure_pct"), 0),
            "recommended_cash_pct": n(optimizer.get("recommended_cash_pct"), 100),
            "decision_status": decision_status,
            "rationale": rationale,
            "vote_summary": distribution,
            "conflicts": conflicts,
            "blockers": blockers + [f"VETO:{v['agent_key']}" for v in vetoes],
            "warnings": warnings,
            "paper_approved": True,
            "live_approved": False,
            "autonomous_execution_enabled": False,
        },
        "session_id",
    )

    session_status = (
        "CRITICAL" if blockers or vetoes else
        "WARNING" if warnings or conflict_count else
        "PASS"
    )

    client.patch(
        "council_sessions_v51",
        f"id=eq.{session_id}",
        {
            "session_status": session_status,
            "agents_completed": len(votes),
            "consensus_score": consensus_score,
            "conflict_count": conflict_count,
            "final_decision": final_decision,
            "final_confidence": final_confidence,
            "blockers": blockers,
            "warnings": warnings,
            "summary": rationale,
            "completed_at": now(),
        },
    )

    client.insert(
        "consensus_history_v51",
        {
            "consensus_date": RUN_DATE,
            "session_id": session_id,
            "final_decision": final_decision,
            "consensus_score": consensus_score,
            "final_confidence": final_confidence,
            "agent_count": len(votes),
            "conflict_count": conflict_count,
            "vote_distribution": distribution,
        },
    )

    overall_status = "CRITICAL" if session_status == "CRITICAL" else "WARNING" if session_status == "WARNING" else "PASS"

    client.upsert(
        "council_status_v51",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_session_id": session_id,
            "sessions_completed": 1,
            "agents_registered": len(registry),
            "agents_completed": len(votes),
            "votes_cast": len(votes),
            "conflicts_detected": conflict_count,
            "vetoes_cast": len(vetoes),
            "consensus_score": consensus_score,
            "final_confidence": final_confidence,
            "final_decision": final_decision,
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
            "blockers": blockers + [f"VETO:{v['agent_key']}" for v in vetoes],
            "warnings": warnings,
            "summary": rationale,
            "diagnostics": {
                "weighted_consensus_value": consensus_value,
                "vote_distribution": distribution,
                "market_regime": market_regime,
            },
        },
        "status_date",
    )

    client.upsert(
        "council_metrics_v51",
        {
            "metric_date": RUN_DATE,
            "sessions_completed": 1,
            "agents_active": len(votes),
            "votes_cast": len(votes),
            "conflicts_detected": conflict_count,
            "vetoes_cast": len(vetoes),
            "average_consensus": consensus_score,
            "average_confidence": final_confidence,
            "blocked_decisions": 1 if decision_status == "BLOCKED" else 0,
            "approved_decisions": 1 if decision_status == "APPROVED_FOR_PAPER" else 0,
            "diagnostics": {
                "final_decision": final_decision,
                "distribution": distribution,
            },
        },
        "metric_date",
    )

    print(rationale)
    print(f"Enterprise 5.1 Multi-Agent Council status: {overall_status}")

    if blockers:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
