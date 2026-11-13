"""Offline, fail-closed Phase 3.6.8 snapshot audit. Never contacts Supabase."""
import argparse
from datetime import date, datetime
import json
from pathlib import Path

PORTFOLIO = "V92_PRODUCTION_PAPER_V91"
STRATEGY = "V9.1"
SOURCES = {
    "supervision": ("paper_runtime_supervision_state_v92", "supervision_date"),
    "activation": ("paper_autonomous_activation_state_v92", "activation_date"),
    "qualification": ("paper_continuous_qualification_v92", "qualification_date"),
    "readiness": ("paper_operational_readiness_v92", "readiness_date"),
    "health": ("paper_system_health_v92", "health_date"),
    "sla": ("paper_observability_daily_v92", "observation_date"),
    "master": ("paper_master_cycles_v92", "cycle_date"),
    "incident": ("paper_incident_audit_v92", "incident_date"),
}

def audit(snapshot, business_date, portfolio=PORTFOLIO, strategy=STRATEGY):
    """READY means evidence is reviewable, NOT permission to execute."""
    errors, missing = [], []
    try:
        date.fromisoformat(business_date)
    except (TypeError, ValueError):
        return {"status": "INSUFFICIENT_EVIDENCE", "reasons": ["INVALID_BUSINESS_DATE"]}
    if not isinstance(snapshot, dict):
        return {"status": "INSUFFICIENT_EVIDENCE", "reasons": ["INVALID_SNAPSHOT"]}
    if snapshot.get("portfolio_id") != portfolio or snapshot.get("strategy_version") != strategy:
        errors.append("SNAPSHOT_SCOPE_MISMATCH")
    if snapshot.get("business_date") != business_date:
        errors.append("SNAPSHOT_DATE_MISMATCH")
    for source, (_, date_field) in SOURCES.items():
        row = snapshot.get(source)
        if not isinstance(row, dict):
            missing.append("MISSING_" + source.upper())
            continue
        if row.get("portfolio_id") != portfolio or row.get("strategy_version") != strategy:
            errors.append("SCOPE_MISMATCH_" + source.upper())
        if row.get(date_field) != business_date:
            errors.append("DATE_MISMATCH_" + source.upper())
        stamp = row.get("updated_at") or row.get("created_at")
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.date() < date.fromisoformat(business_date):
                errors.append("STALE_TIMESTAMP_" + source.upper())
        except (TypeError, ValueError, AttributeError):
            missing.append("MISSING_TIMESTAMP_" + source.upper())
        # Match Phase 3.6.7's critical safety checks for canonical input rows.
        # Optional fields, when supplied, must not contradict the paper-only contract.
        if source in ("activation", "qualification", "readiness", "health", "sla", "master"):
            for key in (
                "synthetic_market_data", "synthetic_signals", "fake_prices_allowed",
                "broker_api_used", "broker_credentials_used",
                "broker_order_submission_enabled", "real_money_trading_enabled",
                "live_money_release_authorized",
            ):
                if key in row and row[key] is not False:
                    errors.append("UNSAFE_" + source.upper() + "_" + key.upper())
            if "fail_closed_policy" in row and row["fail_closed_policy"] is not True:
                errors.append("FAIL_CLOSED_DISABLED_" + source.upper())
        if source == "supervision":
            if row.get("safety_revocation_triggered") is True:
                errors.append("SAFETY_REVOCATION_TRIGGERED")
            if row.get("safety_revocation_triggered") is not False:
                missing.append("REVOCATION_NOT_VERIFIED_FALSE")
            if row.get("autonomous_paper_operations_continued") is not True:
                errors.append("AUTONOMOUS_CONTINUATION_NOT_AUTHORIZED")
            if row.get("supervision_state") not in ("CONTINUE_ACTIVE", "CONTINUE_WITH_OBSERVATION"):
                errors.append("SUPERVISION_NOT_CONTINUABLE")
            if not isinstance(row.get("reason_codes"), list):
                missing.append("SUPERVISION_REASONS_MISSING")
            elif any(isinstance(reason, str) and reason.upper().startswith("CRITICAL_") for reason in row["reason_codes"]):
                errors.append("SUPERVISION_CRITICAL_REASON_PRESENT")
            canonical_dates = row.get("canonical_dates")
            if canonical_dates is not None:
                if not isinstance(canonical_dates, dict):
                    missing.append("SUPERVISION_CANONICAL_DATES_MALFORMED")
                else:
                    for canonical_source in ("activation", "qualification", "readiness", "health", "sla", "master"):
                        if canonical_dates.get(canonical_source) != business_date:
                            errors.append("SUPERVISION_CANONICAL_DATE_MISMATCH_" + canonical_source.upper())
            critical = row.get("critical_failures")
            if not isinstance(critical, list):
                missing.append("SUPERVISION_CRITICAL_FAILURES_UNVERIFIED")
            elif critical:
                errors.append("SUPERVISION_CRITICAL_FAILURES_PRESENT")
        if source == "activation" and (row.get("activation_state") not in ("ACTIVE", "ACTIVE_WITH_OBSERVATION") or row.get("autonomous_paper_operations_active") is not True):
            errors.append("ACTIVATION_NOT_ACTIVE")
        if source == "qualification" and (row.get("qualification_state") not in ("QUALIFIED", "QUALIFIED_WITH_OBSERVATION") or row.get("autonomous_paper_operations_authorized") is not True):
            errors.append("QUALIFICATION_NOT_AUTHORIZED")
        if source == "readiness" and (row.get("readiness_status") not in ("READY", "READY_WITH_OBSERVATION") or row.get("promotion_gate_open") is not True):
            errors.append("READINESS_NOT_READY")
        if source == "health" and row.get("health_status") not in ("HEALTHY", "DEGRADED"):
            errors.append("HEALTH_NOT_VALID")
        if source == "sla" and row.get("sla_status") not in ("SLA_PASS", "SLA_WARN"):
            errors.append("SLA_NOT_VALID")
        if source == "master" and (row.get("cycle_status") or row.get("master_status") or row.get("status")) not in ("PASS", "SUCCESS", "COMPLETED", "HEALTHY"):
            errors.append("MASTER_NOT_PASS")
        if source == "incident" and (row.get("incident_state") or row.get("incident_status") or row.get("status")) not in ("CLOSED", "RESOLVED", "CLEAR", "NONE", "OBSERVED"):
            errors.append("INCIDENT_NOT_CLEAR")
    producer = snapshot.get("producer")
    if not isinstance(producer, dict):
        missing.append("PRODUCER_MISSING")
    else:
        if (producer.get("run_id"), producer.get("attempt")) == (43272218054, 1):
            errors.append("KNOWN_PRODUCER_WITHOUT_SIZING_AUTHORITY")
        if producer.get("canonical_sizing_authority") is not True:
            missing.append("CANONICAL_SIZING_AUTHORITY_NOT_PROVEN")
        if producer.get("business_date") != business_date or producer.get("portfolio_id") != portfolio or producer.get("strategy_version") != strategy:
            errors.append("PRODUCER_SCOPE_MISMATCH")
        if not isinstance(producer.get("run_id"), int) or not isinstance(producer.get("attempt"), int) or producer.get("attempt", 0) < 1 or not isinstance(producer.get("evidence_sha256"), str) or len(producer.get("evidence_sha256", "")) != 64:
            missing.append("PRODUCER_PROVENANCE_INCOMPLETE")
    approval = snapshot.get("recovery_approval")
    if not isinstance(approval, dict) or approval.get("authorized") is not True or approval.get("portfolio_id") != portfolio or approval.get("strategy_version") != strategy or approval.get("business_date") != business_date or not approval.get("operator") or not approval.get("code_sha") or not approval.get("stop_conditions"):
        missing.append("SCOPED_RECOVERY_APPROVAL_MISSING")
    return {
        "status": "BLOCKED" if errors else "INSUFFICIENT_EVIDENCE" if missing else "READY",
        "reasons": sorted(set(errors + missing)),
        "business_date": business_date, "portfolio_id": portfolio,
        "strategy_version": strategy, "read_only": True,
        "authorizes_execution": False,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--business-date", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.snapshot.read_text(encoding="utf-8")), args.business_date), indent=2))

if __name__ == "__main__":
    main()
