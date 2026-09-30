from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / ".github/supabase/validation/phase353_handoff_receipt_live_validation.sql"
DOC = ROOT / "docs/phase353-scheduled-authority.md"

# One stable fragment for every semantic assertion in the pre-refactor script.
ASSERTION_INVENTORY = {
    "receipt_table_exists": "PHASE353_LIVE_VALIDATION_L01_TABLE",
    "required_columns_exist": "PHASE353_LIVE_VALIDATION_L02_COLUMNS",
    "identity_constraint_exists": "PHASE353_LIVE_VALIDATION_L03_UNIQUE_CONSTRAINT",
    "rls_enabled": "PHASE353_LIVE_VALIDATION_L04_RLS",
    "mutation_rpcs_exist": "PHASE353_LIVE_VALIDATION_L05_RPC_EXISTENCE",
    "completion_rpc_absent": "PHASE353_LIVE_VALIDATION_L06_COMPLETION_RPC",
    "untrusted_execute_absent": "PHASE353_LIVE_VALIDATION_L07_UNTRUSTED_PRIVILEGES",
    "service_rpc_and_update_privileges": "PHASE353_LIVE_VALIDATION_L08_SERVICE_PRIVILEGES",
    "first_claim": "first claim did not return CLAIM_ACQUIRED/CLAIMED",
    "identical_claim_replay": "identical replay did not return ALREADY_CLAIMED/CLAIMED",
    "identical_replay_single_row": "identical replay created more than one row",
    "conflicting_sha": "conflicting producer SHA did not fail closed",
    "conflicting_authority_hash": "conflicting authority hash did not fail closed",
    "conflicting_business_date": "conflicting business date did not fail closed",
    "claimed_to_dispatch_accepted": "CLAIMED to DISPATCH_ACCEPTED failed",
    "dispatch_replay": "dispatch acceptance replay was not idempotent",
    "dispatch_does_not_complete": "HTTP acceptance state was not preserved as DISPATCH_ACCEPTED",
    "collector_survives_commit": "temporary result collector did not survive",
    "transaction_marker_is_local": "PHASE353_LIVE_VALIDATION_L18_MARKER_ISOLATION",
    "completed_rejected": "PHASE353_LIVE_VALIDATION_L19_COMPLETED_REJECTION",
    "reverse_transition_rejected": "PHASE353_LIVE_VALIDATION_L20_REVERSE_STATUS",
    "direct_last_error_rejected": "PHASE353_LIVE_VALIDATION_L21_LAST_ERROR",
    "identity_update_rejected": "PHASE353_LIVE_VALIDATION_L22_IMMUTABLE_IDENTITY",
    "anon_rpc_denied": "PHASE353_LIVE_VALIDATION_L23_ANON_DENIAL",
    "authenticated_rpc_denied": "PHASE353_LIVE_VALIDATION_L24_AUTHENTICATED_DENIAL",
    "service_role_claim_and_claimed_failed": "PHASE353_LIVE_VALIDATION_L25_CLAIMED_FAILED",
    "accepted_to_failed": "PHASE353_LIVE_VALIDATION_L26_ACCEPTED_FAILED",
    "identical_failed_replay": "PHASE353_LIVE_VALIDATION_L27_FAILURE_REPLAY",
    "conflicting_failed_replay": "PHASE353_LIVE_VALIDATION_L28_CONFLICTING_REPLAY",
    "failed_terminal": "PHASE353_LIVE_VALIDATION_L29_FAILED_TERMINAL",
    "exact_cleanup": "PHASE353_LIVE_VALIDATION_L30_CLEANUP",
}


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

    def test_result_collector_survives_validation_commit(self):
        create_at = self.lower.index("create temporary table phase353_validation_results")
        first_commit_after_create = self.lower.index("commit;", create_at)
        last_reference = self.lower.rindex("pg_temp.phase353_validation_results")
        self.assertIn("on commit preserve rows", self.lower[create_at:first_commit_after_create])
        self.assertGreater(last_reference, first_commit_after_create)
        self.assertIn("temporary result collector did not survive", self.lower)
        self.assertNotIn("on commit drop", self.lower)

    def test_result_collector_references_are_temp_schema_qualified(self):
        references = [line.strip() for line in self.sql.splitlines()
                      if "phase353_validation_results" in line
                      and not line.strip().lower().startswith("create temporary table")]
        self.assertTrue(references)
        self.assertTrue(all("pg_temp.phase353_validation_results" in line for line in references))

    def test_expected_error_blocks_cannot_drop_collector(self):
        self.assertNotRegex(self.lower, r"drop\s+table\s+(?:if\s+exists\s+)?(?:pg_temp\.)?phase353_validation_results")
        self.assertLess(self.lower.index("create temporary table phase353_validation_results"),
                        self.lower.index("do $checkpoint$", self.lower.index("create temporary table phase353_validation_results")))

    def test_no_persistent_validation_table_is_created(self):
        self.assertNotRegex(self.lower, r"create\s+table\s+(?:public\.)?phase353_validation_results")
        self.assertIn("create temporary table phase353_validation_results", self.lower)

    def test_semantic_assertion_inventory_is_complete(self):
        self.assertEqual(31, len(ASSERTION_INVENTORY))
        for name, fragment in ASSERTION_INVENTORY.items():
            with self.subTest(assertion=name):
                self.assertIn(fragment, self.sql)

    def test_no_executable_relation_or_alias_named_a(self):
        executable = re.sub(r"--[^\n]*", " ", self.sql)
        executable = re.sub(r"'(?:''|[^'])*'", "''", executable)
        executable = re.sub(r"\$[a-z_]*\$.*?\$[a-z_]*\$", " ", executable,
                            flags=re.IGNORECASE | re.DOTALL)
        self.assertNotRegex(executable.lower(),
                            r"\b(?:from|join|update|into)\s+(?:only\s+)?a\b|\bas\s+a\b")

    def test_migration_removes_service_role_mutation_privileges(self):
        migration = (ROOT / ".github/supabase/migrations/015_phase353_handoff_receipts.sql").read_text(encoding="utf-8").lower()
        revoke = "revoke all privileges on table public.phase353_handoff_receipts from service_role;"
        grant = "grant select on table public.phase353_handoff_receipts to service_role;"
        self.assertIn(revoke, migration)
        self.assertIn(grant, migration)
        self.assertLess(migration.index(revoke), migration.index(grant))
        self.assertNotIn("grant update on table public.phase353_handoff_receipts", migration)


if __name__ == "__main__":
    unittest.main()

