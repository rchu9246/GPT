from __future__ import annotations

import math
import os
from datetime import date, datetime, timezone
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

def safe_get(client, table: str, query: str):
    try:
        return client.get(table, query)
    except Exception:
        return []

def recommendation(score: float) -> str:
    if score >= 68:
        return "BUY"
    if score <= 38:
        return "SELL"
    return "HOLD"

def main() -> None:
    client = SupabaseRestClient()
    portfolios = client.get(
        "enterprise_portfolios_v40",
        "lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100",
    )
    agents = client.get(
        "committee_agents_v43",
        "enabled=eq.true&order=id.asc&limit=100",
    )
    regime_row = latest(client, "market_regimes_v40", "regime_date")
    regime = str(regime_row.get("regime") or "UNKNOWN")

    completed = opinions_count = votes_count = theses_count = decisions_count = 0
    risk_vetoes = 0
    blockers: list[str] = []

    for portfolio in portfolios:
        pid = str(portfolio["id"])
        account = str(portfolio.get("account_name") or "paper-main")

        existing = client.get(
            "investment_committee_sessions_v43",
            f"session_date=eq.{RUN_DATE}&portfolio_id=eq.{pid}&session_type=eq.DAILY&limit=1",
        )
        if existing and existing[0].get("session_status") == "CLOSED":
            completed += 1
            continue

        if existing:
            session_id = str(existing[0]["id"])
            client.patch(
                "investment_committee_sessions_v43",
                f"id=eq.{session_id}",
                {
                    "session_status": "OPEN",
                    "market_regime": regime,
                    "blockers": [],
                    "closed_at": None,
                },
            )
        else:
            session = client.insert(
                "investment_committee_sessions_v43",
                {
                    "session_date": RUN_DATE,
                    "portfolio_id": pid,
                    "session_type": "DAILY",
                    "session_status": "OPEN",
                    "market_regime": regime,
                    "quorum_required": 4,
                    "quorum_reached": 0,
                    "live_trading_enabled": False,
                },
            )[0]
            session_id = str(session["id"])

        risk = latest(client, "risk_governor_status_v41", "status_date")
        adaptive = latest(client, "adaptive_allocation_status_v42", "status_date")
        portfolio_risk = latest(
            client,
            "portfolio_risk_v41",
            "risk_date",
            f"portfolio_id=eq.{pid}",
        )
        monte = latest(
            client,
            "monte_carlo_runs_v42",
            "run_date",
            f"portfolio_id=eq.{pid}",
        )
        proposal = latest(
            client,
            "rebalance_proposals_v42",
            "proposal_date",
            f"portfolio_id=eq.{pid}",
        )
        factor_rows = safe_get(
            client,
            "factor_rankings_v32",
            f"account_name=eq.{account}&order=ranking_date.desc,rank_position.asc&limit=20",
        )

        factor_quality = (
            sum(n(row.get("quality_score"), 50) for row in factor_rows) / len(factor_rows)
            if factor_rows else 50
        )
        portfolio_risk_score = n(portfolio_risk.get("risk_score"), 50)
        prob_loss = n(monte.get("probability_of_loss"), 0.5)
        prob_breach = n(monte.get("probability_of_breach"), 0.2)
        expected_shortfall = n(monte.get("expected_shortfall_pct"), 4)
        risk_status = str(risk.get("overall_status") or "NO_DATA")
        adaptive_status = str(adaptive.get("overall_status") or "NO_DATA")
        proposal_status = str(proposal.get("proposal_status") or "NO_DATA")

        regime_bias = {
            "BULL": 15,
            "SIDEWAYS": 3,
            "BEAR": -15,
            "HIGH_VOLATILITY": -12,
            "RISK_OFF": -25,
            "UNKNOWN": -5,
        }.get(regime, -5)

        opinion_payloads = []
        for agent in agents:
            key = str(agent["agent_key"])
            weight = n(agent.get("voting_weight"), 1)

            if key == "macro":
                score = 50 + regime_bias
                thesis = f"Macro regime is {regime}; allocation should reflect regime risk."
            elif key == "technical":
                score = factor_quality + regime_bias * 0.3
                thesis = f"Technical and factor quality average is {factor_quality:.1f}."
            elif key == "quant":
                score = factor_quality * 0.7 + (1 - prob_loss) * 100 * 0.3
                thesis = f"Quant score combines factor quality and simulated loss probability."
            elif key == "risk":
                score = 100 - portfolio_risk_score - prob_breach * 40
                thesis = f"Risk score {portfolio_risk_score:.1f}, breach probability {prob_breach:.1%}."
            elif key == "portfolio":
                score = 60 if proposal_status == "PROPOSED" else 35 if proposal_status == "BLOCKED" else 50
                thesis = f"Adaptive proposal status is {proposal_status}."
            else:
                continue

            score = clamp(score, 0, 100)
            rec = recommendation(score)
            confidence = clamp(abs(score - 50) * 1.8 + 35, 35, 95)
            expected_return = (score - 50) * 0.18
            downside = max(1.0, expected_shortfall + portfolio_risk_score * 0.03)
            proposed_weight = clamp(n(portfolio.get("max_position_pct"), 15) * score / 100, 0, 15)

            opinion = client.upsert(
                "committee_opinions_v43",
                {
                    "session_id": session_id,
                    "agent_id": agent["id"],
                    "symbol": "PORTFOLIO",
                    "recommendation": rec,
                    "confidence": confidence,
                    "expected_return_pct": expected_return,
                    "downside_risk_pct": downside,
                    "proposed_weight_pct": proposed_weight,
                    "thesis_summary": thesis,
                    "bull_case": f"{regime} conditions and factor quality support upside.",
                    "bear_case": f"Risk status {risk_status}, adaptive status {adaptive_status}.",
                    "catalysts": ["improving regime", "factor confirmation"],
                    "risks": ["drawdown", "correlation", "liquidity", "model risk"],
                    "evidence": {
                        "regime": regime,
                        "factor_quality": factor_quality,
                        "portfolio_risk_score": portfolio_risk_score,
                        "probability_of_loss": prob_loss,
                        "probability_of_breach": prob_breach,
                    },
                },
                "session_id,agent_id,symbol",
            )
            opinions_count += 1

            vote_value = 1 if rec == "BUY" else -1 if rec == "SELL" else 0
            veto = (
                key == "risk"
                and (
                    risk_status == "CRITICAL"
                    or portfolio_risk_score >= 80
                    or prob_breach >= 0.25
                    or proposal_status == "BLOCKED"
                )
            )
            if veto:
                risk_vetoes += 1

            client.upsert(
                "committee_votes_v43",
                {
                    "session_id": session_id,
                    "agent_id": agent["id"],
                    "symbol": "PORTFOLIO",
                    "vote": rec,
                    "confidence": confidence,
                    "weighted_vote": vote_value * weight * confidence / 100,
                    "veto_exercised": veto,
                    "rationale": thesis,
                },
                "session_id,agent_id,symbol",
            )
            votes_count += 1
            opinion_payloads.append({
                "agent": key,
                "recommendation": rec,
                "confidence": confidence,
                "score": score,
                "weight": weight,
                "veto": veto,
                "expected_return": expected_return,
                "downside": downside,
                "proposed_weight": proposed_weight,
                "thesis": thesis,
            })

        quorum = len(opinion_payloads)
        weighted_sum = sum(
            (1 if row["recommendation"] == "BUY" else -1 if row["recommendation"] == "SELL" else 0)
            * row["weight"]
            * row["confidence"] / 100
            for row in opinion_payloads
        )
        total_weight = sum(row["weight"] for row in opinion_payloads) or 1
        normalized_vote = weighted_sum / total_weight
        vetoed = any(row["veto"] for row in opinion_payloads)

        if vetoed:
            final_action = "HOLD"
            chairman_decision = "RISK_VETO"
            chairman_confidence = 95
            final_risk_status = "BLOCKED"
        elif normalized_vote >= 0.18:
            final_action = "BUY"
            chairman_decision = "APPROVED"
            chairman_confidence = clamp(50 + normalized_vote * 100, 50, 95)
            final_risk_status = "PASS"
        elif normalized_vote <= -0.18:
            final_action = "SELL"
            chairman_decision = "APPROVED"
            chairman_confidence = clamp(50 + abs(normalized_vote) * 100, 50, 95)
            final_risk_status = "PASS"
        else:
            final_action = "HOLD"
            chairman_decision = "NO_CONSENSUS"
            chairman_confidence = 60
            final_risk_status = "REVIEW"

        supporting = [
            row["thesis"] for row in opinion_payloads
            if row["recommendation"] == final_action
        ]
        opposing = [
            row["thesis"] for row in opinion_payloads
            if row["recommendation"] not in (final_action, "HOLD")
        ]
        proposed_weights = [row["proposed_weight"] for row in opinion_payloads]
        recommended_weight = sum(proposed_weights) / len(proposed_weights) if proposed_weights else 0
        expected_returns = [row["expected_return"] for row in opinion_payloads]
        downsides = [row["downside"] for row in opinion_payloads]

        thesis = client.upsert(
            "investment_theses_v43",
            {
                "session_id": session_id,
                "portfolio_id": pid,
                "symbol": "PORTFOLIO",
                "thesis_date": RUN_DATE,
                "thesis_status": "ACTIVE",
                "final_recommendation": final_action,
                "confidence": chairman_confidence,
                "recommended_weight_pct": recommended_weight,
                "expected_return_pct": (
                    sum(expected_returns) / len(expected_returns)
                    if expected_returns else 0
                ),
                "downside_risk_pct": (
                    sum(downsides) / len(downsides)
                    if downsides else 0
                ),
                "bull_case": "Regime and quantitative factors improve while risk remains controlled.",
                "base_case": f"Committee decision {final_action} with confidence {chairman_confidence:.1f}%.",
                "bear_case": "Risk deterioration, correlation spike or stress loss invalidates the thesis.",
                "catalysts": ["regime improvement", "factor confirmation", "risk normalization"],
                "risks": ["risk veto", "stress loss", "drawdown", "liquidity"],
                "invalidation_conditions": [
                    "risk governor becomes CRITICAL",
                    "Monte Carlo breach probability exceeds 25%",
                    "circuit breaker triggers",
                ],
                "explanation": (
                    f"Weighted committee vote {normalized_vote:.3f}; "
                    f"risk veto {'active' if vetoed else 'inactive'}."
                ),
            },
            "session_id,symbol",
        )
        theses_count += 1

        client.upsert(
            "explainable_decisions_v43",
            {
                "decision_date": RUN_DATE,
                "session_id": session_id,
                "portfolio_id": pid,
                "symbol": "PORTFOLIO",
                "requested_action": proposal_status,
                "final_action": final_action,
                "confidence": chairman_confidence,
                "score_breakdown": {
                    "weighted_vote": normalized_vote,
                    "factor_quality": factor_quality,
                    "portfolio_risk_score": portfolio_risk_score,
                    "probability_of_loss": prob_loss,
                    "probability_of_breach": prob_breach,
                },
                "supporting_reasons": supporting,
                "opposing_reasons": opposing,
                "risk_overrides": (
                    ["CHIEF_RISK_OFFICER_VETO"] if vetoed else []
                ),
                "explanation": (
                    f"Final action {final_action}. "
                    f"Committee quorum {quorum}; vote {normalized_vote:.3f}; "
                    f"risk status {risk_status}."
                ),
                "approved_for_paper": final_action in ("BUY", "SELL", "HOLD") and not vetoed,
                "approved_for_live": False,
            },
            "decision_date,portfolio_id,symbol",
        )
        decisions_count += 1

        client.patch(
            "investment_committee_sessions_v43",
            f"id=eq.{session_id}",
            {
                "session_status": "CLOSED",
                "quorum_reached": quorum,
                "chairman_decision": chairman_decision,
                "chairman_confidence": chairman_confidence,
                "final_risk_status": final_risk_status,
                "final_action": final_action,
                "summary": (
                    f"Committee closed with {final_action}; "
                    f"confidence {chairman_confidence:.1f}%; quorum {quorum}."
                ),
                "blockers": ["RISK_VETO"] if vetoed else [],
                "live_trading_enabled": False,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        client.insert(
            "committee_audit_v43",
            {
                "session_id": session_id,
                "event_type": "SESSION_CLOSED",
                "actor_key": "chairman",
                "entity_key": f"{RUN_DATE}:{pid}",
                "after_state": {
                    "final_action": final_action,
                    "confidence": chairman_confidence,
                    "vetoed": vetoed,
                    "quorum": quorum,
                },
                "rationale": "Weighted multi-agent committee decision.",
                "severity": "WARNING" if vetoed else "INFO",
            },
        )

        client.upsert(
            "knowledge_records_v43",
            {
                "record_date": RUN_DATE,
                "record_type": "INVESTMENT_COMMITTEE_DECISION",
                "source_entity_type": "COMMITTEE_SESSION",
                "source_entity_key": session_id,
                "portfolio_id": pid,
                "strategy_id": None,
                "title": f"Daily committee decision: {final_action}",
                "summary": (
                    f"Regime {regime}; action {final_action}; "
                    f"confidence {chairman_confidence:.1f}%; "
                    f"risk veto {vetoed}."
                ),
                "tags": ["enterprise-4.3", "committee", regime, final_action],
                "facts": {
                    "factor_quality": factor_quality,
                    "risk_score": portfolio_risk_score,
                    "loss_probability": prob_loss,
                    "breach_probability": prob_breach,
                    "weighted_vote": normalized_vote,
                },
                "confidence": chairman_confidence,
                "retention_status": "ACTIVE",
            },
            "record_date,record_type,source_entity_type,source_entity_key",
        )
        completed += 1

    overall = "WARNING" if risk_vetoes else "PASS"
    summary = (
        f"Completed {completed} session(s), generated {opinions_count} opinion(s), "
        f"{votes_count} vote(s), {theses_count} thesis record(s), "
        f"{decisions_count} explainable decision(s), risk vetoes {risk_vetoes}."
    )

    client.upsert(
        "committee_status_v43",
        {
            "status_date": RUN_DATE,
            "overall_status": overall,
            "sessions_completed": completed,
            "opinions_generated": opinions_count,
            "votes_cast": votes_count,
            "theses_generated": theses_count,
            "decisions_generated": decisions_count,
            "risk_vetoes": risk_vetoes,
            "live_trading_enabled": False,
            "blockers": ["RISK_VETO_ACTIVE"] if risk_vetoes else [],
            "summary": summary,
        },
        "status_date",
    )

    client.insert(
        "audit_logs_v40",
        {
            "actor_type": "SYSTEM",
            "actor_key": "enterprise43-investment-committee",
            "action": "INVESTMENT_COMMITTEE_COMPLETED",
            "entity_type": "COMMITTEE",
            "entity_key": RUN_DATE,
            "severity": "WARNING" if risk_vetoes else "INFO",
            "metadata": {
                "overall_status": overall,
                "summary": summary,
                "risk_vetoes": risk_vetoes,
            },
        },
    )

    print(summary)
    print(f"Enterprise 4.3 status: {overall}")

if __name__ == "__main__":
    main()
