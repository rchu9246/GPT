from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.7.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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
    order_field: str,
    where: str = "",
) -> dict[str, Any]:
    query = (
        f"{where}&order={order_field}.desc&limit=1"
        if where
        else f"order={order_field}.desc&limit=1"
    )
    rows = read(client, table, query)
    return rows[0] if rows else {}


def evaluate_rule(
    rule: dict[str, Any],
    ranking: dict[str, Any],
) -> tuple[bool, str, float | None, str | None]:
    rule_type = str(rule.get("rule_type") or "")
    operator = str(rule.get("comparison_operator") or "")
    numeric_threshold = rule.get("numeric_threshold")
    text_threshold = rule.get("text_threshold")

    observed_numeric: float | None = None
    observed_text: str | None = None

    if rule_type == "RANK":
        observed_numeric = num(ranking.get("rank_no"))
    elif rule_type == "EVOLUTION_SCORE":
        observed_numeric = num(ranking.get("evolution_score"))
    elif rule_type == "CONFIDENCE_SCORE":
        observed_numeric = num(ranking.get("confidence_score"))
    elif rule_type == "RECOMMENDATION":
        observed_text = str(ranking.get("recommendation") or "")
    elif rule_type == "SELECTED_FOR_REVIEW":
        observed_text = str(bool(ranking.get("selected_for_review"))).lower()
    else:
        return True, "Rule not evaluated by v2.0 engine.", None, None

    passed = True

    if observed_numeric is not None:
        threshold = num(numeric_threshold)
        if operator == "EQ":
            passed = observed_numeric == threshold
        elif operator == "NE":
            passed = observed_numeric != threshold
        elif operator == "GT":
            passed = observed_numeric > threshold
        elif operator == "GTE":
            passed = observed_numeric >= threshold
        elif operator == "LT":
            passed = observed_numeric < threshold
        elif operator == "LTE":
            passed = observed_numeric <= threshold
    else:
        expected = str(text_threshold or "")
        if operator == "EQ":
            passed = observed_text == expected
        elif operator == "NE":
            passed = observed_text != expected
        elif operator == "TRUE":
            passed = observed_text == "true"
        elif operator == "FALSE":
            passed = observed_text == "false"
        elif operator == "IN":
            allowed = {item.strip() for item in expected.split(",") if item.strip()}
            passed = observed_text in allowed

    message = (
        f"{rule.get('rule_key')}: PASS"
        if passed
        else f"{rule.get('rule_key')}: FAIL"
    )
    return passed, message, observed_numeric, observed_text


def main() -> None:
    client = SupabaseRestClient()
    run_id = str(uuid.uuid4())

    max_rankings = integer(os.getenv("ENTERPRISE57_MAX_RANKINGS"), 20)

    rankings = read(
        client,
        "portfolio_rankings_v56",
        (
            "order=ranking_date.desc,rank_no.asc"
            f"&limit={max_rankings}"
        ),
        required=True,
    )

    rules = read(
        client,
        "promotion_rules_v57",
        "enabled=eq.true&order=rule_order.asc&limit=100",
        required=True,
    )

    baseline = latest(
        client,
        "baseline_versions_v57",
        "created_at",
        "active=eq.true&baseline_status=eq.CURRENT_BASELINE",
    )
    current_baseline_version = str(
        baseline.get("version_no") or "5.7-baseline-0001"
    )

    blockers: list[str] = []
    warnings: list[str] = []

    rankings_read = 0
    candidates_created = 0
    candidates_eligible = 0
    candidates_rejected = 0
    candidates_retest_required = 0
    rule_evaluations = 0
    rule_failures = 0
    human_reviews_created = 0
    human_reviews_pending = 0
    human_reviews_approved = 0
    promotion_plans_created = 0
    baselines_registered = 1
    eligibility_scores: list[float] = []

    current_top_candidate_version = None
    current_review_request_id = None
    current_promotion_plan_id = None

    if not rankings:
        blockers.append("NO_PORTFOLIO_RANKINGS_V56")

    for ranking in rankings:
        rankings_read += 1

        ranking_id = str(ranking["id"])
        source_version_id = ranking.get("version_id")
        version_rows = read(
            client,
            "portfolio_versions_v56",
            f"id=eq.{source_version_id}&limit=1",
        )
        version = version_rows[0] if version_rows else {}
        source_version_no = str(
            version.get("version_no")
            or ranking.get("version_no")
            or f"UNKNOWN-{ranking_id[:8]}"
        )

        rank_no = integer(ranking.get("rank_no"), 999)
        evolution_score = num(ranking.get("evolution_score"))
        confidence_score = num(ranking.get("confidence_score"))
        recommendation = str(ranking.get("recommendation") or "HOLD")
        selected_for_review = bool(ranking.get("selected_for_review"))

        candidate_key = f"BASELINE_PROMOTION:{source_version_no}"

        client.upsert(
            "promotion_candidates_v57",
            {
                "candidate_date": RUN_DATE,
                "candidate_key": candidate_key,
                "source_ranking_id": ranking_id,
                "source_version_id": source_version_id,
                "source_version_no": source_version_no,
                "baseline_version_no": current_baseline_version,
                "rank_no": rank_no,
                "evolution_score": evolution_score,
                "confidence_score": confidence_score,
                "source_recommendation": recommendation,
                "source_selected_for_review": selected_for_review,
                "candidate_status": "EVALUATING",
                "eligibility_status": "NOT_EVALUATED",
                "eligibility_score": 0,
                "rejection_reason": None,
                "human_approval_required": True,
                "automatic_promotion_enabled": False,
                "paper_only": True,
                "live_trading_enabled": False,
                "metadata": {
                    "run_id": run_id,
                    "engine_version": ENGINE_VERSION,
                },
            },
            "candidate_date,candidate_key",
        )

        candidate = read(
            client,
            "promotion_candidates_v57",
            (
                f"candidate_date=eq.{RUN_DATE}"
                f"&candidate_key=eq.{candidate_key}"
                "&limit=1"
            ),
            required=True,
        )[0]
        candidate_id = str(candidate["id"])
        candidates_created += 1

        required_passes = 0
        required_total = 0
        critical_failures: list[str] = []
        warning_failures: list[str] = []

        for rule in rules:
            passed, message, observed_numeric, observed_text = evaluate_rule(
                rule,
                ranking,
            )
            required = bool(rule.get("required"))
            severity = str(rule.get("severity") or "CRITICAL")

            if required:
                required_total += 1
                if passed:
                    required_passes += 1

            if not passed:
                rule_failures += 1
                if severity == "CRITICAL":
                    critical_failures.append(str(rule.get("rule_key")))
                else:
                    warning_failures.append(str(rule.get("rule_key")))

            rule_evaluations += 1
            client.upsert(
                "candidate_evaluations_v57",
                {
                    "candidate_id": candidate_id,
                    "evaluation_date": RUN_DATE,
                    "evaluation_key": str(rule.get("rule_key")),
                    "rule_key": str(rule.get("rule_key")),
                    "observed_numeric_value": observed_numeric,
                    "observed_text_value": observed_text,
                    "threshold_numeric_value": rule.get("numeric_threshold"),
                    "threshold_text_value": rule.get("text_threshold"),
                    "evaluation_status": "PASS" if passed else "FAIL",
                    "passed": passed,
                    "severity": severity,
                    "message": message,
                    "evidence": {
                        "ranking_id": ranking_id,
                        "source_version_no": source_version_no,
                    },
                },
                "candidate_id,evaluation_date,evaluation_key",
            )

        eligibility_score = (
            required_passes / required_total * 100
            if required_total
            else 0
        )
        eligibility_scores.append(eligibility_score)

        if critical_failures:
            candidate_status = "REJECTED"
            eligibility_status = "NOT_ELIGIBLE"
            rejection_reason = ",".join(critical_failures)
            candidates_rejected += 1
        elif warning_failures:
            candidate_status = "RETEST_REQUIRED"
            eligibility_status = "NEEDS_MORE_EVIDENCE"
            rejection_reason = ",".join(warning_failures)
            candidates_retest_required += 1
        else:
            candidate_status = "READY_FOR_REVIEW"
            eligibility_status = "ELIGIBLE"
            rejection_reason = None
            candidates_eligible += 1

        client.patch(
            "promotion_candidates_v57",
            f"id=eq.{candidate_id}",
            {
                "candidate_status": candidate_status,
                "eligibility_status": eligibility_status,
                "eligibility_score": eligibility_score,
                "rejection_reason": rejection_reason,
            },
        )

        client.upsert(
            "promotion_audit_v57",
            {
                "audit_time": now(),
                "audit_date": RUN_DATE,
                "candidate_id": candidate_id,
                "review_request_id": None,
                "promotion_plan_id": None,
                "event_type": "CANDIDATE_EVALUATED",
                "event_status": (
                    "PASS"
                    if eligibility_status == "ELIGIBLE"
                    else "WARNING"
                    if eligibility_status == "NEEDS_MORE_EVIDENCE"
                    else "FAIL"
                ),
                "actor": "ENTERPRISE57_BASELINE_PROMOTION",
                "message": (
                    f"{source_version_no} evaluated as {eligibility_status}."
                ),
                "previous_state": {},
                "new_state": {
                    "candidate_status": candidate_status,
                    "eligibility_status": eligibility_status,
                    "eligibility_score": eligibility_score,
                },
                "metadata": {
                    "run_id": run_id,
                    "critical_failures": critical_failures,
                    "warning_failures": warning_failures,
                },
            },
            None,
        )

        if eligibility_status != "ELIGIBLE":
            continue

        request_key = f"HUMAN_REVIEW:{source_version_no}"
        client.upsert(
            "human_review_requests_v57",
            {
                "candidate_id": candidate_id,
                "request_date": RUN_DATE,
                "request_key": request_key,
                "request_status": "PENDING",
                "review_priority": "HIGH" if rank_no == 1 else "MEDIUM",
                "requested_by": "ENTERPRISE57_BASELINE_PROMOTION",
                "requested_at": now(),
                "due_at": None,
                "review_summary": (
                    f"Review {source_version_no} for Paper Baseline promotion. "
                    f"Evolution score={evolution_score:.2f}, "
                    f"confidence={confidence_score:.2f}."
                ),
                "human_approval_required": True,
                "automatic_approval_enabled": False,
                "evidence": {
                    "ranking_id": ranking_id,
                    "eligibility_score": eligibility_score,
                },
            },
            "request_date,request_key",
        )

        review = read(
            client,
            "human_review_requests_v57",
            (
                f"request_date=eq.{RUN_DATE}"
                f"&request_key=eq.{request_key}"
                "&limit=1"
            ),
            required=True,
        )[0]
        review_id = str(review["id"])
        current_review_request_id = review_id
        human_reviews_created += 1
        human_reviews_pending += 1

        client.upsert(
            "human_review_decisions_v57",
            {
                "review_request_id": review_id,
                "decision_date": RUN_DATE,
                "decision_key": "PRIMARY_DECISION",
                "decision": "PENDING",
                "decided_by": None,
                "decided_at": None,
                "decision_comment": (
                    "Awaiting explicit human approval."
                ),
                "approval_scope": "PAPER_BASELINE_ONLY",
                "automatic_execution_enabled": False,
                "evidence": {
                    "candidate_id": candidate_id,
                },
            },
            "review_request_id,decision_key",
        )

        proposed_baseline_version = (
            f"5.7-candidate-baseline-{source_version_no.replace('.', '-')}"
        )

        client.upsert(
            "baseline_versions_v57",
            {
                "version_date": RUN_DATE,
                "version_no": proposed_baseline_version,
                "source_candidate_id": candidate_id,
                "source_version_no": source_version_no,
                "baseline_status": "CANDIDATE_BASELINE",
                "portfolio_snapshot": version.get("allocation_snapshot") or {},
                "strategy_snapshot": version.get("strategy_snapshot") or {},
                "agent_weight_snapshot": version.get("agent_weight_snapshot") or {},
                "risk_snapshot": version.get("risk_snapshot") or {},
                "active": False,
                "paper_only": True,
                "human_approval_required": True,
                "automatic_activation_enabled": False,
                "live_trading_enabled": False,
                "description": (
                    f"Candidate Paper Baseline derived from {source_version_no}."
                ),
                "metadata": {
                    "run_id": run_id,
                    "review_request_id": review_id,
                },
            },
            "version_date,version_no",
        )
        baselines_registered += 1

        baseline_candidate = read(
            client,
            "baseline_versions_v57",
            (
                f"version_date=eq.{RUN_DATE}"
                f"&version_no=eq.{proposed_baseline_version}"
                "&limit=1"
            ),
            required=True,
        )[0]
        baseline_candidate_id = str(baseline_candidate["id"])

        plan_key = f"PROMOTION_PLAN:{source_version_no}"
        client.upsert(
            "baseline_promotion_plans_v57",
            {
                "candidate_id": candidate_id,
                "review_request_id": review_id,
                "target_baseline_version_id": baseline_candidate_id,
                "plan_date": RUN_DATE,
                "plan_key": plan_key,
                "plan_status": "WAITING_FOR_APPROVAL",
                "current_baseline_version": current_baseline_version,
                "proposed_baseline_version": proposed_baseline_version,
                "activation_mode": "MANUAL",
                "rollback_target_version": current_baseline_version,
                "rollback_ready": True,
                "human_approval_required": True,
                "automatic_activation_enabled": False,
                "automatic_rollback_enabled": False,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
                "implementation_steps": [
                    "Human approval",
                    "Manual baseline activation",
                    "Paper verification",
                    "Manual rollback if required",
                ],
                "validation_steps": [
                    "Verify candidate snapshot",
                    "Verify approval record",
                    "Verify live trading remains disabled",
                ],
            },
            "plan_date,plan_key",
        )

        plan = read(
            client,
            "baseline_promotion_plans_v57",
            (
                f"plan_date=eq.{RUN_DATE}"
                f"&plan_key=eq.{plan_key}"
                "&limit=1"
            ),
            required=True,
        )[0]
        plan_id = str(plan["id"])
        current_promotion_plan_id = plan_id
        promotion_plans_created += 1

        client.patch(
            "promotion_candidates_v57",
            f"id=eq.{candidate_id}",
            {"candidate_status": "PROMOTION_PLANNED"},
        )

        client.upsert(
            "baseline_history_v57",
            {
                "event_date": RUN_DATE,
                "event_time": now(),
                "event_key": f"PROMOTION_PLANNED:{source_version_no}",
                "baseline_version_id": baseline_candidate_id,
                "previous_baseline_version": current_baseline_version,
                "new_baseline_version": proposed_baseline_version,
                "event_type": "PROMOTION_PLANNED",
                "event_status": "PENDING",
                "actor": "ENTERPRISE57_BASELINE_PROMOTION",
                "reason": "Candidate passed all promotion rules.",
                "human_approval_reference": review_id,
                "automatic_execution_enabled": False,
                "evidence": {
                    "candidate_id": candidate_id,
                    "plan_id": plan_id,
                },
            },
            "event_date,event_key",
        )

        if rank_no == 1:
            current_top_candidate_version = source_version_no

    if candidates_eligible > 0:
        overall_status = "READY_FOR_HUMAN_REVIEW"
    elif candidates_created > 0:
        overall_status = "NO_ELIGIBLE_CANDIDATE"
        warnings.append("NO_ELIGIBLE_CANDIDATE")
    else:
        overall_status = "CRITICAL"

    summary = (
        f"Enterprise 5.7 read {rankings_read} ranking(s), "
        f"created {candidates_created} candidate(s), "
        f"found {candidates_eligible} eligible candidate(s), "
        f"created {human_reviews_created} human review request(s), "
        f"and created {promotion_plans_created} promotion plan(s)."
    )

    client.upsert(
        "promotion_metrics_v57",
        {
            "metric_date": RUN_DATE,
            "rankings_read": rankings_read,
            "candidates_created": candidates_created,
            "candidates_eligible": candidates_eligible,
            "candidates_rejected": candidates_rejected,
            "candidates_retest_required": candidates_retest_required,
            "rule_evaluations": rule_evaluations,
            "rule_failures": rule_failures,
            "human_reviews_created": human_reviews_created,
            "human_reviews_pending": human_reviews_pending,
            "human_reviews_approved": human_reviews_approved,
            "promotion_plans_created": promotion_plans_created,
            "baselines_registered": baselines_registered,
            "automatic_promotions": 0,
            "automatic_rollbacks": 0,
            "average_eligibility_score": (
                mean(eligibility_scores) if eligibility_scores else 0
            ),
            "diagnostics": {
                "run_id": run_id,
                "engine_version": ENGINE_VERSION,
            },
        },
        "metric_date",
    )

    client.upsert(
        "promotion_status_v57",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_baseline_version": current_baseline_version,
            "current_top_candidate_version": current_top_candidate_version,
            "current_review_request_id": current_review_request_id,
            "current_promotion_plan_id": current_promotion_plan_id,
            "rankings_read": rankings_read,
            "candidates_created": candidates_created,
            "candidates_eligible": candidates_eligible,
            "candidates_rejected": candidates_rejected,
            "candidates_retest_required": candidates_retest_required,
            "rule_evaluations": rule_evaluations,
            "rule_failures": rule_failures,
            "human_reviews_created": human_reviews_created,
            "human_reviews_pending": human_reviews_pending,
            "human_reviews_approved": human_reviews_approved,
            "promotion_plans_created": promotion_plans_created,
            "baselines_registered": baselines_registered,
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
            },
        },
        "status_date",
    )

    if rankings and candidates_created == 0:
        raise RuntimeError(
            "v56 rankings exist but v57 created zero promotion candidates."
        )

    print(summary)
    print(f"Enterprise 5.7 status: {overall_status}")


if __name__ == "__main__":
    main()
