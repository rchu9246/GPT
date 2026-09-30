from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / ".github/supabase/validation/phase353_handoff_receipt_full_live_diagnostic.sql").read_text(encoding="utf-8")

class Phase353FullLiveDiagnosticTests(unittest.TestCase):
    def test_unique_live_diag_identity(self):
        values = re.findall(r"'(VALIDATION_ONLY_PHASE353[^']*)'", SQL)
        self.assertTrue(values)
        self.assertTrue(all(value.startswith("VALIDATION_ONLY_PHASE353_LIVE_DIAG_") for value in values))

    def test_catalog_differences_have_exception_checkpoints(self):
        for number, name in enumerate(("TABLE", "COLUMNS", "UNIQUE_CONSTRAINT", "RLS",
                                       "RPC_EXISTENCE", "COMPLETION_RPC",
                                       "UNTRUSTED_PRIVILEGES", "SERVICE_PRIVILEGES"), 1):
            self.assertIn(f"PHASE353_LIVE_DIAG_L{number:02}_{name}", SQL)
        blocks = re.findall(r"do \$checkpoint\$(.*?)\$checkpoint\$;", SQL, re.I | re.S)
        self.assertGreaterEqual(len(blocks), 22)
        self.assertTrue(all("exception when others" in block.lower()
                            and "sqlstate, sqlerrm" in block.lower() for block in blocks))

    def test_self_contained_temporary_state(self):
        lower = SQL.lower()
        self.assertIn("create or replace function pg_temp.phase353_live_diag_assert", lower)
        self.assertIn("create temporary table phase353_live_diagnostic_results", lower)
        self.assertIn("on commit preserve rows", lower)
        self.assertGreaterEqual(lower.count("begin;"), 2)
        self.assertGreaterEqual(lower.count("commit;"), 2)

    def test_exact_cleanup_and_no_persistent_table(self):
        lower = SQL.lower()
        self.assertGreaterEqual(lower.count("delete from public.phase353_handoff_receipts"), 2)
        self.assertNotRegex(lower, r"create\s+table\s+(?:public\.)?phase353_live_diagnostic")
        self.assertNotIn("truncate", lower)

    def test_no_financial_or_workflow_surface(self):
        for forbidden in ("paper_", "trade_orders", "positions", "portfolio", "broker",
                          "workflow_dispatch", "api.github.com"):
            self.assertNotIn(forbidden, SQL.lower())

    def test_pass_and_failure_formats(self):
        self.assertIn("PHASE353_FULL_LIVE_DIAGNOSTIC_PASS", SQL)
        self.assertRegex(SQL, r"PHASE353_LIVE_DIAG_L\d{2}_[A-Z_]+ \[%\] %")

if __name__ == "__main__":
    unittest.main()
