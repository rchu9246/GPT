"""Offline tests for Phase 3.6.8 snapshot audit; no network or secrets."""
import unittest
from automation.v92.phase368_readonly_snapshot_audit import SOURCES, audit, PORTFOLIO, STRATEGY

DAY = "2026-11-13"

def fixture():
    rows = {k: {"portfolio_id": PORTFOLIO, "strategy_version": STRATEGY, date_field: DAY,
                "updated_at": DAY + "T12:00:00+00:00"}
            for k, (_, date_field) in SOURCES.items()}
    rows["supervision"].update(supervision_state="CONTINUE", safety_revocation_triggered=False,
                                autonomous_paper_operations_continued=True, reason_codes=[])
    rows["activation"].update(activation_state="ACTIVE", autonomous_paper_operations_active=True)
    rows["qualification"].update(qualification_state="QUALIFIED", autonomous_paper_operations_authorized=True)
    rows["readiness"].update(readiness_status="READY", promotion_gate_open=True)
    rows["health"]["health_status"] = "HEALTHY"
    rows["sla"]["sla_status"] = "SLA_PASS"
    rows["master"]["master_status"] = "PASS"
    rows["incident"]["incident_state"] = "CLOSED"
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
