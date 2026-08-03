from __future__ import annotations

import math
import os
import time
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
    rows = client.get(table, query)
    return rows[0] if rows else {}


def constraint_map(client) -> dict[str, dict[str, Any]]:
    rows = client.get(
        "execution_constraints_v52",
        "enabled=eq.true&paper_only=eq.true&live_enabled=eq.false&limit=100",
    )
    return {str(row["constraint_key"]): row for row in rows}


def value(constraints: dict[str, dict[str, Any]], key: str, fallback: float) -> float:
    return n(constraints.get(key, {}).get("numeric_value"), fallback)


def audit(client, plan_id, order_id, event_type, status, message, previous=None, new=None):
    client.insert(
        "execution_audit_v52",
        {
            "audit_time": now(),
            "audit_date": RUN_DATE,
            "plan_id": plan_id,
            "order_id": order_id,
            "event_type": event_type,
            "event_status": status,
            "actor": "ENTERPRISE52_EXECUTION_LAYER",
            "message": message,
            "previous_state": previous or {},
            "new_state": new or {},
            "metadata": {"paper_only": True, "engine_version": "5.2.0"},
        },
    )


def risk_check(
    client,
    plan_id,
    order_id,
    constraint_key,
    scope,
    observed,
    limit_value,
    status,
    severity,
    action,
    message,
):
    client.insert(
        "execution_risk_checks_v52",
        {
            "plan_id": plan_id,
            "order_id": order_id,
            "constraint_key": constraint_key,
            "check_scope": scope,
            "observed_value": observed,
            "limit_value": limit_value,
            "check_status": status,
            "severity": severity,
            "action_taken": action,
            "message": message,
            "evidence": {"paper_only": True},
        },
    )


def main() -> None:
    started = time.perf_counter()
    client = SupabaseRestClient()
    constraints = constraint_map(client)

    council = latest(client, "decision_council_v51", "decision_date")
    if not council:
        raise SystemExit("No decision_council_v51 record found")

    session_id = council.get("session_id")
    session = {}
    if session_id:
        rows = client.get("council_sessions_v51", f"id=eq.{session_id}&limit=1")
        session = rows[0] if rows else {}

    portfolios = client.get(
        "enterprise_portfolios_v40",
        "lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100",
    )
    if not portfolios:
        raise SystemExit("No active PAPER portfolios")

    final_decision = str(council.get("final_decision") or "BLOCK")
    target_exposure = n(council.get("recommended_exposure_pct"), 0)
    target_cash = n(council.get("recommended_cash_pct"), 100)
    market_regime = str(council.get("market_regime") or "UNKNOWN")
    council_confidence = n(council.get("final_confidence"), 0)

    max_change = value(constraints, "MAX_ORDER_WEIGHT_CHANGE_PCT", 25)
    max_turnover = value(constraints, "MAX_DAILY_TURNOVER_PCT", 60)
    min_confidence = value(constraints, "MIN_ORDER_CONFIDENCE", 40)
    max_gross = value(constraints, "MAX_GROSS_EXPOSURE_PCT", 100)
    min_cash = value(constraints, "MIN_CASH_PCT", 20)

    total_plans = plans_approved = plans_blocked = 0
    total_batches = total_orders = 0
    approved_orders = reduced_orders = rejected_orders = 0
    checks_run = checks_failed = 0
    confidences = []
    turnovers = []
    latest_plan_id = None
    global_blockers = []
    global_warnings = []

    for portfolio in portfolios:
        portfolio_id = str(portfolio["id"])

        target_rows = client.get(
            "portfolio_target_weights_v49",
            (
                f"portfolio_id=eq.{portfolio_id}"
                "&order=weight_date.desc,priority.asc&limit=100"
            ),
        )
        if target_rows:
            latest_weight_date = str(target_rows[0].get("weight_date") or "")
            target_rows = [
                row for row in target_rows
                if str(row.get("weight_date") or "") == latest_weight_date
            ]

        trade_rows = client.get(
            "trade_plans_v49",
            (
                f"portfolio_id=eq.{portfolio_id}"
                "&order=trade_date.desc,priority.asc&limit=100"
            ),
        )
        if trade_rows:
            latest_trade_date = str(trade_rows[0].get("trade_date") or "")
            trade_rows = [
                row for row in trade_rows
                if str(row.get("trade_date") or "") == latest_trade_date
            ]

        turnover = sum(abs(n(row.get("delta_weight_pct"))) for row in target_rows)
        turnovers.append(turnover)

        blockers = []
        warnings = []

        if final_decision == "BLOCK":
            blockers.append("COUNCIL_DECISION_BLOCK")
        if target_exposure > max_gross:
            blockers.append("MAX_GROSS_EXPOSURE_BREACH")
        if target_cash < min_cash:
            blockers.append("MIN_CASH_BREACH")
        if turnover > max_turnover:
            blockers.append("MAX_DAILY_TURNOVER_BREACH")
        if council_confidence < min_confidence:
            warnings.append("COUNCIL_CONFIDENCE_BELOW_ORDER_MINIMUM")

        plan_status = "BLOCKED" if blockers else "VALIDATED"

        client.upsert(
            "execution_plans_v52",
            {
                "plan_date": RUN_DATE,
                "portfolio_id": portfolio_id,
                "council_decision_id": council.get("id"),
                "session_id": session_id,
                "cycle_id": council.get("cycle_id"),
                "market_regime": market_regime,
                "final_decision": final_decision,
                "execution_mode": "PAPER",
                "plan_status": plan_status,
                "target_exposure_pct": target_exposure,
                "target_cash_pct": target_cash,
                "expected_turnover_pct": turnover,
                "expected_order_count": len(trade_rows),
                "approved_order_count": 0,
                "rejected_order_count": 0,
                "blockers": blockers,
                "warnings": warnings,
                "rationale": str(council.get("rationale") or "Council-derived Paper execution plan."),
                "diagnostics": {
                    "engine_version": "5.2.0",
                    "session_status": session.get("session_status"),
                    "council_confidence": council_confidence,
                },
                "paper_approved": True,
                "live_approved": False,
                "broker_submission_enabled": False,
            },
            "plan_date,portfolio_id,council_decision_id",
        )

        plans = client.get(
            "execution_plans_v52",
            (
                f"plan_date=eq.{RUN_DATE}"
                f"&portfolio_id=eq.{portfolio_id}"
                f"&council_decision_id=eq.{council.get('id')}&limit=1"
            ),
        )
        plan_id = str(plans[0]["id"])
        latest_plan_id = plan_id
        total_plans += 1

        audit(
            client,
            plan_id,
            None,
            "PLAN_CREATED",
            plan_status,
            f"Execution plan created for portfolio {portfolio_id}.",
            new={"status": plan_status, "turnover": turnover},
        )

        checks = [
            (
                "BLOCK_COUNCIL_DECISION",
                None,
                None,
                "BLOCKED" if final_decision == "BLOCK" else "PASS",
                "CRITICAL",
                "BLOCK" if final_decision == "BLOCK" else "NONE",
                f"Council final decision is {final_decision}.",
            ),
            (
                "MAX_GROSS_EXPOSURE_PCT",
                target_exposure,
                max_gross,
                "BLOCKED" if target_exposure > max_gross else "PASS",
                "CRITICAL",
                "BLOCK" if target_exposure > max_gross else "NONE",
                f"Target exposure {target_exposure:.2f}% vs max {max_gross:.2f}%.",
            ),
            (
                "MIN_CASH_PCT",
                target_cash,
                min_cash,
                "BLOCKED" if target_cash < min_cash else "PASS",
                "CRITICAL",
                "BLOCK" if target_cash < min_cash else "NONE",
                f"Target cash {target_cash:.2f}% vs min {min_cash:.2f}%.",
            ),
            (
                "MAX_DAILY_TURNOVER_PCT",
                turnover,
                max_turnover,
                "BLOCKED" if turnover > max_turnover else "PASS",
                "CRITICAL",
                "BLOCK" if turnover > max_turnover else "NONE",
                f"Expected turnover {turnover:.2f}% vs max {max_turnover:.2f}%.",
            ),
        ]

        for key, observed, limit_val, status, severity, action, message in checks:
            checks_run += 1
            if status != "PASS":
                checks_failed += 1
            risk_check(
                client, plan_id, None, key, "PORTFOLIO",
                observed, limit_val, status, severity, action, message
            )

        if blockers:
            plans_blocked += 1
            global_blockers.extend(blockers)
            client.patch(
                "execution_plans_v52",
                f"id=eq.{plan_id}",
                {
                    "plan_status": "BLOCKED",
                    "approved_order_count": 0,
                    "rejected_order_count": len(trade_rows),
                },
            )
            for trade in trade_rows:
                client.upsert(
                    "execution_orders_v52",
                    {
                        "plan_id": plan_id,
                        "batch_id": None,
                        "portfolio_id": portfolio_id,
                        "source_trade_plan_id": trade.get("id"),
                        "symbol": trade.get("symbol"),
                        "asset_type": trade.get("asset_type", "STRATEGY"),
                        "side": trade.get("action", "HOLD"),
                        "order_type": "TARGET_WEIGHT",
                        "target_weight_pct": n(trade.get("target_weight_pct")),
                        "current_weight_pct": 0,
                        "delta_weight_pct": n(trade.get("target_weight_pct")),
                        "quantity": None,
                        "estimated_price": None,
                        "estimated_value": 0,
                        "priority": int(n(trade.get("priority"), 100)),
                        "confidence": n(trade.get("confidence")),
                        "risk_level": trade.get("risk_level", "MEDIUM"),
                        "order_status": "REJECTED",
                        "validation_status": "BLOCKED",
                        "rejection_reason": ",".join(blockers),
                        "reason": trade.get("reason", "Blocked by execution plan."),
                        "evidence": {"plan_blockers": blockers},
                        "paper_only": True,
                        "live_submission_enabled": False,
                    },
                    "plan_id,symbol,side",
                )
                rejected_orders += 1
                total_orders += 1
            continue

        client.insert(
            "execution_batches_v52",
            {
                "plan_id": plan_id,
                "batch_no": 1,
                "batch_status": "DRAFT",
                "priority": 100,
                "scheduled_at": now(),
                "order_count": len(trade_rows),
                "approved_count": 0,
                "rejected_count": 0,
                "estimated_value": 0,
                "estimated_turnover_pct": turnover,
                "paper_only": True,
                "live_submission_enabled": False,
                "metadata": {"engine_version": "5.2.0"},
            },
        )
        batches = client.get(
            "execution_batches_v52",
            f"plan_id=eq.{plan_id}&batch_no=eq.1&limit=1",
        )
        batch_id = str(batches[0]["id"])
        total_batches += 1

        plan_approved = 0
        plan_rejected = 0

        for trade in trade_rows:
            symbol = str(trade.get("symbol") or "UNKNOWN")
            side = str(trade.get("action") or "HOLD")
            target_weight = n(trade.get("target_weight_pct"))
            confidence = n(trade.get("confidence"))
            confidence_status = "PASS" if confidence >= min_confidence else "BLOCKED"
            change_status = "PASS"
            adjusted_target = target_weight
            validation = "APPROVED"
            order_status = "READY"
            rejection_reason = None

            if abs(target_weight) > max_change:
                adjusted_target = math.copysign(max_change, target_weight)
                validation = "REDUCED"
                change_status = "WARNING"
                reduced_orders += 1
                warnings.append(f"{symbol}:ORDER_WEIGHT_REDUCED")

            if confidence < min_confidence:
                validation = "BLOCKED"
                order_status = "REJECTED"
                rejection_reason = "MIN_ORDER_CONFIDENCE"
                plan_rejected += 1
                rejected_orders += 1
            else:
                plan_approved += 1
                approved_orders += 1
                confidences.append(confidence)

            client.upsert(
                "execution_orders_v52",
                {
                    "plan_id": plan_id,
                    "batch_id": batch_id,
                    "portfolio_id": portfolio_id,
                    "source_trade_plan_id": trade.get("id"),
                    "symbol": symbol,
                    "asset_type": trade.get("asset_type", "STRATEGY"),
                    "side": side,
                    "order_type": "TARGET_WEIGHT",
                    "target_weight_pct": adjusted_target,
                    "current_weight_pct": 0,
                    "delta_weight_pct": adjusted_target,
                    "quantity": None,
                    "estimated_price": None,
                    "estimated_value": 0,
                    "priority": int(n(trade.get("priority"), 100)),
                    "confidence": confidence,
                    "risk_level": trade.get("risk_level", "MEDIUM"),
                    "order_status": order_status,
                    "validation_status": validation,
                    "rejection_reason": rejection_reason,
                    "reason": trade.get("reason", "Council and optimizer generated Paper order."),
                    "evidence": {
                        "original_target_weight_pct": target_weight,
                        "council_decision": final_decision,
                    },
                    "paper_only": True,
                    "live_submission_enabled": False,
                },
                "plan_id,symbol,side",
            )

            order_rows = client.get(
                "execution_orders_v52",
                (
                    f"plan_id=eq.{plan_id}"
                    f"&symbol=eq.{symbol}"
                    f"&side=eq.{side}&limit=1"
                ),
            )
            order_id = str(order_rows[0]["id"])
            total_orders += 1

            checks_run += 2
            if confidence_status != "PASS":
                checks_failed += 1
            risk_check(
                client, plan_id, order_id,
                "MIN_ORDER_CONFIDENCE", "ORDER",
                confidence, min_confidence,
                confidence_status, "WARNING",
                "BLOCK" if confidence_status != "PASS" else "NONE",
                f"Order confidence {confidence:.2f} vs minimum {min_confidence:.2f}.",
            )

            if change_status != "PASS":
                checks_failed += 1
            risk_check(
                client, plan_id, order_id,
                "MAX_ORDER_WEIGHT_CHANGE_PCT", "ORDER",
                abs(target_weight), max_change,
                change_status, "CRITICAL",
                "REDUCE" if change_status != "PASS" else "NONE",
                f"Order weight change {abs(target_weight):.2f}% vs max {max_change:.2f}%.",
            )

            audit(
                client,
                plan_id,
                order_id,
                "ORDER_VALIDATED",
                validation,
                f"Order {symbol} validation result: {validation}.",
                previous={"target_weight_pct": target_weight},
                new={"target_weight_pct": adjusted_target, "status": order_status},
            )

        batch_status = "READY" if plan_approved > 0 else "BLOCKED"
        client.patch(
            "execution_batches_v52",
            f"id=eq.{batch_id}",
            {
                "batch_status": batch_status,
                "approved_count": plan_approved,
                "rejected_count": plan_rejected,
            },
        )

        final_plan_status = "APPROVED_FOR_PAPER" if plan_approved > 0 else "BLOCKED"
        client.patch(
            "execution_plans_v52",
            f"id=eq.{plan_id}",
            {
                "plan_status": final_plan_status,
                "approved_order_count": plan_approved,
                "rejected_order_count": plan_rejected,
                "warnings": warnings,
            },
        )

        if final_plan_status == "APPROVED_FOR_PAPER":
            plans_approved += 1
        else:
            plans_blocked += 1

        global_warnings.extend(warnings)

        audit(
            client,
            plan_id,
            None,
            "PLAN_VALIDATED",
            final_plan_status,
            f"Execution plan validation completed with {plan_approved} approved order(s).",
            new={
                "approved_orders": plan_approved,
                "rejected_orders": plan_rejected,
                "batch_status": batch_status,
            },
        )

        client.upsert(
            "execution_metrics_v52",
            {
                "metric_date": RUN_DATE,
                "plan_id": plan_id,
                "plans_created": 1,
                "batches_created": 1,
                "orders_created": len(trade_rows),
                "approved_orders": plan_approved,
                "reduced_orders": len([w for w in warnings if "ORDER_WEIGHT_REDUCED" in w]),
                "rejected_orders": plan_rejected,
                "blocked_plans": 1 if final_plan_status == "BLOCKED" else 0,
                "average_confidence": mean(confidences) if confidences else 0,
                "expected_turnover_pct": turnover,
                "estimated_total_value": 0,
                "runtime_seconds": time.perf_counter() - started,
                "diagnostics": {"engine_version": "5.2.0"},
            },
            "metric_date,plan_id",
        )

    runtime = time.perf_counter() - started
    overall_status = (
        "CRITICAL" if plans_blocked and not plans_approved
        else "WARNING" if plans_blocked or rejected_orders or reduced_orders
        else "PASS"
    )

    summary = (
        f"Enterprise 5.2 created {total_plans} plan(s), "
        f"{total_batches} batch(es), {total_orders} order(s); "
        f"approved {approved_orders}, reduced {reduced_orders}, "
        f"rejected {rejected_orders}."
    )

    client.upsert(
        "execution_status_v52",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_plan_id": latest_plan_id,
            "plans_created": total_plans,
            "plans_approved": plans_approved,
            "plans_blocked": plans_blocked,
            "batches_created": total_batches,
            "orders_created": total_orders,
            "orders_approved": approved_orders,
            "orders_reduced": reduced_orders,
            "orders_rejected": rejected_orders,
            "risk_checks_run": checks_run,
            "risk_checks_failed": checks_failed,
            "average_confidence": mean(confidences) if confidences else 0,
            "expected_turnover_pct": mean(turnovers) if turnovers else 0,
            "paper_mode_enabled": True,
            "live_trading_enabled": False,
            "broker_submission_enabled": False,
            "blockers": sorted(set(global_blockers)),
            "warnings": sorted(set(global_warnings)),
            "summary": summary,
            "diagnostics": {
                "engine_version": "5.2.0",
                "runtime_seconds": runtime,
                "council_decision_id": council.get("id"),
            },
        },
        "status_date",
    )

    print(summary)
    print(f"Enterprise 5.2 Execution Intelligence status: {overall_status}")

    if overall_status == "CRITICAL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
