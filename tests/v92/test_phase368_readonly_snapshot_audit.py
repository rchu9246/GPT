"""Offline tests for Phase 3.6.8 snapshot audit; no network or secrets."""
import unittest
from automation.v92.phase368_readonly_snapshot_audit import SOURCES, audit, PORTFOLIO, STRATEGY

DAY = "2026-11-13"

def fixture():
    rows = {k: {"portfolio_id": PORTFOLIO, "strategy_version": STRATEGY, date_field: DAY,
                "updated_at": DAY + "T12:00:00+00:00"}
            for k, (_, date_field) in SOURCES.items()}
    rows["supervision"].update(supervision_state="CONTINUE_ACTIVE", safety_revocation_triggered=False,
                                autonomous_paper_operations_continued=True, reason_codes=[], critical_failures=[],
                                paper_only=True, fail_closed_policy=True,
                                broker_api_used=False, broker_credentials_used=False,
                                broker_order_submission_enabled=False, real_money_trading_enabled=False,
                                live_money_release_authorized=False,
                                canonical_dates={source: DAY for source in
                                                 ("activation", "qualification", "readiness", "health", "sla", "master")})
    rows["activation"].update(activation_state="ACTIVE", autonomous_paper_operations_active=True)
    rows["qualification"].update(qualification_state="QUALIFIED", autonomous_paper_operations_authorized=True)
    rows["readiness"].update(readiness_status="READY", promotion_gate_open=True)
    rows["health"]["health_status"] = "HEALTHY"
    rows["sla"]["sla_status"] = "SLA_PASS"
    rows["master"]["master_status"] = "PASS"
    rows["incident"]["incident_state"] = "CLOSED"
    rows["supervision"].update(activation_state="ACTIVE", qualification_state="QUALIFIED",
                               readiness_state="READY", health_state="HEALTHY", sla_state="SLA_PASS",
                               master_cycle_state="PASS", open_incident=False,
                               incident_severity="UNKNOWN")
    rows.update(portfolio_id=PORTFOLIO, strategy_version=STRATEGY, business_date=DAY,
                producer={"run_id": 999999, "attempt": 1, "canonical_sizing_authority": True,
                          "business_date": DAY, "portfolio_id": PORTFOLIO, "strategy_version": STRATEGY,
                          "evidence_sha256": "a" * 64},
                recovery_approval={"authorized": True, "operator": "test-only", "code_sha": "b" * 40,
                                   "portfolio_id": PORTFOLIO, "strategy_version": STRATEGY,
                                   "business_date": DAY, "stop_conditions": "stop"})
    return rows

class ReadonlyAuditTests(unittest.TestCase):
    def test_reviewable_not_executable(self):
        result = audit(fixture(), DAY)
        self.assertEqual(result["status"], "READY")
        self.assertFalse(result["authorizes_execution"])

    def test_missing_snapshot(self):
        self.assertEqual(audit(None, DAY)["status"], "INSUFFICIENT_EVIDENCE")

    def test_missing_source(self):
        row = fixture(); del row["sla"]
        self.assertEqual(audit(row, DAY)["status"], "INSUFFICIENT_EVIDENCE")

    def test_noncanonical_supervision_state_fails_closed(self):
        row = fixture(); row["supervision"]["supervision_state"] = "CONTINUE"
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_supervision_critical_failure_blocks(self):
        row = fixture(); row["supervision"]["critical_failures"] = ["readiness_gate"]
        result = audit(row, DAY)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("SUPERVISION_CRITICAL_FAILURES_PRESENT", result["reasons"])

    def test_supervision_critical_reason_blocks(self):
        row = fixture(); row["supervision"]["reason_codes"] = ["CRITICAL_READINESS_GATE"]
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_missing_supervision_critical_failures_is_insufficient(self):
        row = fixture(); del row["supervision"]["critical_failures"]
        self.assertEqual(audit(row, DAY)["status"], "INSUFFICIENT_EVIDENCE")

    def test_broker_submission_flag_blocks_even_when_supervision_claims_safe(self):
        row = fixture(); row["activation"]["broker_order_submission_enabled"] = True
        result = audit(row, DAY)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("UNSAFE_ACTIVATION_BROKER_ORDER_SUBMISSION_ENABLED", result["reasons"])

    def test_synthetic_market_data_blocks(self):
        row = fixture(); row["health"]["synthetic_market_data"] = True
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_fail_closed_policy_false_blocks(self):
        row = fixture(); row["master"]["fail_closed_policy"] = False
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_canonical_dates_conflict_blocks(self):
        row = fixture()
        row["supervision"]["canonical_dates"] = {
            source: DAY for source in ("activation", "qualification", "readiness", "health", "sla", "master")
        }
        row["supervision"]["canonical_dates"]["master"] = "2026-11-12"
        self.assertIn("SUPERVISION_CANONICAL_DATE_MISMATCH_MASTER", audit(row, DAY)["reasons"])

    def test_valid_canonical_dates_are_reviewable(self):
        row = fixture()
        row["supervision"]["canonical_dates"] = {
            source: DAY for source in ("activation", "qualification", "readiness", "health", "sla", "master")
        }
        self.assertEqual(audit(row, DAY)["status"], "READY")

    def test_supervision_level_broker_flag_blocks(self):
        row = fixture(); row["supervision"]["broker_order_submission_enabled"] = True
        result = audit(row, DAY)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("UNSAFE_SUPERVISION_BROKER_ORDER_SUBMISSION_ENABLED", result["reasons"])

    def test_supervision_level_real_money_flag_blocks(self):
        row = fixture(); row["supervision"]["real_money_trading_enabled"] = True
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_missing_supervision_paper_only_is_insufficient(self):
        row = fixture(); del row["supervision"]["paper_only"]
        self.assertEqual(audit(row, DAY)["status"], "INSUFFICIENT_EVIDENCE")

    def test_missing_supervision_canonical_dates_is_insufficient(self):
        row = fixture(); del row["supervision"]["canonical_dates"]
        result = audit(row, DAY)
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("SUPERVISION_CANONICAL_DATES_MISSING", result["reasons"])

    def test_supervision_activation_claim_conflict(self):
        row = fixture(); row["supervision"]["activation_state"] = "BLOCKED"
        result = audit(row, DAY)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("SUPERVISION_CLAIM_CONFLICT_ACTIVATION_STATE", result["reasons"])

    def test_supervision_readiness_claim_conflict(self):
        row = fixture(); row["supervision"]["readiness_state"] = "NOT_READY"
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_supervision_master_claim_conflict(self):
        row = fixture(); row["supervision"]["master_cycle_state"] = "FAILED"
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_missing_supervision_qualification_claim_is_insufficient(self):
        row = fixture(); del row["supervision"]["qualification_state"]
        result = audit(row, DAY)
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("SUPERVISION_CLAIM_MISSING_QUALIFICATION_STATE", result["reasons"])

    def test_supervision_open_incident_claim_conflict(self):
        row = fixture(); row["supervision"]["open_incident"] = True
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_supervision_incident_severity_claim_conflict(self):
        row = fixture(); row["supervision"]["incident_severity"] = "CRITICAL"
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_revoked(self):
        row = fixture(); row["supervision"]["safety_revocation_triggered"] = True
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_stale_master(self):
        row = fixture(); row["master"]["cycle_date"] = "2026-09-11"
        self.assertIn("DATE_MISMATCH_MASTER", audit(row, DAY)["reasons"])

    def test_bad_producer(self):
        row = fixture(); row["producer"].update(run_id=43272218054, attempt=1, canonical_sizing_authority=False)
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_missing_authority(self):
        row = fixture(); row["producer"]["canonical_sizing_authority"] = False
        self.assertEqual(audit(row, DAY)["status"], "INSUFFICIENT_EVIDENCE")

    def test_missing_approval(self):
        row = fixture(); del row["recovery_approval"]
        self.assertEqual(audit(row, DAY)["status"], "INSUFFICIENT_EVIDENCE")

    def test_wrong_portfolio(self):
        row = fixture(); row["health"]["portfolio_id"] = "OTHER"
        self.assertEqual(audit(row, DAY)["status"], "BLOCKED")

    def test_timestamp_required(self):
        row = fixture(); del row["health"]["updated_at"]
        self.assertEqual(audit(row, DAY)["status"], "INSUFFICIENT_EVIDENCE")

if __name__ == "__main__":
    unittest.main()
