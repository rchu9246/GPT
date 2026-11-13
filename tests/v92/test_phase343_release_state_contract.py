"""Fail-closed contract tests for canonical Phase 3.4 release states."""

import importlib.util
import os
import unittest
from unittest.mock import patch
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
            "latest_snapshot_pass": True,
            "latest_market_date_present": True,
            "market_data_fresh": True,
            "equity_non_negative": True,
            "positions_within_limit": True,
            "drawdown_within_limit": True,
            "safety_mode_locked": True,
            "consecutive_pass_requirement": True,
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

    def test_phase34_evaluate_output_matches_readiness_contract(self):
        producer_spec = importlib.util.spec_from_file_location(
            "phase34_offline_producer", SOURCE.with_name("paper_trading_phase34_human_approval_release.py")
        )
        producer = importlib.util.module_from_spec(producer_spec)
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://invalid.example",
            "SUPABASE_SERVICE_ROLE_KEY": "offline-test",
            "PAPER_TRADING_MODE": "SHADOW_ONLY_NO_BROKER",
            "PHASE34_REQUIRED_PASS_DAYS": "5",
        }):
            producer_spec.loader.exec_module(producer)

        snapshots = [{
            "run_date": "2026-11-09",
            "latest_market_date": "2026-11-09",
            "status": "PASS",
            "equity": 1000000,
            "positions_open": 0,
        }]
        with patch.object(producer, "load_snapshots", return_value=snapshots), \
             patch.object(producer, "consecutive_pass_days", return_value=(60, [])), \
             patch.object(producer, "ACTION", "evaluate"), \
             patch.object(producer, "APPROVER", ""), \
             patch.object(producer, "APPROVAL_TEXT", ""):
            result = producer.evaluate()

        self.assertEqual(result["release_state"], "AWAITING_HUMAN_APPROVAL")
        self.assertEqual(READINESS.validate_source(result), (True, []))

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

    def assert_blocked(self, data, reason):
        valid, errors = READINESS.validate_source(data)
        self.assertFalse(valid)
        self.assertIn(reason, errors)
        summary = READINESS.build_summary(data, valid, errors)
        self.assertEqual(summary["approval_readiness"], "BLOCKED")
        self.assertEqual(summary["release_state"], "LOCKED")
        for flag in ("automatic_approval", "broker_trading_enabled", "real_money_trading_enabled"):
            self.assertIs(summary[flag], False)

    def test_every_required_check_must_be_present(self):
        for name in canonical_qualified()["checks"]:
            with self.subTest(name=name):
                data = canonical_qualified()
                del data["checks"][name]
                self.assert_blocked(data, "qualification_checks_incomplete")

    def test_non_boolean_values_are_rejected(self):
        for value in (1, "true", None, [], {}):
            with self.subTest(value=value):
                data = canonical_qualified()
                data["checks"]["latest_snapshot_pass"] = value
                self.assert_blocked(data, "qualification_checks_incomplete")

    def test_missing_malformed_and_unrelated_checks_are_rejected(self):
        for checks in (None, {}, ["unrelated"], {"unrelated": True},
                       {**canonical_qualified()["checks"], "unrelated": True}):
            with self.subTest(checks=checks):
                data = canonical_qualified()
                if checks is None:
                    del data["checks"]
                else:
                    data["checks"] = checks
                self.assert_blocked(data, "qualification_checks_incomplete")

    def test_each_safety_field_is_required_and_strict(self):
        for field, expected in canonical_qualified()["safety"].items():
            for value in (None, not expected, "DISARMED"):
                with self.subTest(field=field, value=value):
                    data = canonical_qualified()
                    if value is None:
                        del data["safety"][field]
                    else:
                        data["safety"][field] = value
                    self.assert_blocked(data, "paper_trading_safety_lock_invalid")

    def test_locked_status_cannot_bypass_readiness_checks(self):
        data = canonical_qualified()
        data.update(release_state="LOCKED", checks={"unrelated": True})
        self.assert_blocked(data, "locked_source_claims_completed_qualification")

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
