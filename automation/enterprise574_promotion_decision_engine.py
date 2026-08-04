from __future__ import annotations

import argparse
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.7.4"

VALID_OUTPUTS = {"PROMOTE", "HOLD", "REJECT"}


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


def deterministic_id(*parts: Any) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join(str(part) for part in parts),
        )
    )


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


def get_latest_review(
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
    )
    return rows[0] if rows else {}


def get_latest_decision(
    client: SupabaseRestClient,
    review_id: str | None,
) -> dict[str, Any]:
    if not review_id:
        return {}
    rows = read(
        client,
        "human_review_decisions_v57",
        (
            f"review_request_id=eq.{review_id}"
            "&decision_key=eq.PRIMARY_DECISION"
            "&limit=1"
        ),
    )
    return rows[0] if rows else {}


def get_latest_plan(
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


def get_latest_calibration(
    client: SupabaseRestClient,
    candidate_id: str,
) -> dict[str, Any]:
    rows = read(
        client,
        "promotion_audit_v57",
        (
            "event_type=eq.PROMOTION_CALIBRATION"
            f"&candidate_id=eq.{candidate_id}"
            "&order=audit_time.desc"
            "&limit=1"
        ),
    )
    return rows[0] if rows else {}


def get_latest_status(
    client: SupabaseRestClient,
) -> dict[str, Any]:
    rows = read(
        client,
        "promotion_status_v57",
        "order=status_date.desc&limit=1",
    )
    return rows[0] if rows else {}


def decide(
    *,
    candidate: dict[str, Any],
    review: dict[str, Any],
    human_decision: dict[str, Any],
    plan: dict[str, Any],
    calibration: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    eligibility_status = str(candidate.get("eligibility_status") or "")
    candidate_status = str(candidate.get("candidate_status") or "")
    review_status = str(review.get("request_status") or "")
    decision_value = str(human_decision.get("decision") or "")
    plan_status = str(plan.get("plan_status") or "")

    if eligibility_status != "ELIGIBLE":
        blockers.append("CANDIDATE_NOT_ELIGIBLE")

    if not review:
        blockers.append("HUMAN_REVIEW_REQUEST_MISSING")
    elif review_status == "PENDING":
        warnings.append("HUMAN_REVIEW_PENDING")
    elif review_status == "REJECTED":
        blockers.append("HUMAN_REVIEW_REJECTED")
    elif review_status == "RETEST_REQUIRED":
        blockers.append("HUMAN_REVIEW_RETEST_REQUIRED")

    if not human_decision:
        warnings.append("HUMAN_DECISION_MISSING")
    elif decision_value == "PENDING":
        warnings.append("HUMAN_DECISION_PENDING")
    elif decision_value == "REJECTED":
        blockers.append("HUMAN_DECISION_REJECTED")
    elif decision_value == "RETEST_REQUIRED":
        blockers.append("HUMAN_DECISION_RETEST_REQUIRED")

    if not plan:
        blockers.append("PROMOTION_PLAN_MISSING")
    elif plan_status not in {
        "READY_FOR_MANUAL_ACTIVATION",
        "WAITING_FOR_APPROVAL",
    }:
        blockers.append(f"PROMOTION_PLAN_NOT_READY:{plan_status or 'UNKNOWN'}")

    if plan:
        if plan.get("automatic_activation_enabled") is not False:
            blockers.append("AUTOMATIC_ACTIVATION_NOT_DISABLED")
        if plan.get("live_trading_enabled") is not False:
            blockers.append("LIVE_TRADING_NOT_DISABLED")
        if plan.get("broker_submission_enabled") is not False:
            blockers.append("BROKER_SUBMISSION_NOT_DISABLED")

    calibration_metadata = calibration.get("metadata") or {}
    if calibration:
        calibration_payload = calibration_metadata.get("calibration") or {}
        if not calibration_payload.get("paper_reviewable", False):
            warnings.append("CALIBRATION_NOT_PAPER_REVIEWABLE")
    else:
        warnings.append("CALIBRATION_AUDIT_MISSING")

    if blockers:
        return "REJECT", blockers, warnings

    if (
        decision_value == "APPROVED"
        and review_status == "APPROVED"
        and plan_status == "READY_FOR_MANUAL_ACTIVATION"
        and candidate_status in {"APPROVED", "READY_FOR_REVIEW"}
    ):
        return "PROMOTE", blockers, warnings

    return "HOLD", blockers, warnings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise 5.7.4 Promotion Decision Engine"
    )
    parser.add_argument("--candidate-id", required=True)
    args = parser.parse_args()

    client = SupabaseRestClient()

    candidate = get_candidate(client, args.candidate_id)
    review = get_latest_review(client, args.candidate_id)
    review_id = str(review.get("id")) if review else None
    human_decision = get_latest_decision(client, review_id)
    plan = get_latest_plan(client, args.candidate_id)
    calibration = get_latest_calibration(client, args.candidate_id)
    status = get_latest_status(client)

    final_decision, blockers, warnings = decide(
        candidate=candidate,
        review=review,
        human_decision=human_decision,
        plan=plan,
        calibration=calibration,
    )

    if final_decision not in VALID_OUTPUTS:
        raise RuntimeError(f"Invalid final decision: {final_decision}")

    decision_time = now()
    decision_id = deterministic_id(
        "enterprise574",
        RUN_DATE,
        args.candidate_id,
        final_decision,
    )

    source_version_no = str(
        candidate.get("source_version_no") or args.candidate_id
    )

    client.upsert(
        "promotion_audit_v57",
        {
            "id": decision_id,
            "audit_time": decision_time,
            "audit_date": RUN_DATE,
            "candidate_id": args.candidate_id,
            "review_request_id": review_id,
            "promotion_plan_id": plan.get("id") if plan else None,
            "event_type": "FINAL_PROMOTION_DECISION",
            "event_status": (
                "PASS" if final_decision == "PROMOTE"
                else "WARNING" if final_decision == "HOLD"
                else "FAIL"
            ),
            "actor": "ENTERPRISE574_PROMOTION_DECISION",
            "message": (
                f"Final promotion decision for {source_version_no}: "
                f"{final_decision}."
            ),
            "previous_state": {
                "candidate_status": candidate.get("candidate_status"),
                "eligibility_status": candidate.get("eligibility_status"),
                "review_status": review.get("request_status") if review else None,
                "human_decision": (
                    human_decision.get("decision")
                    if human_decision
                    else None
                ),
                "plan_status": plan.get("plan_status") if plan else None,
            },
            "new_state": {
                "final_decision": final_decision,
                "blockers": blockers,
                "warnings": warnings,
            },
            "metadata": {
                "engine_version": ENGINE_VERSION,
                "paper_only": True,
                "human_approval_required": True,
                "automatic_activation_enabled": False,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
            },
        },
        "id",
    )

    next_candidate_status = {
        "PROMOTE": "APPROVED_FOR_MANUAL_ACTIVATION",
        "HOLD": "HOLD",
        "REJECT": "REJECTED",
    }[final_decision]

    client.patch(
        "promotion_candidates_v57",
        f"id=eq.{args.candidate_id}",
        {
            "candidate_status": next_candidate_status,
            "updated_at": decision_time,
            "metadata": {
                **(candidate.get("metadata") or {}),
                "final_decision_engine_version": ENGINE_VERSION,
                "final_decision": final_decision,
                "final_decision_time": decision_time,
                "final_decision_blockers": blockers,
                "final_decision_warnings": warnings,
            },
        },
    )

    if plan:
        next_plan_status = {
            "PROMOTE": "READY_FOR_MANUAL_ACTIVATION",
            "HOLD": "ON_HOLD",
            "REJECT": "REJECTED",
        }[final_decision]

        client.patch(
            "baseline_promotion_plans_v57",
            f"id=eq.{plan['id']}",
            {
                "plan_status": next_plan_status,
                "automatic_activation_enabled": False,
                "automatic_rollback_enabled": False,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
                "updated_at": decision_time,
            },
        )

    if status:
        # Preserve database-approved overall_status to avoid CHECK violations.
        client.patch(
            "promotion_status_v57",
            f"status_date=eq.{status['status_date']}",
            {
                "overall_status": status.get("overall_status") or "WARNING",
                "current_top_candidate_version": source_version_no,
                "current_review_request_id": review_id,
                "current_promotion_plan_id": plan.get("id") if plan else None,
                "human_approval_required": True,
                "automatic_baseline_promotion_enabled": False,
                "automatic_portfolio_application_enabled": False,
                "automatic_live_deployment_enabled": False,
                "automatic_rollback_execution_enabled": False,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
                "blockers": blockers,
                "warnings": warnings,
                "summary": (
                    f"Enterprise 5.7.4 final decision: {final_decision} "
                    f"for {source_version_no}."
                ),
                "diagnostics": {
                    **(status.get("diagnostics") or {}),
                    "decision_engine_version": ENGINE_VERSION,
                    "candidate_id": args.candidate_id,
                    "source_version_no": source_version_no,
                    "final_decision": final_decision,
                    "blockers": blockers,
                    "warnings": warnings,
                    "decided_at": decision_time,
                },
            },
        )

    print(
        f"Enterprise 5.7.4 complete: candidate={source_version_no}, "
        f"decision={final_decision}"
    )
    print(f"Blockers: {blockers}")
    print(f"Warnings: {warnings}")
    print("Automatic baseline activation: false")
    print("Live trading: false")
    print("Broker submission: false")


if __name__ == "__main__":
    main()
