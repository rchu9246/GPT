from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = ROOT / ".github/supabase/validation/phase353_handoff_receipt_post_commit_diagnostic.sql"


class Phase353PostCommitDiagnosticSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL_PATH.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_checkpoints_are_unique_ordered_and_complete(self):
        labels = re.findall(r"PHASE353_DIAG_(D\d{2}_[A-Z_]+)", self.sql)
        self.assertEqual(labels, [
            "D01_COLLECTOR", "D02_MARKER_ISOLATION", "D03_COMPLETED_REJECTION",
            "D04_REVERSE_STATUS", "D05_LAST_ERROR", "D06_IMMUTABLE_IDENTITY",
            "D07_ANON_DENIAL", "D08_AUTHENTICATED_DENIAL", "D09_CLAIMED_FAILED",
            "D10_ACCEPTED_FAILED", "D11_FAILURE_REPLAY", "D12_CONFLICTING_REPLAY",
            "D13_FAILED_TERMINAL", "D14_CLEANUP",
        ])

    def test_each_checkpoint_preserves_sqlstate_and_message(self):
        blocks = re.findall(r"do \$checkpoint\$(.*?)\$checkpoint\$;", self.sql,
                            flags=re.IGNORECASE | re.DOTALL)
        self.assertEqual(len(blocks), 14)
        for block in blocks:
            self.assertIn("exception when others", block.lower())
            self.assertRegex(block.lower(), r"raise exception 'phase353_diag_d\d{2}_[a-z_]+ \[%\] %', sqlstate, sqlerrm")

    def test_diagnostic_is_independent_of_other_editor_sessions(self):
        self.assertIn("create or replace function pg_temp.phase353_diag_assert", self.lower)
        self.assertIn("create temporary table phase353_diagnostic_results", self.lower)
        self.assertIn("on commit preserve rows", self.lower)
        self.assertNotIn("phase353_validation_results", self.lower)

    def test_only_exact_diagnostic_identities_are_used(self):
        quoted = re.findall(r"'(VALIDATION_ONLY_PHASE353[^']*)'", self.sql)
        self.assertTrue(quoted)
        self.assertTrue(all(value.startswith("VALIDATION_ONLY_PHASE353_DIAGNOSTIC_") for value in quoted))
        self.assertEqual(set(re.findall(r"935302\d+", self.sql)), {"935302001", "935302003"})

    def test_exact_cleanup_exists_at_start_end_and_recovery(self):
        deletes = re.findall(r"delete from public\.phase353_handoff_receipts\s+where\s+(.+?);",
                             self.sql, flags=re.IGNORECASE | re.DOTALL)
        self.assertEqual(len(deletes), 2)
        for where in deletes:
            for term in ("repository =", "producer_workflow =", "producer_run_id in",
                         "producer_run_attempt =", "consumer ="):
                self.assertIn(term, where.lower())
        self.assertIn("-- Exact recovery before a run or after any failure:", self.sql)
        self.assertIn("-- delete from public.phase353_handoff_receipts", self.sql)

    def test_no_persistent_diagnostic_relation_or_financial_table(self):
        self.assertNotRegex(self.lower, r"create\s+table\s+(?:public\.)?phase353_diagnostic")
        self.assertNotIn("truncate", self.lower)
        for forbidden in ("paper_", "trade_orders", "positions", "portfolio", "broker"):
            self.assertNotIn(forbidden, self.lower)

    def test_no_workflow_integration(self):
        workflows = "\n".join(path.read_text(encoding="utf-8-sig")
                              for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertNotIn("phase353_handoff_receipt_post_commit_diagnostic", workflows)
        self.assertNotIn("PHASE353_POST_COMMIT_DIAGNOSTIC_PASS", workflows)

    def test_no_executable_relation_alias_a(self):
        executable = re.sub(r"--[^\n]*", "", self.sql)
        executable = re.sub(r"'(?:''|[^'])*'", "", executable, flags=re.DOTALL)
        self.assertNotRegex(executable.lower(), r"(?:\bfrom\s+a\b|\bjoin\s+a\b|\bas\s+a\b|\ba\.)")


if __name__ == "__main__":
    unittest.main()
