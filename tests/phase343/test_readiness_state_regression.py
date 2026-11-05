"""Regression tests for Phase 3.4.3 pre-approval safety contract."""
import unittest
from automation.v92.paper_trading_phase343_approval_readiness import validate_source


def canonical(**overrides):
    row = {
        "status": "PASS",
        "qualification_state": "QUALIFIED",
        "release_state": "AWAITING_HUMAN_APPROVAL",
        "requested_action": "evaluate",
        "consecutive_pass_days": 5,
        "latest_market_date": "2026-11-04",
        "market_stale_days": 0,
        "pass_day_source": "distinct_run_date_snapshot_status",
        "mode": "SHADOW_ONLY_NO_BROKER",
    }
    row.update(overrides)
    return row


class Phase343ReadinessSafetyTests(unittest.TestCase):
    def test_qualified_awaiting_human_approval_is_valid(self):
        self.assertEqual(validate_source(canonical()), (True, []))

    def test_observation_must_remain_locked(self):
        self.assertFalse(validate_source(canonical(
            qualification_state="OBSERVATION", consecutive_pass_days=2
        ))[0])

    def test_approved_state_cannot_pass_evaluate_gate(self):
        self.assertFalse(validate_source(canonical(
            release_state="PRODUCTION_PAPER_APPROVED"
        ))[0])

    def test_revoked_state_cannot_pass_evaluate_gate(self):
        self.assertFalse(validate_source(canonical(
            release_state="PRODUCTION_PAPER_REVOKED"
        ))[0])

    def test_non_evaluate_action_cannot_pass_preapproval_gate(self):
        self.assertFalse(validate_source(canonical(
            requested_action="approve_production_paper"
        ))[0])

    def test_unqualified_locked_state_is_valid_observation(self):
        self.assertEqual(validate_source(canonical(
            qualification_state="OBSERVATION", release_state="LOCKED",
            consecutive_pass_days=2
        )), (True, []))


if __name__ == "__main__":
    unittest.main()
