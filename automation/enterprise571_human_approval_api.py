from __future__ import annotations

import argparse
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from enterprise2.client import SupabaseRestClient

ENGINE_VERSION = "5.7.1"
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

VALID_DECISIONS = {"APPROVED", "REJECTED", "RETEST_REQUIRED"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def get_candidate(
    client: SupabaseRestClient,
    candidate_id: str,
) -> dict[str, Any]:
    rows = read(
        client,
        "promotion_candidates_v57",
        f"id=eq.{candidate_id}&limit=1",
        required=True,
    )
    if not rows:
        raise ValueError(f"Candidate not found: {candidate_id}")
    return rows[0]


def get_review_request(
    client: SupabaseRestClient,
    candidate_id: str,
) -> dict[str, Any]:
    rows = read(
        client,
        "human_review_requests_v57",
        (
            f"candidate_id=eq.{candidate_id}"
            "&order=requested_at.desc"
            "&limit=1"
        ),
        required=True,
    )
    if not rows:
        raise ValueError(
            f"No Human Review Request exists for Candidate {candidate_id}"
        )
    return rows[0]


def get_plan(
    client: SupabaseRestClient,
    candidate_id: str,
) -> dict[str, Any]:
    rows = read(
        client,
        "baseline_promotion_plans_v57",
        (
            f"candidate_id=eq.{candidate_id}"
            "&order=created_at.desc"
            "&limit=1"
        ),
    )
    return rows[0] if rows else {}


def get_status(client: SupabaseRestClient) -> dict[str, Any]:
    rows = read(
        client,
        "promotion_status_v57",
        "order=status_date.desc&limit=1",
    )
    return rows[0] if rows else {}


def get_metrics(client: SupabaseRestClient) -> dict[str, Any]:
    rows = read(
        client,
        "promotion_metrics_v57",
        "order=metric_date.desc&limit=1",
    )
    return rows[0] if rows else {}


def audit_id(candidate_id: str, decision: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"enterprise571:{RUN_DATE}:{candidate_id}:{decision}",
        )
    )


def decision_effects(decision: str) -> dict[str, str]:
    if decision == "APPROVED":
        return {
            "candidate_status": "APPROVED",
            "eligibility_status": "ELIGIBLE",
            "request_status": "APPROVED",
            "plan_status": "READY_FOR_MANUAL_ACTIVATION",
            "history_type": "APPROVED",
            "history_status": "COMPLETED",
            "overall_status": "PASS",
        }
    if decision == "REJECTED":
        return {
            "candidate_status": "REJECTED",
            "eligibility_status": "NOT_ELIGIBLE",
            "request_status": "REJECTED",
            "plan_status": "REJECTED",
            "history_type": "REJECTED",
            "history_status": "COMPLETED",
            "overall_status": "WARNING",
        }
    return {
        "candidate_status": "RETEST_REQUIRED",
        "eligibility_status": "NEEDS_MORE_EVIDENCE",
        "request_status": "RETEST_REQUIRED",
        "plan_status": "PAUSED",
        "history_type": "RETEST_REQUIRED",
        "history_status": "PENDING",
        "overall_status": "WARNING",
    }


def process_decision(
    *,
    candidate_id: str,
    decision: str,
    reviewer: str,
    comment: str,
) -> None:
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Unsupported decision {decision}. "
            f"Expected one of {sorted(VALID_DECISIONS)}"
        )
    if not reviewer.strip():
        raise ValueError("Reviewer is required.")
    if not comment.strip():
        raise ValueError("Decision comment is required.")

    client = SupabaseRestClient()
    candidate = get_candidate(client, candidate_id)
    review = get_review_request(client, candidate_id)
    plan = get_plan(client, candidate_id)
    status = get_status(client)
    metrics = get_metrics(client)

    review_id = str(review["id"])
    effects = decision_effects(decision)
    decision_time = now()

    client.patch(
        "human_review_requests_v57",
        f"id=eq.{review_id}",
        {
            "request_status": effects["request_status"],
            "updated_at": decision_time,
        },
    )

    client.upsert(
        "human_review_decisions_v57",
        {
            "review_request_id": review_id,
            "decision_date": RUN_DATE,
            "decision_key": "PRIMARY_DECISION",
            "decision": decision,
            "decided_by": reviewer,
            "decided_at": decision_time,
            "decision_comment": comment,
            "approval_scope": "PAPER_BASELINE_ONLY",
            "automatic_execution_enabled": False,
            "evidence": {
                "candidate_id": candidate_id,
                "engine_version": ENGINE_VERSION,
                "paper_only": True,
            },
        },
        "review_request_id,decision_key",
    )

    client.patch(
        "promotion_candidates_v57",
        f"id=eq.{candidate_id}",
        {
            "candidate_status": effects["candidate_status"],
            "eligibility_status": effects["eligibility_status"],
            "updated_at": decision_time,
        },
    )

    plan_id = None
    if plan:
        plan_id = str(plan["id"])
        client.patch(
            "baseline_promotion_plans_v57",
            f"id=eq.{plan_id}",
            {
                "plan_status": effects["plan_status"],
                "automatic_activation_enabled": False,
                "automatic_rollback_enabled": False,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
                "updated_at": decision_time,
            },
        )

    target_baseline_version_id = (
        plan.get("target_baseline_version_id") if plan else None
    )
    if decision == "APPROVED" and target_baseline_version_id:
        client.patch(
            "baseline_versions_v57",
            f"id=eq.{target_baseline_version_id}",
            {
                "baseline_status": "APPROVED_FOR_MANUAL_ACTIVATION",
                "active": False,
                "automatic_activation_enabled": False,
                "live_trading_enabled": False,
                "updated_at": decision_time,
            },
        )

    source_version_no = str(candidate.get("source_version_no") or candidate_id)
    history_key = f"{decision}:{source_version_no}"
    client.upsert(
        "baseline_history_v57",
        {
            "event_date": RUN_DATE,
            "event_time": decision_time,
            "event_key": history_key,
            "baseline_version_id": target_baseline_version_id,
            "previous_baseline_version": (
                plan.get("current_baseline_version") if plan else None
            ),
            "new_baseline_version": (
                plan.get("proposed_baseline_version") if plan else None
            ),
            "event_type": effects["history_type"],
            "event_status": effects["history_status"],
            "actor": reviewer,
            "reason": comment,
            "human_approval_reference": review_id,
            "automatic_execution_enabled": False,
            "evidence": {
                "candidate_id": candidate_id,
                "review_request_id": review_id,
                "decision": decision,
            },
        },
        "event_date,event_key",
    )

    client.upsert(
        "promotion_audit_v57",
        {
            "id": audit_id(candidate_id, decision),
            "audit_time": decision_time,
            "audit_date": RUN_DATE,
            "candidate_id": candidate_id,
            "review_request_id": review_id,
            "promotion_plan_id": plan_id,
            "event_type": "HUMAN_REVIEW_DECISION",
            "event_status": "PASS",
            "actor": reviewer,
            "message": f"Human review decision: {decision}. {comment}",
            "previous_state": {
                "candidate_status": candidate.get("candidate_status"),
                "request_status": review.get("request_status"),
                "plan_status": plan.get("plan_status") if plan else None,
            },
            "new_state": {
                "candidate_status": effects["candidate_status"],
                "request_status": effects["request_status"],
                "plan_status": effects["plan_status"],
                "decision": decision,
            },
            "metadata": {
                "engine_version": ENGINE_VERSION,
                "automatic_execution_enabled": False,
                "live_trading_enabled": False,
            },
        },
        "id",
    )

    pending_reviews = int(metrics.get("human_reviews_pending") or 0)
    approved_reviews = int(metrics.get("human_reviews_approved") or 0)

    if decision == "APPROVED":
        pending_reviews = max(0, pending_reviews - 1)
        approved_reviews += 1
    elif decision in {"REJECTED", "RETEST_REQUIRED"}:
        pending_reviews = max(0, pending_reviews - 1)

    client.upsert(
        "promotion_metrics_v57",
        {
            "metric_date": RUN_DATE,
            "rankings_read": int(metrics.get("rankings_read") or 0),
            "candidates_created": int(metrics.get("candidates_created") or 0),
            "candidates_eligible": int(metrics.get("candidates_eligible") or 0),
            "candidates_rejected": (
                int(metrics.get("candidates_rejected") or 0)
                + (1 if decision == "REJECTED" else 0)
            ),
            "candidates_retest_required": (
                int(metrics.get("candidates_retest_required") or 0)
                + (1 if decision == "RETEST_REQUIRED" else 0)
            ),
            "rule_evaluations": int(metrics.get("rule_evaluations") or 0),
            "rule_failures": int(metrics.get("rule_failures") or 0),
            "human_reviews_created": int(
                metrics.get("human_reviews_created") or 0
            ),
            "human_reviews_pending": pending_reviews,
            "human_reviews_approved": approved_reviews,
            "promotion_plans_created": int(
                metrics.get("promotion_plans_created") or 0
            ),
            "baselines_registered": int(
                metrics.get("baselines_registered") or 1
            ),
            "automatic_promotions": 0,
            "automatic_rollbacks": 0,
            "average_eligibility_score": float(
                metrics.get("average_eligibility_score") or 0
            ),
            "diagnostics": {
                "engine_version": ENGINE_VERSION,
                "last_human_decision": decision,
                "last_candidate_id": candidate_id,
                "last_reviewer": reviewer,
            },
        },
        "metric_date",
    )

    summary = (
        f"Human reviewer {reviewer} marked Candidate "
        f"{source_version_no} as {decision}. "
        "No automatic baseline activation was performed."
    )

    client.upsert(
        "promotion_status_v57",
        {
            "status_date": RUN_DATE,
            "overall_status": effects["overall_status"],
            "current_baseline_version": status.get(
                "current_baseline_version",
                "5.7-baseline-0001",
            ),
            "current_top_candidate_version": source_version_no,
            "current_review_request_id": review_id,
            "current_promotion_plan_id": plan_id,
            "rankings_read": int(status.get("rankings_read") or 0),
            "candidates_created": int(status.get("candidates_created") or 0),
            "candidates_eligible": int(status.get("candidates_eligible") or 0),
            "candidates_rejected": (
                int(status.get("candidates_rejected") or 0)
                + (1 if decision == "REJECTED" else 0)
            ),
            "candidates_retest_required": (
                int(status.get("candidates_retest_required") or 0)
                + (1 if decision == "RETEST_REQUIRED" else 0)
            ),
            "rule_evaluations": int(status.get("rule_evaluations") or 0),
            "rule_failures": int(status.get("rule_failures") or 0),
            "human_reviews_created": int(
                status.get("human_reviews_created") or 0
            ),
            "human_reviews_pending": pending_reviews,
            "human_reviews_approved": approved_reviews,
            "promotion_plans_created": int(
                status.get("promotion_plans_created") or 0
            ),
            "baselines_registered": int(
                status.get("baselines_registered") or 1
            ),
            "human_approval_required": True,
            "automatic_baseline_promotion_enabled": False,
            "automatic_portfolio_application_enabled": False,
            "automatic_live_deployment_enabled": False,
            "automatic_rollback_execution_enabled": False,
            "live_trading_enabled": False,
            "broker_submission_enabled": False,
            "blockers": [],
            "warnings": (
                []
                if decision == "APPROVED"
                else [f"HUMAN_DECISION_{decision}"]
            ),
            "summary": summary,
            "diagnostics": {
                "engine_version": ENGINE_VERSION,
                "decision": decision,
                "candidate_id": candidate_id,
                "reviewer": reviewer,
                "manual_activation_required": decision == "APPROVED",
            },
        },
        "status_date",
    )

    print(summary)
    print("Automatic baseline activation: false")
    print("Live trading: false")
    print("Broker submission: false")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enterprise 5.7.1 Human Approval API"
    )
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument(
        "--decision",
        required=True,
        choices=sorted(VALID_DECISIONS),
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--comment", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    process_decision(
        candidate_id=args.candidate_id,
        decision=args.decision,
        reviewer=args.reviewer,
        comment=args.comment,
    )


if __name__ == "__main__":
    main()
