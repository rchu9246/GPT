from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "automation/v92/phase37191_failure_log_evidence_deep_inspection_targeted_workflow_discovery.py"
spec = importlib.util.spec_from_file_location("phase37191_diagnostic", SCRIPT)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def category(log):
    return diagnostic.classify(diagnostic.runtime_log_lines(log))[0]


class RuntimeClassificationTests(unittest.TestCase):
    def test_echoed_timeout_is_not_observed_timeout(self):
        log = '2026Z \x1b[36;1mecho "::error::Phase timed out"\x1b[0m\n2026Z ##[error]Process completed with exit code 1.'
        self.assertEqual(category(log), "UNKNOWN")

    def test_completed_pending_with_empty_failure_is_race(self):
        log = ('2026Z \x1b[36;1mecho "::error::Phase timed out"\x1b[0m\n'
               '2026Z Phase 3.7.6: status=completed conclusion=pending\n'
               '2026Z ##[error]Phase 3.7.6 Promotion Gate failed with \n'
               '2026Z ##[error]Process completed with exit code 1.')
        self.assertEqual(category(log), "CHILD_CONCLUSION_PENDING")

    def test_actual_child_failure_not_timeout(self):
        log = ('2026Z \x1b[36;1mecho "::error::Phase timed out"\x1b[0m\n'
               '2026Z Phase 3.7.10: status=completed conclusion=failure\n'
               '2026Z ##[error]Phase 3.7.10 failed with conclusion=failure')
        self.assertEqual(category(log), "CHILD_WORKFLOW_FAILURE")

    def test_emitted_timeout_is_timeout(self):
        self.assertEqual(category('2026Z ##[error]Phase 3.7.8 timed out.'), "TIMEOUT_POLLING")

    def test_routine_pending_poll_is_not_timeout(self):
        log = ('2026Z Phase 3.7.8 status=in_progress conclusion=pending\n'
               '2026Z ##[error]Process completed with exit code 1.')
        self.assertEqual(category(log), "UNKNOWN")

    def test_actual_schema_error(self):
        self.assertEqual(category('2026Z ##[error]PGRST: column old_field does not exist'), "DATABASE_SCHEMA_COMPATIBILITY")


if __name__ == "__main__":
    unittest.main()
