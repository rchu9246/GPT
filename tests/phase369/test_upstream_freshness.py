import unittest
from automation.v92.phase369_upstream_freshness_diagnostic import assess


class FreshnessTests(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(assess("", "2026-11-05")["status"], "BLOCKED_MISSING_UPSTREAM")

    def test_stale(self):
        result = assess("2026-09-11", "2026-11-05")
        self.assertEqual(result["status"], "BLOCKED_STALE_UPSTREAM")
        self.assertFalse(result["safe_to_run_phase369"])

    def test_future_mismatch(self):
        self.assertEqual(assess("2026-11-06", "2026-11-05")["status"], "BLOCKED_STALE_UPSTREAM")

    def test_invalid_date(self):
        self.assertEqual(assess("bad-date", "2026-11-05")["status"], "BLOCKED_INVALID_UPSTREAM_DATE")

    def test_matching_date_is_not_approval(self):
        result = assess("2026-11-05", "2026-11-05")
        self.assertEqual(result["status"], "DATE_MATCH_ONLY")
        self.assertFalse(result["safe_to_run_phase369"])


if __name__ == "__main__":
    unittest.main()
