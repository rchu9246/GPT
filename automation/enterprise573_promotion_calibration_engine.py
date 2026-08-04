from __future__ import annotations

import argparse
import math
import os
import uuid
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.7.3.1"

STRICT_THRESHOLDS = {
    "minimum_evolution_score": 70.0,
    "minimum_confidence_score": 60.0,
    "minimum_rule_pass_rate": 100.0,
}

PAPER_SAFETY_FLOORS = {
    "minimum_evolution_score": 60.0,
    "minimum_confidence_score": 30.0,
    "minimum_rule_pass_rate": 60.0,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {
        "true", "t", "1", "yes", "y", "pass", "passed"
    }


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


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * p
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    fraction = index - lower
    return ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * fraction


def evaluation_passed(row: dict[str, Any]) -> bool:
    if row.get("passed") is not None:
        return boolean(row.get("passed"))
    return str(row.get("evaluation_status") or "").upper() == "PASS"


def group_evaluations(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            grouped.setdefault(candidate_id, []).append(row)
    return grouped


def calculate_candidate_pass_rate(
    evaluations: list[dict[str, Any]],
) -> float:
    applicable = [
        row for row in evaluations
        if str(row.get("evaluation_status") or "").upper()
        != "NOT_APPLICABLE"
    ]
    if not applicable:
        return 0.0
    passed = sum(
        1 for row in applicable if evaluation_passed(row)
    )
    return passed / len(applicable) * 100.0


def calculate_calibration(
    candidates: list[dict[str, Any]],
    evaluations_by_candidate: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    ranked = sorted(
        candidates,
        key=lambda row: int(row.get("rank_no") or 999),
    )

    evolution_scores = [
        num(row.get("evolution_score"))
        for row in ranked
        if row.get("evolution_score") is not None
    ]
    confidence_scores = [
        num(row.get("confidence_score"))
        for row in ranked
        if row.get("confidence_score") is not None
    ]

    pass_rates = [
        calculate_candidate_pass_rate(
            evaluations_by_candidate.get(str(row["id"]), [])
        )
        for row in ranked
    ]

    top_candidate = ranked[0] if ranked else {}
    top_evolution = num(top_candidate.get("evolution_score"))
    top_confidence = num(top_candidate.get("confidence_score"))
    top_pass_rate = (
        calculate_candidate_pass_rate(
            evaluations_by_candidate.get(
                str(top_candidate.get("id") or ""),
                [],
            )
        )
        if top_candidate
        else 0.0
    )

    proposed_evolution = max(
        PAPER_SAFETY_FLOORS["minimum_evolution_score"],
        min(
            STRICT_THRESHOLDS["minimum_evolution_score"],
            round(percentile(evolution_scores, 0.75), 2),
        ),
    )

    proposed_confidence = max(
        PAPER_SAFETY_FLOORS["minimum_confidence_score"],
        min(
            STRICT_THRESHOLDS["minimum_confidence_score"],
            round(percentile(confidence_scores, 0.75), 2),
        ),
    )

    proposed_pass_rate = max(
        PAPER_SAFETY_FLOORS["minimum_rule_pass_rate"],
        min(
            STRICT_THRESHOLDS["minimum_rule_pass_rate"],
            round(percentile(pass_rates, 0.75), 2),
        ),
    )

    # A paper calibration may not exceed the top candidate,
    # otherwise it can never produce a review candidate.
    proposed_evolution = min(
        proposed_evolution,
        max(
            PAPER_SAFETY_FLOORS["minimum_evolution_score"],
            round(top_evolution, 2),
        ),
    )
    proposed_confidence = min(
        proposed_confidence,
        max(
            PAPER_SAFETY_FLOORS["minimum_confidence_score"],
            round(top_confidence, 2),
        ),
    )
    proposed_pass_rate = min(
        proposed_pass_rate,
        max(
            PAPER_SAFETY_FLOORS["minimum_rule_pass_rate"],
            round(top_pass_rate, 2),
        ),
    )

    reviewable = (
        top_evolution >= proposed_evolution
        and top_confidence >= proposed_confidence
        and top_pass_rate >= proposed_pass_rate
        and int(top_candidate.get("rank_no") or 999) == 1
    )

    return {
        "strict_thresholds": STRICT_THRESHOLDS,
        "paper_safety_floors": PAPER_SAFETY_FLOORS,
        "proposed_thresholds": {
            "minimum_evolution_score": proposed_evolution,
            "minimum_confidence_score": proposed_confidence,
            "minimum_rule_pass_rate": proposed_pass_rate,
        },
        "top_candidate": {
            "id": top_candidate.get("id"),
            "source_version_no": top_candidate.get("source_version_no"),
            "rank_no": top_candidate.get("rank_no"),
            "evolution_score": top_evolution,
            "confidence_score": top_confidence,
            "rule_pass_rate": top_pass_rate,
        },
        "population": {
            "candidate_count": len(ranked),
            "average_evolution_score": (
                round(mean(evolution_scores), 4)
                if evolution_scores
                else 0.0
            ),
            "average_confidence_score": (
                round(mean(confidence_scores), 4)
                if confidence_scores
                else 0.0
            ),
            "average_rule_pass_rate": (
                round(mean(pass_rates), 4)
                if pass_rates
                else 0.0
            ),
        },
        "paper_reviewable": reviewable,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise 5.7.3 Promotion Calibration Engine"
    )
    parser.add_argument(
        "--mode",
        choices=["ANALYZE_ONLY", "APPLY_PAPER_PILOT"],
        default="ANALYZE_ONLY",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
    )
    args = parser.parse_args()

    client = SupabaseRestClient()

    candidates = read(
        client,
        "promotion_candidates_v57",
        f"order=candidate_date.desc,rank_no.asc&limit={args.limit}",
        required=True,
    )
    if not candidates:
        raise RuntimeError("No promotion_candidates_v57 rows found.")

    evaluation_rows = read(
        client,
        "candidate_evaluations_v57",
        "limit=5000",
        required=True,
    )
    evaluations_by_candidate = group_evaluations(evaluation_rows)

    calibration = calculate_calibration(
        candidates,
        evaluations_by_candidate,
    )

    calibration_id = deterministic_id(
        "enterprise573",
        RUN_DATE,
        args.mode,
    )

    audit_message = (
        f"Promotion calibration analyzed {len(candidates)} candidate(s). "
        f"Mode={args.mode}. "
        f"Proposed paper thresholds="
        f"{calibration['proposed_thresholds']}."
    )

    client.upsert(
        "promotion_audit_v57",
        {
            "id": calibration_id,
            "audit_time": now(),
            "audit_date": RUN_DATE,
            "candidate_id": calibration["top_candidate"]["id"],
            "review_request_id": None,
            "promotion_plan_id": None,
            "event_type": "PROMOTION_CALIBRATION",
            "event_status": (
                "PASS"
                if calibration["paper_reviewable"]
                else "WARNING"
            ),
            "actor": "ENTERPRISE573_PROMOTION_CALIBRATION",
            "message": audit_message,
            "previous_state": {
                "strict_thresholds": STRICT_THRESHOLDS,
            },
            "new_state": {
                "mode": args.mode,
                "proposed_thresholds": (
                    calibration["proposed_thresholds"]
                ),
            },
            "metadata": {
                "engine_version": ENGINE_VERSION,
                "calibration": calibration,
                "paper_only": True,
                "automatic_baseline_activation": False,
                "live_trading_enabled": False,
            },
        },
        "id",
    )

    status_rows = read(
        client,
        "promotion_status_v57",
        f"status_date=eq.{RUN_DATE}&limit=1",
    )
    if status_rows:
        status = status_rows[0]
        client.patch(
            "promotion_status_v57",
            f"status_date=eq.{RUN_DATE}",
            {
                # Preserve the existing database-approved status value.
                # promotion_status_v57 may have a CHECK constraint and does
                # not necessarily allow CALIBRATION_READY/CALIBRATION_WARNING.
                "overall_status": status.get("overall_status") or "WARNING",
                "human_approval_required": True,
                "automatic_baseline_promotion_enabled": False,
                "automatic_portfolio_application_enabled": False,
                "automatic_live_deployment_enabled": False,
                "automatic_rollback_execution_enabled": False,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
                "warnings": (
                    []
                    if calibration["paper_reviewable"]
                    else ["NO_REVIEWABLE_CANDIDATE_AFTER_CALIBRATION"]
                ),
                "summary": audit_message,
                "diagnostics": {
                    **(status.get("diagnostics") or {}),
                    "calibration_engine_version": ENGINE_VERSION,
                    "calibration_mode": args.mode,
                    "calibration": calibration,
                    "calibrated_at": now(),
                },
            },
        )

    if args.mode == "APPLY_PAPER_PILOT":
        top_candidate = calibration["top_candidate"]
        if not calibration["paper_reviewable"]:
            raise RuntimeError(
                "Paper pilot calibration cannot be applied because "
                "the top candidate is still below safety floors."
            )

        candidate_id = str(top_candidate["id"])
        proposed = calibration["proposed_thresholds"]

        candidate_rows = read(
            client,
            "promotion_candidates_v57",
            f"id=eq.{candidate_id}&limit=1",
            required=True,
        )
        candidate = candidate_rows[0]

        client.patch(
            "promotion_candidates_v57",
            f"id=eq.{candidate_id}",
            {
                "candidate_status": "READY_FOR_REVIEW",
                "eligibility_status": "ELIGIBLE",
                "eligibility_score": top_candidate["rule_pass_rate"],
                "rejection_reason": None,
                "metadata": {
                    **(candidate.get("metadata") or {}),
                    "calibration_engine_version": ENGINE_VERSION,
                    "calibration_mode": "PAPER_PILOT",
                    "calibrated_thresholds": proposed,
                    "paper_only": True,
                },
            },
        )

        request_key = (
            f"CALIBRATED_PAPER_REVIEW:"
            f"{top_candidate['source_version_no']}"
        )

        client.upsert(
            "human_review_requests_v57",
            {
                "candidate_id": candidate_id,
                "request_date": RUN_DATE,
                "request_key": request_key,
                "request_status": "PENDING",
                "review_priority": "HIGH",
                "requested_by": "ENTERPRISE573_PROMOTION_CALIBRATION",
                "requested_at": now(),
                "due_at": None,
                "review_summary": (
                    "Candidate admitted to paper-only human review "
                    "under calibrated thresholds. "
                    f"Thresholds={proposed}."
                ),
                "human_approval_required": True,
                "automatic_approval_enabled": False,
                "evidence": {
                    "engine_version": ENGINE_VERSION,
                    "calibration": calibration,
                    "paper_only": True,
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
                "decision_comment": (
                    "Awaiting explicit human approval for paper pilot."
                ),
                "approval_scope": "PAPER_BASELINE_ONLY",
                "automatic_execution_enabled": False,
                "evidence": {
                    "candidate_id": candidate_id,
                    "calibrated_thresholds": proposed,
                },
            },
            "review_request_id,decision_key",
        )

        print(
            "Paper-pilot calibration applied to top candidate:",
            top_candidate["source_version_no"],
        )

    print(
        "Enterprise 5.7.3 complete:",
        f"mode={args.mode}",
        f"paper_reviewable={calibration['paper_reviewable']}",
        f"thresholds={calibration['proposed_thresholds']}",
    )
    print("Human approval required: true")
    print("Automatic baseline activation: false")
    print("Live trading: false")


if __name__ == "__main__":
    main()
