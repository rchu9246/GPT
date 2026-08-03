from __future__ import annotations

import math
import os
import time
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())


def n(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


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
    rows = client.get(table, query)
    return rows[0] if rows else {}


def safe_get(
    client: SupabaseRestClient,
    table: str,
    query: str,
) -> list[dict[str, Any]]:
    try:
        rows = client.get(table, query)
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        print(f"Optional source unavailable: {table}: {exc}")
        return []


def json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def constraint_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("constraint_key")): row
        for row in rows
        if row.get("constraint_key")
    }


def numeric_constraint(
    constraints: dict[str, dict[str, Any]],
    key: str,
    fallback: float,
) -> float:
    row = constraints.get(key, {})
    return n(row.get("numeric_value"), fallback)


def policy_parameters(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("parameters")
    return value if isinstance(value, dict) else {}


def current_weight_map(
    client: SupabaseRestClient,
    portfolio_id: str,
) -> dict[str, float]:
    previous = safe_get(
        client,
        "portfolio_target_weights_v49",
        (
            f"portfolio_id=eq.{portfolio_id}"
            "&order=weight_date.desc&limit=500"
        ),
    )
    if not previous:
        return {}

    latest_date = str(previous[0].get("weight_date") or "")
    return {
        str(row.get("asset_symbol")): n(row.get("target_weight_pct"))
        for row in previous
        if str(row.get("weight_date") or "") == latest_date
    }


def classify_action(current: float, target: float) -> str:
    delta = target - current
    if abs(delta) < 0.01:
        return "HOLD"
    if target <= 0 and current > 0:
        return "EXIT"
    if delta > 0:
        return "BUY"
    if target > 0:
        return "REDUCE"
    return "SELL"


def apply_weight_cap(
    weighted: list[dict[str, Any]],
    target_exposure: float,
    max_weight: float,
    min_weight: float,
) -> list[dict[str, Any]]:
    if not weighted or target_exposure <= 0:
        return []

    active = [dict(row) for row in weighted]
    for row in active:
        row["weight"] = 0.0

    remaining = target_exposure
    unresolved = list(range(len(active)))

    for _ in range(len(active) + 3):
        if not unresolved or remaining <= 1e-9:
            break

        raw_total = sum(
            max(0.0, n(active[index].get("raw_weight")))
            for index in unresolved
        )
        if raw_total <= 0:
            equal = remaining / len(unresolved)
            proposed = {index: equal for index in unresolved}
        else:
            proposed = {
                index: (
                    remaining
                    * max(0.0, n(active[index].get("raw_weight")))
                    / raw_total
                )
                for index in unresolved
            }

        capped_now: list[int] = []
        for index, value in proposed.items():
            if value > max_weight:
                active[index]["weight"] = max_weight
                remaining -= max_weight
                capped_now.append(index)

        if not capped_now:
            for index, value in proposed.items():
                active[index]["weight"] = value
            remaining = 0
            break

        unresolved = [
            index for index in unresolved if index not in capped_now
        ]

    selected: list[dict[str, Any]] = []
    removed_weight = 0.0
    for row in active:
        weight = max(0.0, n(row.get("weight")))
        if 0 < weight < min_weight:
            removed_weight += weight
            continue
        row["weight"] = weight
        selected.append(row)

    if selected and removed_weight > 0:
        capacity = sum(
            max(0.0, max_weight - n(row.get("weight")))
            for row in selected
        )
        if capacity > 0:
            for row in selected:
                available = max(0.0, max_weight - n(row.get("weight")))
                addition = removed_weight * available / capacity
                row["weight"] = min(
                    max_weight,
                    n(row.get("weight")) + addition,
                )

    return selected


def main() -> None:
    started = time.perf_counter()
    client = SupabaseRestClient()

    portfolios = client.get(
        "enterprise_portfolios_v40",
        "lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100",
    )
    policy = latest(
        client,
        "allocation_policies_v48",
        "priority",
        "enabled=eq.true&paper_approved=eq.true&live_approved=eq.false",
    )
    constraints_rows = safe_get(
        client,
        "allocation_constraints_v48",
        "enabled=eq.true&paper_approved=eq.true&live_approved=eq.false"
        "&limit=100",
    )
    constraints = constraint_map(constraints_rows)
    regime = latest(client, "market_regime_ai_v46", "regime_date")
    risk_status = latest(client, "risk_governor_status_v41", "status_date")

    market_regime = str(regime.get("market_regime") or "UNKNOWN")
    posture = str(regime.get("recommended_posture") or "NEUTRAL")
    active_breakers = int(n(risk_status.get("active_breakers")))
    critical_events = int(n(risk_status.get("open_critical_events")))

    top_n = int(n(policy.get("top_n_strategies"), 3))
    min_score = n(policy.get("minimum_strategy_score"), 50)
    min_confidence = n(policy.get("minimum_confidence_score"), 50)
    max_weight = min(
        n(policy.get("maximum_strategy_weight_pct"), 40),
        numeric_constraint(
            constraints,
            "MAX_STRATEGY_WEIGHT_PCT",
            40,
        ),
    )
    min_weight = max(
        n(policy.get("minimum_strategy_weight_pct"), 5),
        numeric_constraint(
            constraints,
            "MIN_STRATEGY_WEIGHT_PCT",
            5,
        ),
    )
    min_cash = max(
        n(policy.get("minimum_cash_pct"), 20),
        numeric_constraint(constraints, "MIN_CASH_PCT", 20),
    )
    max_gross = min(
        n(policy.get("maximum_gross_exposure_pct"), 100),
        numeric_constraint(
            constraints,
            "MAX_GROSS_EXPOSURE_PCT",
            100,
        ),
    )
    target_gross = min(
        n(policy.get("target_gross_exposure_pct"), 80),
        max_gross,
        100 - min_cash,
    )
    max_leverage = min(
        n(policy.get("maximum_leverage"), 1),
        numeric_constraint(constraints, "MAX_LEVERAGE", 1),
    )
    high_risk_cap = numeric_constraint(
        constraints,
        "MAX_HIGH_RISK_WEIGHT_PCT",
        20,
    )
    minimum_health = numeric_constraint(
        constraints,
        "MIN_PORTFOLIO_HEALTH_SCORE",
        40,
    )
    maximum_breakers = int(
        numeric_constraint(constraints, "MAX_ACTIVE_BREAKERS", 0)
    )

    if posture in ("RISK_OFF", "CAPITAL_PRESERVATION"):
        target_gross *= n(
            policy.get("risk_off_exposure_multiplier"),
            0.5,
        )
    if market_regime == "CRASH":
        target_gross = 0.0

    params = policy_parameters(policy)
    score_weight = n(params.get("score_weight"), 0.45)
    confidence_weight = n(params.get("confidence_weight"), 0.25)
    risk_weight = n(params.get("risk_weight"), 0.20)
    regime_weight = n(params.get("regime_fit_weight"), 0.10)

    portfolios_processed = 0
    candidates_generated = 0
    selected_count_total = 0
    allocations_generated = 0
    allocations_approved = 0
    allocations_reduced = 0
    allocations_blocked = 0
    critical_findings = 0
    warning_findings = 0

    allocation_scores: list[float] = []
    confidence_scores: list[float] = []
    gross_exposures: list[float] = []
    cash_weights: list[float] = []

    for portfolio in portfolios:
        portfolio_id = str(portfolio["id"])
        portfolio_key = str(
            portfolio.get("portfolio_key") or portfolio_id
        )
        scores = safe_get(
            client,
            "strategy_scores_v47",
            (
                f"score_date=eq.{RUN_DATE}"
                f"&portfolio_id=eq.{portfolio_id}"
                "&order=rank.asc&limit=100"
            ),
        )
        if not scores:
            scores = safe_get(
                client,
                "strategy_scores_v47",
                (
                    f"portfolio_id=eq.{portfolio_id}"
                    "&order=score_date.desc,rank.asc&limit=100"
                ),
            )
            if scores:
                latest_score_date = str(scores[0].get("score_date") or "")
                scores = [
                    row for row in scores
                    if str(row.get("score_date") or "")
                    == latest_score_date
                ]

        health = latest(
            client,
            "portfolio_health_v46",
            "health_date",
            f"portfolio_id=eq.{portfolio_id}",
        )
        health_score = n(health.get("health_score"), 50)
        health_risk_score = n(health.get("risk_score"), 50)

        blockers: list[str] = []
        warnings: list[str] = []

        if active_breakers > maximum_breakers:
            blockers.append("ACTIVE_CIRCUIT_BREAKER")
        if critical_events > 0:
            blockers.append("OPEN_CRITICAL_RISK_EVENT")
        if health_score < minimum_health:
            blockers.append("PORTFOLIO_HEALTH_BELOW_MINIMUM")
        if market_regime == "CRASH":
            blockers.append("CRASH_REGIME")

        weighted_candidates: list[dict[str, Any]] = []
        for row in scores:
            strategy_key = str(row.get("strategy_key") or "")
            eligible = bool(row.get("eligible"))
            composite = n(row.get("composite_score"))
            confidence = n(row.get("confidence_score"))
            risk_quality = n(row.get("risk_score"))
            regime_fit = n(row.get("regime_fit_score"))
            stability = n(row.get("stability_score"))

            reasons = json_list(row.get("disqualification_reasons"))
            adjustment_reasons: list[str] = []

            candidate_eligible = (
                eligible
                and composite >= min_score
                and confidence >= min_confidence
            )
            if not eligible:
                reasons.append("STRATEGY_SCORE_INELIGIBLE")
            if composite < min_score:
                reasons.append("SCORE_BELOW_POLICY_MINIMUM")
            if confidence < min_confidence:
                reasons.append("CONFIDENCE_BELOW_POLICY_MINIMUM")

            raw = (
                composite * score_weight
                + confidence * confidence_weight
                + risk_quality * risk_weight
                + regime_fit * regime_weight
            )

            catalog_rows = safe_get(
                client,
                "strategy_catalog_v47",
                f"strategy_key=eq.{strategy_key}&limit=1",
            )
            catalog = catalog_rows[0] if catalog_rows else {}
            risk_level = str(
                catalog.get("default_risk_level") or "MEDIUM"
            )

            if risk_level == "HIGH":
                raw *= n(
                    policy.get("high_risk_strategy_multiplier"),
                    0.5,
                )
                adjustment_reasons.append(
                    "HIGH_RISK_STRATEGY_MULTIPLIER"
                )

            if health_score < 60:
                raw *= n(
                    policy.get("low_health_exposure_multiplier"),
                    0.5,
                )
                adjustment_reasons.append(
                    "LOW_HEALTH_EXPOSURE_MULTIPLIER"
                )

            candidate = {
                "candidate_date": RUN_DATE,
                "portfolio_id": portfolio_id,
                "strategy_key": strategy_key,
                "strategy_score_id": row.get("id"),
                "market_regime": market_regime,
                "rank": int(n(row.get("rank"), 0)),
                "composite_score": composite,
                "confidence_score": confidence,
                "risk_score": risk_quality,
                "regime_fit_score": regime_fit,
                "stability_score": stability,
                "raw_weight": max(0.0, raw),
                "normalized_weight_pct": 0,
                "capped_weight_pct": 0,
                "final_candidate_weight_pct": 0,
                "eligible": candidate_eligible,
                "selected": False,
                "disqualification_reasons": reasons,
                "adjustment_reasons": adjustment_reasons,
                "diagnostics": {
                    "risk_level": risk_level,
                    "portfolio_health_score": health_score,
                    "policy_key": policy.get("policy_key"),
                    "engine_version": "4.9.1",
                },
            }
            weighted_candidates.append(candidate)
            candidates_generated += 1

        eligible_candidates = [
            row for row in weighted_candidates if row["eligible"]
        ]
        eligible_candidates.sort(
            key=lambda row: (
                -n(row.get("raw_weight")),
                -n(row.get("confidence_score")),
                int(n(row.get("rank"), 999)),
            )
        )
        eligible_candidates = eligible_candidates[:top_n]

        selected = apply_weight_cap(
            eligible_candidates,
            target_exposure=target_gross,
            max_weight=max_weight,
            min_weight=min_weight,
        )

        high_risk_total = sum(
            n(row.get("weight"))
            for row in selected
            if str(
                row.get("diagnostics", {}).get("risk_level")
            ) == "HIGH"
        )
        if high_risk_total > high_risk_cap and high_risk_total > 0:
            scale = high_risk_cap / high_risk_total
            for row in selected:
                if str(
                    row.get("diagnostics", {}).get("risk_level")
                ) == "HIGH":
                    row["weight"] = n(row.get("weight")) * scale
                    row["adjustment_reasons"].append(
                        "HIGH_RISK_TOTAL_WEIGHT_CAP"
                    )
            warnings.append("HIGH_RISK_WEIGHT_REDUCED")

        selected_by_key = {
            str(row["strategy_key"]): row for row in selected
        }
        selected_total = sum(
            n(row.get("weight")) for row in selected
        )
        selected_total = min(selected_total, max_gross)
        cash_weight = clamp(100 - selected_total, min_cash, 100)

        for candidate in weighted_candidates:
            strategy_key = str(candidate["strategy_key"])
            selected_row = selected_by_key.get(strategy_key)
            if selected_row:
                final_weight = n(selected_row.get("weight"))
                candidate["selected"] = True
                candidate["normalized_weight_pct"] = final_weight
                candidate["capped_weight_pct"] = final_weight
                candidate["final_candidate_weight_pct"] = final_weight

            client.upsert(
                "allocation_candidates_v48",
                candidate,
                "candidate_date,portfolio_id,strategy_key",
            )

        if not selected and not blockers:
            blockers.append("NO_ELIGIBLE_ALLOCATION_CANDIDATES")

        if blockers:
            allocation_status = "BLOCKED"
            final_gross = 0.0
            cash_weight = 100.0
            selected = []
            allocations_blocked += 1
            critical_findings += 1
        elif selected_total + 0.01 < target_gross:
            allocation_status = "REDUCED"
            final_gross = selected_total
            allocations_reduced += 1
            warning_findings += 1
        elif warnings:
            allocation_status = "WARNING"
            final_gross = selected_total
            warning_findings += 1
        else:
            allocation_status = "APPROVED"
            final_gross = selected_total
            allocations_approved += 1

        strategy_allocations = [
            {
                "strategy_key": str(row["strategy_key"]),
                "weight_pct": round(n(row.get("weight")), 6),
                "composite_score": n(row.get("composite_score")),
                "confidence_score": n(row.get("confidence_score")),
                "risk_score": n(row.get("risk_score")),
                "regime_fit_score": n(row.get("regime_fit_score")),
            }
            for row in selected
        ]

        allocation_score = (
            mean(
                [
                    n(row.get("composite_score"))
                    for row in selected
                ]
            )
            if selected
            else 0
        )
        allocation_confidence = (
            mean(
                [
                    n(row.get("confidence_score"))
                    for row in selected
                ]
            )
            if selected
            else 0
        )

        allocation_payload = {
            "allocation_date": RUN_DATE,
            "portfolio_id": portfolio_id,
            "policy_id": policy.get("id"),
            "market_regime": market_regime,
            "allocation_status": allocation_status,
            "target_gross_exposure_pct": target_gross,
            "final_gross_exposure_pct": final_gross,
            "cash_weight_pct": cash_weight,
            "leverage": max_leverage,
            "selected_strategy_count": len(selected),
            "total_candidate_count": len(weighted_candidates),
            "allocation_score": allocation_score,
            "risk_score": health_risk_score,
            "confidence_score": allocation_confidence,
            "strategy_allocations": strategy_allocations,
            "constraints_applied": list(constraints.keys()),
            "blockers": blockers,
            "warnings": warnings,
            "rationale": (
                f"Portfolio {portfolio_key}: {allocation_status}; "
                f"regime {market_regime}; selected "
                f"{len(selected)} strategy(s); gross exposure "
                f"{final_gross:.2f}%; cash {cash_weight:.2f}%."
            ),
            "diagnostics": {
                "engine_version": "4.9.1",
                "posture": posture,
                "health_score": health_score,
                "active_breakers": active_breakers,
                "critical_events": critical_events,
            },
            "execution_status": (
                "APPROVED_FOR_PAPER"
                if allocation_status in ("APPROVED", "REDUCED", "WARNING")
                else "REJECTED"
            ),
            "paper_approved": True,
            "live_approved": False,
            "autonomous_execution_enabled": False,
            "broker_submission_enabled": False,
        }
        client.upsert(
            "portfolio_allocations_v48",
            allocation_payload,
            "allocation_date,portfolio_id",
        )
        allocation_rows = client.get(
            "portfolio_allocations_v48",
            (
                f"allocation_date=eq.{RUN_DATE}"
                f"&portfolio_id=eq.{portfolio_id}&limit=1"
            ),
        )
        allocation_id = (
            allocation_rows[0].get("id") if allocation_rows else None
        )

        current_weights = current_weight_map(client, portfolio_id)
        target_weights = {
            str(row["strategy_key"]): n(row.get("weight"))
            for row in selected
        }

        all_symbols = sorted(
            set(current_weights.keys()) | set(target_weights.keys())
        )
        turnover = 0.0
        decisions_created = 0
        trade_plan_ids: list[str] = []

        for symbol in all_symbols:
            current = n(current_weights.get(symbol))
            target = n(target_weights.get(symbol))
            delta = target - current
            turnover += abs(delta)

            source = selected_by_key.get(symbol, {})
            confidence = n(source.get("confidence_score"))
            reason = (
                f"Target strategy weight derived from 4.7.1 score, "
                f"4.8 constraints and {market_regime} regime."
            )

            client.upsert(
                "portfolio_target_weights_v49",
                {
                    "weight_date": RUN_DATE,
                    "portfolio_id": portfolio_id,
                    "strategy_key": symbol,
                    "asset_symbol": symbol,
                    "asset_type": "STRATEGY",
                    "current_weight_pct": current,
                    "target_weight_pct": target,
                    "delta_weight_pct": delta,
                    "confidence": confidence,
                    "priority": int(n(source.get("rank"), 100)),
                    "source_allocation_id": allocation_id,
                    "reason": reason,
                    "constraints_applied": list(constraints.keys()),
                    "diagnostics": {
                        "engine_version": "4.9.1",
                        "allocation_status": allocation_status,
                    },
                    "paper_approved": True,
                    "live_approved": False,
                },
                "weight_date,portfolio_id,asset_symbol",
            )

            if abs(delta) >= n(
                policy.get("rebalance_threshold_pct"),
                5,
            ):
                action = classify_action(current, target)
                decision_type = (
                    "STRATEGY_CHANGE"
                    if current == 0 or target == 0
                    else "TARGET_WEIGHT_CHANGE"
                )
                entity_key = symbol

                client.upsert(
                    "allocation_decisions_v49",
                    {
                        "decision_date": RUN_DATE,
                        "portfolio_id": portfolio_id,
                        "decision_type": decision_type,
                        "entity_key": entity_key,
                        "previous_value": {
                            "weight_pct": current,
                        },
                        "new_value": {
                            "weight_pct": target,
                            "delta_weight_pct": delta,
                        },
                        "reason": reason,
                        "confidence": confidence,
                        "decision_status": (
                            "APPROVED_FOR_PAPER"
                            if allocation_status != "BLOCKED"
                            else "REJECTED"
                        ),
                        "source_modules": [
                            "market_regime_ai_v46",
                            "strategy_scores_v47",
                            "allocation_constraints_v48",
                            "enterprise491_portfolio_optimizer",
                        ],
                    },
                    (
                        "decision_date,portfolio_id,"
                        "decision_type,entity_key"
                    ),
                )
                decisions_created += 1

                client.upsert(
                    "trade_plans_v49",
                    {
                        "trade_date": RUN_DATE,
                        "portfolio_id": portfolio_id,
                        "rebalance_plan_id": None,
                        "symbol": symbol,
                        "asset_type": "STRATEGY",
                        "strategy_key": symbol,
                        "action": action,
                        "target_weight_pct": target,
                        "quantity": None,
                        "entry_price": None,
                        "stop_loss_price": None,
                        "take_profit_price": None,
                        "confidence": confidence,
                        "risk_level": str(
                            source.get("diagnostics", {}).get(
                                "risk_level",
                                "MEDIUM",
                            )
                        ),
                        "priority": int(n(source.get("rank"), 100)),
                        "reason": reason,
                        "evidence": {
                            "current_weight_pct": current,
                            "target_weight_pct": target,
                            "delta_weight_pct": delta,
                            "allocation_status": allocation_status,
                        },
                        "status": (
                            "READY"
                            if allocation_status != "BLOCKED"
                            else "CANCELLED"
                        ),
                        "paper_approved": True,
                        "live_approved": False,
                        "broker_submission_enabled": False,
                    },
                    "trade_date,portfolio_id,symbol,action",
                )

                trade_rows = client.get(
                    "trade_plans_v49",
                    (
                        f"trade_date=eq.{RUN_DATE}"
                        f"&portfolio_id=eq.{portfolio_id}"
                        f"&symbol=eq.{symbol}"
                        f"&action=eq.{action}&limit=1"
                    ),
                )
                if trade_rows:
                    trade_plan_id = str(trade_rows[0]["id"])
                    trade_plan_ids.append(trade_plan_id)
                    client.upsert(
                        "execution_queue_v49",
                        {
                            "trade_plan_id": trade_plan_id,
                            "broker": "PAPER",
                            "queue_time": datetime.now(
                                timezone.utc
                            ).isoformat(),
                            "execute_after": None,
                            "status": (
                                "READY"
                                if allocation_status != "BLOCKED"
                                else "CANCELLED"
                            ),
                            "retry_count": 0,
                            "max_retries": 0,
                            "request_payload": {
                                "symbol": symbol,
                                "action": action,
                                "target_weight_pct": target,
                                "paper_only": True,
                            },
                            "response_payload": {},
                            "error_message": None,
                            "paper_only": True,
                            "live_submission_enabled": False,
                        },
                        "trade_plan_id",
                    )

        rebalance_required = (
            turnover >= n(policy.get("rebalance_threshold_pct"), 5)
            and allocation_status != "BLOCKED"
        )
        rebalance_status = (
            "APPROVED_FOR_PAPER"
            if rebalance_required
            else "BLOCKED"
            if allocation_status == "BLOCKED"
            else "COMPLETED"
        )

        client.upsert(
            "rebalance_plans_v49",
            {
                "plan_date": RUN_DATE,
                "portfolio_id": portfolio_id,
                "market_regime": market_regime,
                "rebalance_required": rebalance_required,
                "rebalance_status": rebalance_status,
                "risk_score": health_risk_score,
                "current_cash_pct": clamp(
                    100 - sum(current_weights.values())
                ),
                "target_cash_pct": cash_weight,
                "current_gross_exposure_pct": sum(
                    current_weights.values()
                ),
                "target_gross_exposure_pct": final_gross,
                "expected_turnover_pct": turnover,
                "trigger_reasons": (
                    ["TARGET_WEIGHT_DRIFT"]
                    if rebalance_required
                    else []
                ),
                "blockers": blockers,
                "notes": allocation_payload["rationale"],
                "diagnostics": {
                    "allocation_id": allocation_id,
                    "decisions_created": decisions_created,
                    "trade_plan_count": len(trade_plan_ids),
                    "engine_version": "4.9.1",
                },
                "paper_approved": True,
                "live_approved": False,
                "autonomous_execution_enabled": False,
            },
            "plan_date,portfolio_id",
        )

        client.upsert(
            "portfolio_health_v49",
            {
                "health_date": RUN_DATE,
                "portfolio_id": portfolio_id,
                "health_status": (
                    "CRITICAL"
                    if allocation_status == "BLOCKED"
                    else "WARNING"
                    if allocation_status in ("REDUCED", "WARNING")
                    else "PASS"
                ),
                "health_score": health_score,
                "risk_score": health_risk_score,
                "cash_score": clamp(cash_weight),
                "diversification_score": clamp(
                    len(selected) / max(top_n, 1) * 100
                ),
                "regime_fit_score": (
                    mean(
                        [
                            n(row.get("regime_fit_score"))
                            for row in selected
                        ]
                    )
                    if selected
                    else 0
                ),
                "correlation_score": 50,
                "drawdown_score": n(
                    health.get("drawdown_score"),
                    50,
                ),
                "execution_readiness_score": (
                    0 if allocation_status == "BLOCKED" else 80
                ),
                "blockers": blockers,
                "warnings": warnings,
                "remarks": allocation_payload["rationale"],
                "diagnostics": {
                    "engine_version": "4.9.1",
                    "selected_strategy_count": len(selected),
                    "target_gross_exposure_pct": final_gross,
                },
            },
            "health_date,portfolio_id",
        )

        portfolios_processed += 1
        selected_count_total += len(selected)
        allocations_generated += 1
        allocation_scores.append(allocation_score)
        confidence_scores.append(allocation_confidence)
        gross_exposures.append(final_gross)
        cash_weights.append(cash_weight)

    runtime = time.perf_counter() - started
    overall_status = (
        "CRITICAL"
        if allocations_blocked > 0 or critical_findings > 0
        else "WARNING"
        if allocations_reduced > 0 or warning_findings > 0
        else "PASS"
    )

    summary = (
        f"Enterprise 4.9.1 processed {portfolios_processed} "
        f"portfolio(s), generated {allocations_generated} "
        f"allocation(s), selected {selected_count_total} "
        f"strategy allocation(s), and produced "
        f"{allocations_blocked} blocked allocation(s)."
    )

    client.upsert(
        "allocation_engine_status_v48",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "market_regime": market_regime,
            "portfolios_processed": portfolios_processed,
            "candidates_generated": candidates_generated,
            "candidates_selected": selected_count_total,
            "allocations_generated": allocations_generated,
            "allocations_approved": allocations_approved,
            "allocations_reduced": allocations_reduced,
            "allocations_blocked": allocations_blocked,
            "average_allocation_score": (
                mean(allocation_scores) if allocation_scores else 0
            ),
            "average_confidence_score": (
                mean(confidence_scores) if confidence_scores else 0
            ),
            "average_gross_exposure_pct": (
                mean(gross_exposures) if gross_exposures else 0
            ),
            "average_cash_weight_pct": (
                mean(cash_weights) if cash_weights else 100
            ),
            "critical_findings": critical_findings,
            "warning_findings": warning_findings,
            "paper_mode_enabled": True,
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
            "broker_submission_enabled": False,
            "blockers": (
                ["BLOCKED_ALLOCATIONS_PRESENT"]
                if allocations_blocked
                else []
            ),
            "highlights": [
                f"Market regime: {market_regime}",
                f"Candidates generated: {candidates_generated}",
                f"Strategies selected: {selected_count_total}",
            ],
            "summary": summary,
            "diagnostics": {
                "engine_version": "4.9.1",
                "runtime_seconds": runtime,
                "policy_key": policy.get("policy_key"),
            },
        },
        "status_date",
    )

    client.upsert(
        "optimization_runs_v49",
        {
            "run_date": RUN_DATE,
            "run_key": "PORTFOLIO_OPTIMIZER",
            "portfolios_processed": portfolios_processed,
            "strategies_processed": candidates_generated,
            "assets_processed": selected_count_total,
            "optimizer_version": "4.9.1",
            "optimizer_method": "RULE_BASED",
            "status": overall_status,
            "runtime_seconds": runtime,
            "objective_score": (
                mean(allocation_scores) if allocation_scores else 0
            ),
            "remarks": summary,
            "diagnostics": {
                "market_regime": market_regime,
                "allocations_approved": allocations_approved,
                "allocations_reduced": allocations_reduced,
                "allocations_blocked": allocations_blocked,
            },
            "paper_mode_enabled": True,
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
        },
        "run_date,run_key",
    )

    print(summary)
    print(
        f"Enterprise 4.9.1 Portfolio Optimizer status: "
        f"{overall_status}"
    )


if __name__ == "__main__":
    main()
