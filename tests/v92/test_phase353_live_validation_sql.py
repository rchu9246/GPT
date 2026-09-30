from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / ".github/supabase/validation/phase353_handoff_receipt_live_validation.sql"
DOC = ROOT / "docs/phase353-scheduled-authority.md"


class Phase353LiveValidationSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = VALIDATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()
        cls.doc = DOC.read_text(encoding="utf-8")

    def test_only_exact_synthetic_receipt_identity_is_used(self):
        self.assertIn("VALIDATION_ONLY_PHASE353_REPOSITORY", self.sql)
        self.assertIn("VALIDATION_ONLY_PHASE353_WORKFLOW", self.sql)
        self.assertIn("VALIDATION_ONLY_PHASE353_CONSUMER", self.sql)
        self.assertNotRegex(self.lower, r"\b(paper_|trade_|position|order)[a-z0-9_]*\s*(?:set|values)")

    def test_cleanup_is_exact_and_never_broad(self):
        deletes = re.findall(r"delete from public\.phase353_handoff_receipts\s+where\s+(.+?);",
                             self.sql, flags=re.IGNORECASE | re.DOTALL)
        self.assertGreaterEqual(len(deletes), 2)
        for where in deletes:
            for required in ("repository =", "producer_workflow =", "producer_run_id in",
                             "producer_run_attempt =", "consumer ="):
                self.assertIn(required, where.lower())
        self.assertNotIn("truncate", self.lower)

    def test_structure_and_rpc_existence_are_checked(self):
        for token in ("to_regclass('public.phase353_handoff_receipts')",
                      "phase353_handoff_receipts_identity_key", "relrowsecurity",
                      "claim_phase353_handoff", "mark_phase353_handoff_dispatch_accepted",
                      "mark_phase353_handoff_failed"):
            self.assertIn(token.lower(), self.lower)

    def test_claim_replay_and_conflicts_are_checked(self):
        for token in ("CLAIM_ACQUIRED", "ALREADY_CLAIMED", "conflicting producer SHA",
                      "conflicting authority hash", "conflicting business date"):
            self.assertIn(token, self.sql)

    def test_transitions_terminal_states_and_marker_are_checked(self):
        for token in ("ALREADY_DISPATCH_ACCEPTED", "status = 'COMPLETED'",
                      "CLAIMED to FAILED", "DISPATCH_ACCEPTED to FAILED",
                      "ALREADY_FAILED", "FAILED was not terminal",
                      "app.phase353_handoff_transition"):
            self.assertIn(token, self.sql)

    def test_role_behavior_is_exercised(self):
        for role in ("anon", "authenticated", "service_role"):
            self.assertIn(f"set local role {role};", self.lower)
        self.assertIn("not has_table_privilege('service_role'", self.lower)

    def test_no_workflow_or_network_execution_exists(self):
        for forbidden in ("workflow_dispatch", "api.github.com", "broker", "subprocess", "requests."):
            self.assertNotIn(forbidden, self.lower)

    def test_documented_order_and_real_two_session_test(self):
        self.assertIn("015_phase353_handoff_receipts.sql", self.doc)
        self.assertIn("phase353_handoff_receipt_live_validation.sql", self.doc)
        self.assertIn("session A", self.doc)
        self.assertIn("session B", self.doc)
        self.assertIn("pg_sleep(20)", self.doc)
        self.assertIn("exact_row_count` must be `1`", self.doc)


if __name__ == "__main__":
    unittest.main()
