"""Fail-closed contract tests for canonical Phase 3.4 release states."""

import importlib.util
import unittest
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "automation/v92/paper_trading_phase343_approval_readiness.py"
)
SPEC = importlib.util.spec_from_file_location("phase343_readiness", SOURCE)
READINESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READINESS)


def canonical_qualified():
    return {
        "status": "PASS",
        "qualification_state": "QUALIFIED",
        "release_state": "AWAITING_HUMAN_APPROVAL",
        "consecutive_pass_days": 60,
        "latest_market_date": "2026-11-09",
        "market_stale_days": 0,
        "pass_day_source": "distinct_run_date_snapshot_status",
        "mode": "SHADOW_ONLY_NO_BROKER",
        "requested_action": "evaluate",
        "checks": {
            "consecutive_pass_requirement": True,
            "safety_mode_locked": True,
        },
        "approval": {
            "required": True,
            "approver_present": False,
            "approval_phrase_valid": False,
        },
        "safety": {
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "automatic_live_switch_enabled": False,
            "paper_release_only": True,
            "kill_switch": "ARMED",
            "fail_closed": True,
        },
    }


class Phase343ReleaseContractTests(unittest.TestCase):
    def test_qualified_awaiting_is_ready_for_human_only(self):
        data = canonical_qualified()
        valid, errors = READINESS.validate_source(data)
        self.assertTrue(valid, errors)
        summary = READINESS.build_summary(data, valid, errors)
        self.assertEqual(summary["approval_readiness"], "READY_FOR_HUMAN_APPROVAL")
        self.assertEqual(summary["release_state"], "LOCKED")
        self.assertFalse(summary["automatic_approval"])
        self.assertFalse(summary["broker_trading_enabled"])
        self.assertFalse(summary["real_money_trading_enabled"])

    def test_unqualified_awaiting_is_rejected(self):
        data = canonical_qualified()
        data["qualification_state"] = "OBSERVATION"
        self.assertFalse(READINESS.validate_source(data)[0])

    def test_insufficient_days_are_rejected(self):
        data = canonical_qualified()
        data["consecutive_pass_days"] = 2
        self.assertFalse(READINESS.validate_source(data)[0])

    def test_incomplete_qualification_checks_are_rejected(self):
        data = canonical_qualified()
        data["checks"]["safety_mode_locked"] = False
        self.assertFalse(READINESS.validate_source(data)[0])

    def test_approval_presence_is_rejected(self):
        data = canonical_qualified()
        data["approval"]["approver_present"] = True
        self.assertFalse(READINESS.validate_source(data)[0])

    def test_real_money_flag_is_rejected(self):
        data = canonical_qualified()
        data["safety"]["real_money_enabled"] = True
        self.assertFalse(READINESS.validate_source(data)[0])

    def test_non_evaluate_action_is_rejected(self):
        data = canonical_qualified()
        data["requested_action"] = "approve_production_paper"
        self.assertFalse(READINESS.validate_source(data)[0])

    def test_approved_release_is_rejected(self):
        data = canonical_qualified()
        data["release_state"] = "PRODUCTION_PAPER_APPROVED"
        self.assertFalse(READINESS.validate_source(data)[0])

    def test_locked_observation_remains_valid(self):
        data = canonical_qualified()
        data["release_state"] = "LOCKED"
        data["qualification_state"] = "OBSERVATION"
        data["consecutive_pass_days"] = 2
        self.assertEqual(READINESS.validate_source(data), (True, []))


if __name__ == "__main__":
    unittest.main()
