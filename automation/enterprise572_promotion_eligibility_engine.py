from __future__ import annotations

import argparse
import os
import uuid
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.7.2.1"

POLICIES: dict[str, dict[str, Any]] = {
    "STRICT": {
        "minimum_pass_rate": 100.0,
        "require_rank_one": True,
        "require_selected_for_review": True,
        "require_promotion_recommendation": True,
        "allow_critical_failures": False,
    },
    "PAPER_PILOT": {
        "minimum_pass_rate": 60.0,
        "require_rank_one": True,
        "require_selected_for_review": False,
        "require_promotion_recommendation": False,
        "allow_critical_failures": True,
    },
}


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


def boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0

    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "1", "yes", "y", "pass", "passed"}:
        return True
    if normalized in {"false", "f", "0", "no", "n", "fail", "failed", ""}:
        return False
    return False


def evaluation_passed(row: dict[str, Any]) -> bool:
    raw_passed = row.get("passed")
    if raw_passed is not None:
        return boolean(raw_passed)

    status = str(row.get("evaluation_status") or "").strip().upper()
    return status == "PASS"


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
    except Exception:
        if required:
            raise
        return []


def deterministic_id(*parts: Any) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join(str(part) for part in parts),
        )
    )


def get_current_baseline(client: SupabaseRestClient) -> dict[str, Any]:
    rows = read(
        client,
        "baseline_versions_v57",
        (
            "active=eq.true"
            "&baseline_status=eq.CURRENT_BASELINE"
            "&order=created_at.desc"
            "&limit=1"
        ),
    )
    return rows[0] if rows else {}


def get_version_snapshot(
    client: SupabaseRestClient,
    source_version_no: str,
) -> dict[str, Any]:
    rows = read(
        client,
        "portfolio_versions_v56",
        f"version_no=eq.{source_version_no}&limit=1",
    )
    return rows[0] if rows else {}


def load_all_evaluations(
    client: SupabaseRestClient,
) -> dict[str, list[dict[str, Any]]]:
    rows = read(
        client,
        "candidate_evaluations_v57",
        "limit=5000",
        required=True,
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id:
            continue
        grouped.setdefault(candidate_id, []).append(row)

    return grouped


def fallback_evaluations_from_candidate(
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    rank_no = integer(candidate.get("rank_no"), 999)
    evolution_score = num(candidate.get("evolution_score"))
    confidence_score = num(candidate.get("confidence_score"))
    recommendation = str(candidate.get("source_recommendation") or "")
    selected = boolean(candidate.get("source_selected_for_review"))

    return [
        {
            "rule_key": "TOP_RANK_ONLY",
            "evaluation_status": "PASS" if rank_no == 1 else "FAIL",
            "passed": rank_no == 1,
            "severity": "CRITICAL",
        },
        {
            "rule_key": "MIN_EVOLUTION_SCORE",
            "evaluation_status": "PASS" if evolution_score >= 70 else "FAIL",
            "passed": evolution_score >= 70,
            "severity": "CRITICAL",
        },
        {
            "rule_key": "MIN_CONFIDENCE_SCORE",
            "evaluation_status": "PASS" if confidence_score >= 60 else "FAIL",
            "passed": confidence_score >= 60,
            "severity": "CRITICAL",
        },
        {
            "rule_key": "PROMOTION_RECOMMENDATION_REQUIRED",
            "evaluation_status": (
                "PASS"
                if recommendation == "PROMOTE_FOR_HUMAN_REVIEW"
                else "FAIL"
            ),
            "passed": recommendation == "PROMOTE_FOR_HUMAN_REVIEW",
            "severity": "CRITICAL",
        },
        {
            "rule_key": "SELECTED_FOR_REVIEW_REQUIRED",
            "evaluation_status": "PASS" if selected else "FAIL",
            "passed": selected,
            "severity": "CRITICAL",
        },
    ]


def calculate_eligibility(
    candidate: dict[str, Any],
    evaluations: list[dict[str, Any]],
    policy_name: str,
) -> dict[str, Any]:
    policy = POLICIES[policy_name]

    if not evaluations:
        evaluations = fallback_evaluations_from_candidate(candidate)

    required_rows = [
        row for row in evaluations
        if str(row.get("evaluation_status")) != "NOT_APPLICABLE"
    ]
    passed_rows = [row for row in required_rows if evaluation_passed(row)]
    failed_rows = [row for row in required_rows if not evaluation_passed(row)]
    critical_failures = [
        str(row.get("rule_key"))
        for row in failed_rows
        if str(row.get("severity")) == "CRITICAL"
    ]

    pass_rate = (
        len(passed_rows) / len(required_rows) * 100
        if required_rows
        else 0.0
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if policy["require_rank_one"] and integer(candidate.get("rank_no")) != 1:
        blockers.append("TOP_RANK_REQUIRED")

    if (
        policy["require_selected_for_review"]
        and not bool(candidate.get("source_selected_for_review"))
    ):
        blockers.append("SELECTED_FOR_REVIEW_REQUIRED")

    if (
        policy["require_promotion_recommendation"]
        and str(candidate.get("source_recommendation"))
        != "PROMOTE_FOR_HUMAN_REVIEW"
    ):
        blockers.append("PROMOTION_RECOMMENDATION_REQUIRED")

    if pass_rate < num(policy["minimum_pass_rate"]):
        blockers.append("MINIMUM_RULE_PASS_RATE_NOT_MET")

    if critical_failures and not policy["allow_critical_failures"]:
        blockers.extend(
            f"CRITICAL_RULE_FAILED:{rule_key}"
            for rule_key in critical_failures
        )
    elif critical_failures:
        warnings.extend(
            f"PAPER_PILOT_OVERRIDE:{rule_key}"
            for rule_key in critical_failures
        )

    eligible = not blockers

    if eligible:
        eligibility_status = "ELIGIBLE"
        candidate_status = "READY_FOR_REVIEW"
    elif pass_rate >= 50:
        eligibility_status = "NEEDS_MORE_EVIDENCE"
        candidate_status = "RETEST_REQUIRED"
    else:
        eligibility_status = "NOT_ELIGIBLE"
        candidate_status = "REJECTED"

    return {
        "eligible": eligible,
        "eligibility_status": eligibility_status,
        "candidate_status": candidate_status,
        "eligibility_score": pass_rate,
        "blockers": blockers,
        "warnings": warnings,
        "critical_failures": critical_failures,
        "passed_rules": len(passed_rows),
        "total_rules": len(required_rows),
    }


def ensure_review_and_plan(
    client: SupabaseRestClient,
    candidate: dict[str, Any],
    policy_name: str,
    result: dict[str, Any],
    current_baseline: dict[str, Any],
) -> tuple[str, str]:
    candidate_id = str(candidate["id"])
    source_version_no = str(candidate["source_version_no"])
    current_baseline_no = str(
        current_baseline.get("version_no") or "5.7-baseline-0001"
    )

    request_key = f"ELIGIBILITY_REVIEW:{policy_name}:{source_version_no}"
    client.upsert(
        "human_review_requests_v57",
        {
            "candidate_id": candidate_id,
            "request_date": RUN_DATE,
            "request_key": request_key,
            "request_status": "PENDING",
            "review_priority": "HIGH",
            "requested_by": "ENTERPRISE572_PROMOTION_ELIGIBILITY",
            "requested_at": now(),
            "due_at": None,
            "review_summary": (
                f"{source_version_no} qualified under {policy_name}. "
                f"Rule pass rate={result['eligibility_score']:.2f}%. "
                "Explicit human approval is required."
            ),
            "human_approval_required": True,
            "automatic_approval_enabled": False,
            "evidence": {
                "policy_name": policy_name,
                "eligibility_score": result["eligibility_score"],
                "blockers": result["blockers"],
                "warnings": result["warnings"],
            },
        },
        "request_date,request_key",
    )

    review_rows = read(
        client,
        "human_review_requests_v57",
        (
            f"request_date=eq.{RUN_DATE}"
            f"&request_key=eq.{request_key}"
            "&limit=1"
        ),
        required=True,
    )
    review_id = str(review_rows[0]["id"])

    client.upsert(
        "human_review_decisions_v57",
        {
            "review_request_id": review_id,
            "decision_date": RUN_DATE,
            "decision_key": "PRIMARY_DECISION",
            "decision": "PENDING",
            "decided_by": None,
            "decided_at": None,
            "decision_comment": "Awaiting explicit human approval.",
            "approval_scope": "PAPER_BASELINE_ONLY",
            "automatic_execution_enabled": False,
            "evidence": {
                "candidate_id": candidate_id,
                "policy_name": policy_name,
            },
        },
        "review_request_id,decision_key",
    )

    version_snapshot = get_version_snapshot(client, source_version_no)
    proposed_baseline_no = (
        f"5.7-paper-pilot-{source_version_no.replace('.', '-')}"
        if policy_name == "PAPER_PILOT"
        else f"5.7-candidate-baseline-{source_version_no.replace('.', '-')}"
    )

    client.upsert(
        "baseline_versions_v57",
        {
            "version_date": RUN_DATE,
            "version_no": proposed_baseline_no,
            "source_candidate_id": candidate_id,
            "source_version_no": source_version_no,
            "baseline_status": "CANDIDATE_BASELINE",
            "portfolio_snapshot": (
                version_snapshot.get("allocation_snapshot") or {}
            ),
            "strategy_snapshot": (
                version_snapshot.get("strategy_snapshot") or {}
            ),
            "agent_weight_snapshot": (
                version_snapshot.get("agent_weight_snapshot") or {}
            ),
            "risk_snapshot": (
                version_snapshot.get("risk_snapshot") or {}
            ),
            "active": False,
            "paper_only": True,
            "human_approval_required": True,
            "automatic_activation_enabled": False,
            "live_trading_enabled": False,
            "description": (
                f"Paper-only candidate baseline created under {policy_name}."
            ),
            "metadata": {
                "engine_version": ENGINE_VERSION,
                "policy_name": policy_name,
                "review_request_id": review_id,
            },
        },
        "version_date,version_no",
    )

    baseline_rows = read(
        client,
        "baseline_versions_v57",
        (
            f"version_date=eq.{RUN_DATE}"
            f"&version_no=eq.{proposed_baseline_no}"
            "&limit=1"
        ),
        required=True,
    )
    baseline_id = str(baseline_rows[0]["id"])

    plan_key = f"ELIGIBILITY_PLAN:{policy_name}:{source_version_no}"
    client.upsert(
        "baseline_promotion_plans_v57",
        {
            "candidate_id": candidate_id,
            "review_request_id": review_id,
            "target_baseline_version_id": baseline_id,
            "plan_date": RUN_DATE,
            "plan_key": plan_key,
            "plan_status": "WAITING_FOR_APPROVAL",
            "current_baseline_version": current_baseline_no,
            "proposed_baseline_version": proposed_baseline_no,
            "activation_mode": "MANUAL",
            "rollback_target_version": current_baseline_no,
            "rollback_ready": True,
            "human_approval_required": True,
            "automatic_activation_enabled": False,
            "automatic_rollback_enabled": False,
            "live_trading_enabled": False,
            "broker_submission_enabled": False,
            "implementation_steps": [
                "Explicit human approval",
                "Manual paper-baseline activation",
                "Paper verification",
            ],
            "validation_steps": [
                "Verify review decision",
                "Verify active baseline uniqueness",
                "Verify live trading remains disabled",
            ],
        },
        "plan_date,plan_key",
    )

    plan_rows = read(
        client,
        "baseline_promotion_plans_v57",
        (
            f"plan_date=eq.{RUN_DATE}"
            f"&plan_key=eq.{plan_key}"
            "&limit=1"
        ),
        required=True,
    )
    plan_id = str(plan_rows[0]["id"])

    client.upsert(
        "baseline_history_v57",
        {
            "event_date": RUN_DATE,
            "event_time": now(),
            "event_key": f"ELIGIBILITY_PLAN:{policy_name}:{source_version_no}",
            "baseline_version_id": baseline_id,
            "previous_baseline_version": current_baseline_no,
            "new_baseline_version": proposed_baseline_no,
            "event_type": "PROMOTION_PLANNED",
            "event_status": "PENDING",
            "actor": "ENTERPRISE572_PROMOTION_ELIGIBILITY",
            "reason": (
                f"Candidate passed {policy_name} eligibility policy."
            ),
            "human_approval_reference": review_id,
            "automatic_execution_enabled": False,
            "evidence": {
                "candidate_id": candidate_id,
                "policy_name": policy_name,
                "eligibility_score": result["eligibility_score"],
            },
        },
        "event_date,event_key",
    )

    return review_id, plan_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise 5.7.2 Promotion Eligibility Engine"
    )
    parser.add_argument(
        "--policy",
        choices=sorted(POLICIES),
        default="STRICT",
    )
    parser.add_argument(
        "--candidate-id",
        default="",
        help="Optional single Candidate UUID. Empty means evaluate all candidates.",
    )
    args = parser.parse_args()

    client = SupabaseRestClient()
    current_baseline = get_current_baseline(client)

    query = (
        f"id=eq.{args.candidate_id}&limit=1"
        if args.candidate_id
        else "order=candidate_date.desc,rank_no.asc&limit=100"
    )
    candidates = read(
        client,
        "promotion_candidates_v57",
        query,
        required=True,
    )

    if not candidates:
        raise RuntimeError("No promotion_candidates_v57 rows found.")

    evaluations_by_candidate = load_all_evaluations(client)

    evaluated = 0
    eligible_count = 0
    rejected_count = 0
    retest_count = 0
    review_count = 0
    plan_count = 0
    scores: list[float] = []
    latest_review_id = None
    latest_plan_id = None
    top_candidate_version = None
    all_blockers: list[str] = []
    all_warnings: list[str] = []

    for candidate in candidates:
        candidate_id = str(candidate["id"])
        evaluations = evaluations_by_candidate.get(candidate_id, [])
        result = calculate_eligibility(
            candidate,
            evaluations,
            args.policy,
        )
        evaluated += 1
        scores.append(result["eligibility_score"])
        all_blockers.extend(result["blockers"])
        all_warnings.extend(result["warnings"])

        rejection_reason = (
            ",".join(result["blockers"])
            if result["blockers"]
            else None
        )

        client.patch(
            "promotion_candidates_v57",
            f"id=eq.{candidate_id}",
            {
                "candidate_status": result["candidate_status"],
                "eligibility_status": result["eligibility_status"],
                "eligibility_score": result["eligibility_score"],
                "rejection_reason": rejection_reason,
                "metadata": {
                    **(candidate.get("metadata") or {}),
                    "eligibility_engine_version": ENGINE_VERSION,
                    "eligibility_policy": args.policy,
                    "eligibility_blockers": result["blockers"],
                    "eligibility_warnings": result["warnings"],
                },
            },
        )

        client.upsert(
            "promotion_audit_v57",
            {
                "id": deterministic_id(
                    "enterprise572",
                    RUN_DATE,
                    candidate_id,
                    args.policy,
                ),
                "audit_time": now(),
                "audit_date": RUN_DATE,
                "candidate_id": candidate_id,
                "review_request_id": None,
                "promotion_plan_id": None,
                "event_type": "ELIGIBILITY_REEVALUATED",
                "event_status": (
                    "PASS" if result["eligible"] else "WARNING"
                ),
                "actor": "ENTERPRISE572_PROMOTION_ELIGIBILITY",
                "message": (
                    f"Eligibility policy {args.policy}: "
                    f"{result['eligibility_status']} "
                    f"({result['eligibility_score']:.2f}%)."
                ),
                "previous_state": {
                    "eligibility_status": candidate.get(
                        "eligibility_status"
                    ),
                    "candidate_status": candidate.get("candidate_status"),
                },
                "new_state": {
                    "eligibility_status": result["eligibility_status"],
                    "candidate_status": result["candidate_status"],
                    "eligibility_score": result["eligibility_score"],
                },
                "metadata": {
                    "policy_name": args.policy,
                    "passed_rules": result["passed_rules"],
                    "total_rules": result["total_rules"],
                    "eligibility_score": result["eligibility_score"],
                    "evaluation_rows_loaded": len(evaluations),
                    "used_fallback_evaluation": len(evaluations) == 0,
                    "blockers": result["blockers"],
                    "warnings": result["warnings"],
                },
            },
            "id",
        )

        if result["eligibility_status"] == "NOT_ELIGIBLE":
            rejected_count += 1
        elif result["eligibility_status"] == "NEEDS_MORE_EVIDENCE":
            retest_count += 1

        if not result["eligible"]:
            continue

        eligible_count += 1
        if integer(candidate.get("rank_no")) == 1:
            top_candidate_version = candidate.get("source_version_no")

        review_id, plan_id = ensure_review_and_plan(
            client,
            candidate,
            args.policy,
            result,
            current_baseline,
        )
        latest_review_id = review_id
        latest_plan_id = plan_id
        review_count += 1
        plan_count += 1

    existing_metrics_rows = read(
        client,
        "promotion_metrics_v57",
        f"metric_date=eq.{RUN_DATE}&limit=1",
    )
    existing_metrics = (
        existing_metrics_rows[0] if existing_metrics_rows else {}
    )

    client.upsert(
        "promotion_metrics_v57",
        {
            "metric_date": RUN_DATE,
            "rankings_read": int(
                existing_metrics.get("rankings_read") or 0
            ),
            "candidates_created": int(
                existing_metrics.get("candidates_created") or len(candidates)
            ),
            "candidates_eligible": eligible_count,
            "candidates_rejected": rejected_count,
            "candidates_retest_required": retest_count,
            "rule_evaluations": int(
                existing_metrics.get("rule_evaluations") or 0
            ),
            "rule_failures": int(
                existing_metrics.get("rule_failures") or 0
            ),
            "human_reviews_created": review_count,
            "human_reviews_pending": review_count,
            "human_reviews_approved": int(
                existing_metrics.get("human_reviews_approved") or 0
            ),
            "promotion_plans_created": plan_count,
            "baselines_registered": int(
                existing_metrics.get("baselines_registered") or 1
            ) + plan_count,
            "automatic_promotions": 0,
            "automatic_rollbacks": 0,
            "average_eligibility_score": (
                mean(scores) if scores else 0
            ),
            "diagnostics": {
                "engine_version": ENGINE_VERSION,
                "policy_name": args.policy,
                "candidates_evaluated": evaluated,
            },
        },
        "metric_date",
    )

    overall_status = (
        "READY_FOR_HUMAN_REVIEW"
        if eligible_count > 0
        else "NO_ELIGIBLE_CANDIDATE"
    )

    client.upsert(
        "promotion_status_v57",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_baseline_version": (
                current_baseline.get("version_no")
                or "5.7-baseline-0001"
            ),
            "current_top_candidate_version": top_candidate_version,
            "current_review_request_id": latest_review_id,
            "current_promotion_plan_id": latest_plan_id,
            "rankings_read": int(
                existing_metrics.get("rankings_read") or 0
            ),
            "candidates_created": int(
                existing_metrics.get("candidates_created") or len(candidates)
            ),
            "candidates_eligible": eligible_count,
            "candidates_rejected": rejected_count,
            "candidates_retest_required": retest_count,
            "rule_evaluations": int(
                existing_metrics.get("rule_evaluations") or 0
            ),
            "rule_failures": int(
                existing_metrics.get("rule_failures") or 0
            ),
            "human_reviews_created": review_count,
            "human_reviews_pending": review_count,
            "human_reviews_approved": int(
                existing_metrics.get("human_reviews_approved") or 0
            ),
            "promotion_plans_created": plan_count,
            "baselines_registered": int(
                existing_metrics.get("baselines_registered") or 1
            ) + plan_count,
            "human_approval_required": True,
            "automatic_baseline_promotion_enabled": False,
            "automatic_portfolio_application_enabled": False,
            "automatic_live_deployment_enabled": False,
            "automatic_rollback_execution_enabled": False,
            "live_trading_enabled": False,
            "broker_submission_enabled": False,
            "blockers": sorted(set(all_blockers)),
            "warnings": sorted(set(all_warnings)),
            "summary": (
                f"Enterprise 5.7.2 evaluated {evaluated} candidate(s) "
                f"under {args.policy}; {eligible_count} eligible, "
                f"{review_count} review request(s), "
                f"{plan_count} promotion plan(s)."
            ),
            "diagnostics": {
                "engine_version": ENGINE_VERSION,
                "policy_name": args.policy,
                "paper_only": True,
            },
        },
        "status_date",
    )

    any_pass_rows = any(
        evaluation_passed(row)
        for rows in evaluations_by_candidate.values()
        for row in rows
    )
    if any_pass_rows and scores and max(scores) <= 0:
        raise RuntimeError(
            "Evaluation rows contain PASS results but every eligibility score is 0."
        )

    if eligible_count > 0 and (review_count == 0 or plan_count == 0):
        raise RuntimeError(
            "Eligible candidates exist but review or promotion plan was not created."
        )

    print(
        f"Enterprise 5.7.2 complete: policy={args.policy}, "
        f"evaluated={evaluated}, eligible={eligible_count}, "
        f"reviews={review_count}, plans={plan_count}"
    )
    print("Automatic promotion: false")
    print("Live trading: false")
    print("Broker submission: false")


if __name__ == "__main__":
    main()
