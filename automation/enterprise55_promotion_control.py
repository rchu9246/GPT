from __future__ import annotations

import math
import os
import uuid
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "5.5.2"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
    field: str,
    where: str = "",
) -> dict[str, Any]:
    query = (
        f"{where}&order={field}.desc&limit=1"
        if where
        else f"order={field}.desc&limit=1"
    )
    rows = read(client, table, query)
    return rows[0] if rows else {}


def readiness_score(
    evidence_count: int,
    safety_pass: bool,
    shadow_pass: bool,
    stability_score: float,
    risk_regression_score: float,
    rollback_ready: bool,
) -> float:
    score = 0.0
    score += min(25.0, evidence_count * 2.5)
    score += 20.0 if safety_pass else 5.0
    score += 20.0 if shadow_pass else 5.0
    score += clamp(stability_score, 0, 100) * 0.20
    score += max(
        0.0,
        15.0 - clamp(risk_regression_score, 0, 100) * 0.15,
    )
    score += 5.0 if rollback_ready else 0.0
    return clamp(score, 0, 100)


def readiness_status(
    score: float,
    safety_pass: bool,
    shadow_pass: bool,
    rollback_ready: bool,
    evidence_count: int,
    minimum_evidence: int,
    minimum_readiness: float,
) -> str:
    if not rollback_ready:
        return "BLOCKED"
    if evidence_count < minimum_evidence:
        return "NEEDS_MORE_EVIDENCE"
    if safety_pass and shadow_pass and score >= minimum_readiness:
        return "READY_FOR_PAPER_CANARY"
    if score >= minimum_readiness - 15:
        return "NEEDS_MORE_EVIDENCE"
    return "BLOCKED"


def regression_status(
    score_delta: float,
    calibration_delta: float,
    risk_failure_delta: int,
    stability_delta: float,
) -> tuple[str, bool]:
    critical = (
        score_delta < -10
        or calibration_delta > 15
        or risk_failure_delta > 0
        or stability_delta < -15
    )
    warning = (
        score_delta < -5
        or calibration_delta > 8
        or stability_delta < -8
    )
    if critical:
        return "ROLLBACK_RECOMMENDED", False
    if warning:
        return "WARNING", False
    return "NO_REGRESSION", True


def candidate_sources(
    client: SupabaseRestClient,
) -> list[dict[str, Any]]:
    """
    Primary source:
      parameter_versions_v54 with version_status=CANDIDATE.

    Fallback source:
      adaptive_proposals_v54. This guarantees Enterprise 5.5 can create
      Promotion Requests even when Enterprise 5.4 generated proposals and
      shadow tests but no candidate parameter version.
    """
    versions = read(
        client,
        "parameter_versions_v54",
        (
            "version_status=eq.CANDIDATE"
            "&active=eq.false"
            "&automatic_application_enabled=eq.false"
            "&order=created_at.desc"
            "&limit=100"
        ),
    )

    result: list[dict[str, Any]] = []
    for version in versions:
        proposal_ids = version.get("source_proposals") or []
        if not isinstance(proposal_ids, list):
            proposal_ids = []
        result.append(
            {
                "source_mode": "VERSION",
                "candidate_version_id": version.get("id"),
                "candidate_version_no": version.get("version_no"),
                "rollback_ready": bool(version.get("rollback_ready")),
                "proposal_ids": proposal_ids,
                "configuration": version.get("configuration") or {},
            }
        )

    if result:
        return result

    proposals = read(
        client,
        "adaptive_proposals_v54",
        (
            "paper_only=eq.true"
            "&automatic_application_enabled=eq.false"
            "&order=proposal_date.desc,created_at.desc"
            "&limit=100"
        ),
        required=True,
    )

    for proposal in proposals:
        proposal_id = str(proposal["id"])
        synthetic_version = (
            f"5.5-assessment-{RUN_DATE.replace('-', '')}-"
            f"{proposal_id[:8]}"
        )
        result.append(
            {
                "source_mode": "PROPOSAL_FALLBACK",
                "candidate_version_id": None,
                "candidate_version_no": synthetic_version,
                "rollback_ready": True,
                "proposal_ids": [proposal_id],
                "configuration": {
                    "source_proposal_key": proposal.get("proposal_key"),
                    "source_proposal_status": proposal.get("status"),
                },
            }
        )

    return result


def load_source_proposals(
    client: SupabaseRestClient,
    proposal_ids: list[str],
) -> list[dict[str, Any]]:
    proposals = []
    for proposal_id in proposal_ids:
        rows = read(
            client,
            "adaptive_proposals_v54",
            f"id=eq.{proposal_id}&limit=1",
        )
        if rows:
            proposals.append(rows[0])
    return proposals


def main() -> None:
    client = SupabaseRestClient()
    run_id = str(uuid.uuid4())

    minimum_evidence = int(
        num(os.getenv("ENTERPRISE55_MIN_EVIDENCE_COUNT"), 1)
    )
    minimum_readiness = num(
        os.getenv("ENTERPRISE55_MIN_READINESS_SCORE"), 55
    )
    paper_traffic_pct = num(
        os.getenv("ENTERPRISE55_PAPER_TRAFFIC_PCT"), 10
    )
    paper_duration_cycles = int(
        num(os.getenv("ENTERPRISE55_PAPER_DURATION_CYCLES"), 5)
    )

    sources = candidate_sources(client)

    baseline = latest(
        client,
        "parameter_versions_v54",
        "created_at",
        "version_status=eq.ACTIVE&active=eq.true",
    )
    governance_status = latest(
        client,
        "adaptive_status_v54",
        "status_date",
    )

    baseline_version_no = str(
        baseline.get("version_no") or "5.4-baseline-0001"
    )

    blockers: list[str] = []
    warnings: list[str] = []

    requests_created = 0
    readiness_checks = 0
    approvals_pending = 0
    plans_created = 0
    canary_cycles_created = 0
    comparisons_completed = 0
    regression_events_created = 0
    rollback_recommendations_created = 0
    confirmed_for_manual_promotion = 0
    readiness_scores: list[float] = []

    current_request_id = None
    current_candidate_version = None

    if not sources:
        blockers.append("NO_V54_PROPOSALS_OR_CANDIDATES")

    for source in sources:
        version_id = source.get("candidate_version_id")
        version_no = str(source["candidate_version_no"])
        current_candidate_version = version_no
        proposal_ids = [
            str(value)
            for value in source.get("proposal_ids", [])
            if value
        ]
        source_proposals = load_source_proposals(client, proposal_ids)

        shadow_rows: list[dict[str, Any]] = []
        safety_rows: list[dict[str, Any]] = []
        for proposal in source_proposals:
            pid = str(proposal["id"])
            shadow_rows.extend(
                read(
                    client,
                    "shadow_simulations_v54",
                    (
                        f"proposal_id=eq.{pid}"
                        "&order=created_at.desc"
                        "&limit=1"
                    ),
                )
            )
            safety_rows.extend(
                read(
                    client,
                    "safety_gate_results_v54",
                    f"proposal_id=eq.{pid}&limit=100",
                )
            )

        evidence_count = sum(
            integer(p.get("evidence_count"), 0)
            for p in source_proposals
        )
        if evidence_count == 0:
            evidence_count = max(1, len(source_proposals))

        proposal_safety_flags = [
            bool(p.get("safety_gate_passed"))
            for p in source_proposals
            if p.get("safety_gate_passed") is not None
        ]
        proposal_shadow_flags = [
            bool(p.get("shadow_test_passed"))
            for p in source_proposals
            if p.get("shadow_test_passed") is not None
        ]

        gate_passes = [
            bool(row.get("passed"))
            for row in safety_rows
        ]
        shadow_passes = [
            bool(row.get("passed"))
            for row in shadow_rows
        ]

        safety_pass = (
            all(proposal_safety_flags)
            if proposal_safety_flags
            else all(gate_passes)
            if gate_passes
            else False
        )
        shadow_pass = (
            all(proposal_shadow_flags)
            if proposal_shadow_flags
            else all(shadow_passes)
            if shadow_passes
            else False
        )

        rollback_ready = bool(source.get("rollback_ready", True))

        stability_values = [
            num(row.get("stability_score"))
            for row in shadow_rows
        ]
        risk_values = [
            num(row.get("risk_regression_score"))
            for row in shadow_rows
        ]
        stability = mean(stability_values) if stability_values else 50.0
        risk_regression = mean(risk_values) if risk_values else 50.0

        score = readiness_score(
            evidence_count,
            safety_pass,
            shadow_pass,
            stability,
            risk_regression,
            rollback_ready,
        )
        status = readiness_status(
            score,
            safety_pass,
            shadow_pass,
            rollback_ready,
            evidence_count,
            minimum_evidence,
            minimum_readiness,
        )

        request_key = f"PROMOTION:{version_no}"
        request_status = (
            "READY_FOR_REVIEW"
            if status == "READY_FOR_PAPER_CANARY"
            else "DRAFT"
        )

        client.upsert(
            "promotion_requests_v55",
            {
                "request_date": RUN_DATE,
                "request_key": request_key,
                "candidate_version_id": version_id,
                "candidate_version_no": version_no,
                "baseline_version_id": baseline.get("id"),
                "baseline_version_no": baseline_version_no,
                "source_proposal_ids": proposal_ids,
                "request_status": request_status,
                "readiness_status": status,
                "request_reason": (
                    "Enterprise 5.5 Promotion assessment from "
                    f"{source['source_mode']}."
                ),
                "evidence_count": evidence_count,
                "readiness_score": score,
                "rollback_ready": rollback_ready,
                "human_approval_required": True,
                "paper_only": True,
                "automatic_production_promotion_enabled": False,
                "live_trading_enabled": False,
                "metadata": {
                    "run_id": run_id,
                    "engine_version": ENGINE_VERSION,
                    "source_mode": source["source_mode"],
                    "governance_status": governance_status.get(
                        "overall_status"
                    ),
                    "safety_rows": len(safety_rows),
                    "shadow_rows": len(shadow_rows),
                },
            },
            "request_date,request_key",
        )

        request = read(
            client,
            "promotion_requests_v55",
            (
                f"request_date=eq.{RUN_DATE}"
                f"&request_key=eq.{request_key}"
                "&limit=1"
            ),
            required=True,
        )[0]
        request_id = str(request["id"])
        current_request_id = request_id
        requests_created += 1
        readiness_checks += 1
        readiness_scores.append(score)

        approval_status = (
            "PENDING"
            if status == "READY_FOR_PAPER_CANARY"
            else "NEEDS_MORE_EVIDENCE"
        )
        client.upsert(
            "promotion_approvals_v55",
            {
                "request_id": request_id,
                "approval_stage": "HUMAN_APPROVAL",
                "approval_status": approval_status,
                "approver": None,
                "approval_comment": (
                    "Human approval required before Paper Canary activation."
                ),
                "approved_at": None,
                "human_approval_required": True,
                "automatic_approval_enabled": False,
                "evidence": {
                    "readiness_score": score,
                    "readiness_status": status,
                    "source_mode": source["source_mode"],
                },
            },
            "request_id,approval_stage",
        )
        if approval_status == "PENDING":
            approvals_pending += 1

        plan_key = f"CANARY:{version_no}"
        plan_status = (
            "DRAFT"
            if status == "READY_FOR_PAPER_CANARY"
            else "PAUSED"
        )
        client.upsert(
            "paper_canary_plans_v55",
            {
                "request_id": request_id,
                "plan_date": RUN_DATE,
                "plan_key": plan_key,
                "candidate_version_no": version_no,
                "baseline_version_no": baseline_version_no,
                "traffic_pct": paper_traffic_pct,
                "duration_cycles": paper_duration_cycles,
                "canary_mode": "PAPER",
                "plan_status": plan_status,
                "start_after_approval": True,
                "automatic_start_enabled": False,
                "live_trading_enabled": False,
                "broker_submission_enabled": False,
                "configuration": {
                    "readiness_score": score,
                    "minimum_readiness_score": minimum_readiness,
                    "source_mode": source["source_mode"],
                },
            },
            "plan_date,plan_key",
        )
        plan = read(
            client,
            "paper_canary_plans_v55",
            (
                f"plan_date=eq.{RUN_DATE}"
                f"&plan_key=eq.{plan_key}"
                "&limit=1"
            ),
            required=True,
        )[0]
        plan_id = str(plan["id"])
        plans_created += 1

        baseline_score = clamp(
            num(governance_status.get("ready_for_review"), 0) * 10,
            0,
            100,
        )
        if baseline_score == 0:
            baseline_score = 50.0

        candidate_score = score
        baseline_calibration = 25.0
        candidate_calibration = clamp(100 - stability, 0, 100)
        baseline_risk_failures = integer(
            governance_status.get("rejected_proposals"), 0
        )
        candidate_risk_failures = 0 if safety_pass else 1
        baseline_stability = 50.0
        candidate_stability = stability

        client.upsert(
            "paper_canary_cycles_v55",
            {
                "plan_id": plan_id,
                "cycle_no": 1,
                "cycle_date": RUN_DATE,
                "cycle_status": (
                    "PASS"
                    if status == "READY_FOR_PAPER_CANARY"
                    else "WARNING"
                ),
                "baseline_decision_score": baseline_score,
                "candidate_decision_score": candidate_score,
                "baseline_calibration_error": baseline_calibration,
                "candidate_calibration_error": candidate_calibration,
                "baseline_risk_failures": baseline_risk_failures,
                "candidate_risk_failures": candidate_risk_failures,
                "baseline_stability_score": baseline_stability,
                "candidate_stability_score": candidate_stability,
                "candidate_wins": candidate_score > baseline_score,
                "notes": (
                    "Initial Paper Canary proxy cycle. "
                    "No live execution and no automatic promotion."
                ),
                "diagnostics": {
                    "run_id": run_id,
                    "proxy_only": True,
                    "source_mode": source["source_mode"],
                },
            },
            "plan_id,cycle_no",
        )
        canary_cycles_created += 1

        score_delta = candidate_score - baseline_score
        calibration_delta = (
            candidate_calibration - baseline_calibration
        )
        risk_failure_delta = (
            candidate_risk_failures - baseline_risk_failures
        )
        stability_delta = (
            candidate_stability - baseline_stability
        )

        reg_status, comparison_pass = regression_status(
            score_delta,
            calibration_delta,
            risk_failure_delta,
            stability_delta,
        )
        comparison_status = (
            "PASS"
            if comparison_pass
            else "FAIL"
            if reg_status == "ROLLBACK_RECOMMENDED"
            else "WARNING"
        )

        comparison_key = f"COMPARE:{version_no}"
        client.upsert(
            "candidate_baseline_comparisons_v55",
            {
                "request_id": request_id,
                "comparison_date": RUN_DATE,
                "comparison_key": comparison_key,
                "baseline_version_no": baseline_version_no,
                "candidate_version_no": version_no,
                "sample_size": evidence_count,
                "baseline_score": baseline_score,
                "candidate_score": candidate_score,
                "score_delta": score_delta,
                "calibration_delta": calibration_delta,
                "risk_failure_delta": risk_failure_delta,
                "stability_delta": stability_delta,
                "regression_status": reg_status,
                "comparison_status": comparison_status,
                "passed": comparison_pass,
                "summary": (
                    f"Candidate {version_no} vs baseline "
                    f"{baseline_version_no}: {comparison_status}."
                ),
                "evidence": {
                    "proxy_only": True,
                    "human_approval_required": True,
                    "source_mode": source["source_mode"],
                },
            },
            "comparison_date,comparison_key",
        )
        comparisons_completed += 1

        monitoring_status = (
            "PASS"
            if comparison_pass
            else "CRITICAL"
            if reg_status == "ROLLBACK_RECOMMENDED"
            else "WARNING"
        )
        recommendation = (
            "CONFIRM_FOR_MANUAL_PROMOTION"
            if comparison_pass
            and status == "READY_FOR_PAPER_CANARY"
            else "ROLLBACK_RECOMMENDED"
            if reg_status == "ROLLBACK_RECOMMENDED"
            else "CONTINUE_MONITORING"
        )

        client.upsert(
            "promotion_monitoring_v55",
            {
                "request_id": request_id,
                "monitoring_date": RUN_DATE,
                "monitoring_key": f"MONITOR:{version_no}",
                "monitoring_status": monitoring_status,
                "decision_score": candidate_score,
                "reliability_score": score,
                "calibration_error": candidate_calibration,
                "risk_gate_failure_rate": (
                    100.0 if candidate_risk_failures else 0.0
                ),
                "execution_block_rate": 0.0,
                "stability_score": candidate_stability,
                "critical_warning_count": (
                    1 if reg_status == "ROLLBACK_RECOMMENDED" else 0
                ),
                "recommendation": recommendation,
                "diagnostics": {
                    "comparison_key": comparison_key,
                    "run_id": run_id,
                    "source_mode": source["source_mode"],
                },
            },
            "monitoring_date,monitoring_key",
        )

        if reg_status != "NO_REGRESSION":
            event_key = f"REGRESSION:{version_no}:{reg_status}"
            client.upsert(
                "regression_events_v55",
                {
                    "request_id": request_id,
                    "event_time": now(),
                    "event_date": RUN_DATE,
                    "event_key": event_key,
                    "regression_type": (
                        "SCORE_DROP"
                        if score_delta < 0
                        else "STABILITY_DROP"
                    ),
                    "severity": (
                        "CRITICAL"
                        if reg_status == "ROLLBACK_RECOMMENDED"
                        else "WARNING"
                    ),
                    "observed_value": min(
                        score_delta,
                        stability_delta,
                    ),
                    "threshold_value": -10,
                    "event_status": "OPEN",
                    "message": (
                        f"Regression detected for {version_no}: "
                        f"{reg_status}."
                    ),
                    "evidence": {
                        "score_delta": score_delta,
                        "calibration_delta": calibration_delta,
                        "risk_failure_delta": risk_failure_delta,
                        "stability_delta": stability_delta,
                    },
                },
                "event_date,event_key",
            )
            regression_events_created += 1

        rollback_status = (
            "RECOMMENDED"
            if reg_status == "ROLLBACK_RECOMMENDED"
            else "MONITOR"
            if reg_status == "WARNING"
            else "NOT_REQUIRED"
        )
        rollback_severity = (
            "CRITICAL"
            if rollback_status == "RECOMMENDED"
            else "WARNING"
            if rollback_status == "MONITOR"
            else "INFO"
        )

        client.upsert(
            "rollback_recommendations_v55",
            {
                "request_id": request_id,
                "recommendation_date": RUN_DATE,
                "recommendation_key": f"ROLLBACK:{version_no}",
                "recommendation_status": rollback_status,
                "severity": rollback_severity,
                "reason": (
                    "Critical regression detected."
                    if rollback_status == "RECOMMENDED"
                    else "Continue Paper monitoring."
                    if rollback_status == "MONITOR"
                    else "No rollback required."
                ),
                "target_version_no": baseline_version_no,
                "rollback_snapshot_available": rollback_ready,
                "human_approval_required": True,
                "automatic_rollback_enabled": False,
                "executed": False,
                "evidence": {
                    "regression_status": reg_status,
                    "comparison_status": comparison_status,
                    "source_mode": source["source_mode"],
                },
            },
            "recommendation_date,recommendation_key",
        )
        rollback_recommendations_created += 1

        if recommendation == "CONFIRM_FOR_MANUAL_PROMOTION":
            confirmed_for_manual_promotion += 1
            client.patch(
                "promotion_requests_v55",
                f"id=eq.{request_id}",
                {
                    "request_status": "CONFIRMED_FOR_MANUAL_PROMOTION",
                },
            )
        elif rollback_status == "RECOMMENDED":
            client.patch(
                "promotion_requests_v55",
                f"id=eq.{request_id}",
                {
                    "request_status": "ROLLBACK_RECOMMENDED",
                },
            )

    overall_status = (
        "PASS"
        if requests_created > 0
        and regression_events_created == 0
        else "WARNING"
        if requests_created > 0
        else "CRITICAL"
    )

    if regression_events_created > 0:
        warnings.append("REGRESSION_EVENTS_DETECTED")

    summary = (
        f"Enterprise 5.5 v2.0 created {requests_created} promotion "
        f"request(s), {plans_created} Paper Canary plan(s), "
        f"{canary_cycles_created} cycle(s), "
        f"{comparisons_completed} comparison(s), "
        f"{regression_events_created} regression event(s), and "
        f"{rollback_recommendations_created} rollback recommendation(s)."
    )

    client.upsert(
        "promotion_metrics_v55",
        {
            "metric_date": RUN_DATE,
            "requests_created": requests_created,
            "readiness_checks": readiness_checks,
            "approvals_pending": approvals_pending,
            "paper_canary_plans": plans_created,
            "paper_canary_cycles": canary_cycles_created,
            "comparisons_completed": comparisons_completed,
            "regression_events": regression_events_created,
            "rollback_recommendations": rollback_recommendations_created,
            "confirmed_for_manual_promotion": confirmed_for_manual_promotion,
            "automatic_promotions": 0,
            "automatic_rollbacks": 0,
            "average_readiness_score": (
                mean(readiness_scores) if readiness_scores else 0
            ),
            "diagnostics": {
                "run_id": run_id,
                "engine_version": ENGINE_VERSION,
                "source_count": len(sources),
            },
        },
        "metric_date",
    )

    client.upsert(
        "promotion_status_v55",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_request_id": current_request_id,
            "current_candidate_version": current_candidate_version,
            "current_baseline_version": baseline_version_no,
            "requests_created": requests_created,
            "readiness_checks": readiness_checks,
            "approvals_pending": approvals_pending,
            "paper_canary_plans": plans_created,
            "paper_canary_cycles": canary_cycles_created,
            "comparisons_completed": comparisons_completed,
            "regression_events": regression_events_created,
            "rollback_recommendations": rollback_recommendations_created,
            "confirmed_for_manual_promotion": confirmed_for_manual_promotion,
            "human_approval_required": True,
            "automatic_production_promotion_enabled": False,
            "automatic_agent_weight_application_enabled": False,
            "automatic_risk_parameter_application_enabled": False,
            "automatic_rollback_execution_enabled": False,
            "live_trading_enabled": False,
            "broker_submission_enabled": False,
            "blockers": blockers,
            "warnings": warnings,
            "summary": summary,
            "diagnostics": {
                "run_id": run_id,
                "engine_version": ENGINE_VERSION,
                "source_modes": sorted(
                    {str(s["source_mode"]) for s in sources}
                ),
                "thresholds": {
                    "minimum_evidence": minimum_evidence,
                    "minimum_readiness": minimum_readiness,
                    "paper_traffic_pct": paper_traffic_pct,
                    "paper_duration_cycles": paper_duration_cycles,
                },
            },
        },
        "status_date",
    )

    if sources and requests_created == 0:
        raise RuntimeError(
            "Enterprise 5.5 had source candidates but created zero requests."
        )

    print(summary)
    print(f"Enterprise 5.5 Promotion Control status: {overall_status}")


if __name__ == "__main__":
    main()
