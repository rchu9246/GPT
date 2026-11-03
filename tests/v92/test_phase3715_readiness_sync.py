import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def module(phase):
    path = next((ROOT / "automation/v92").glob("paper_trading_phase" + phase + "_production*.py"))
    spec = importlib.util.spec_from_file_location("p" + phase, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class ReadinessSyncTests(unittest.TestCase):
    def ledger(self, n=3):
        return [dict(cycle_date=f"2026-08-{24+i:02}", valid_cycle=True, blocked_cycle=False,
                     runtime_supervision_pass=True, paper_only_boundary_pass=True) for i in range(n)]

    def counts(self, rows):
        mod = module("375")
        pages = [io.BytesIO(json.dumps(rows).encode()), io.BytesIO(b"[]")]
        with patch.object(mod, "SUPABASE_URL", "https://example.invalid"), patch.object(mod, "SUPABASE_KEY", "test"), patch.object(mod.urllib.request, "urlopen", side_effect=pages) as request:
            result = mod.canonical_qualification_counts()
            self.assertIn("strategy_version=eq.V9.1", request.call_args_list[0].args[0].full_url)
            self.assertIn("offset=3", request.call_args_list[1].args[0].full_url)
            return result

    def test_persisted_cycles_not_single_run_artifact(self):
        self.assertEqual(self.counts(self.ledger())["valid"], 3)

    def test_duplicates_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            self.counts([self.ledger()[0]] * 3)

    def test_missing_safety_fails_closed(self):
        rows = self.ledger(); del rows[0]["paper_only_boundary_pass"]
        with self.assertRaisesRegex(ValueError, "SAFETY"):
            self.counts(rows)

    def test_boundary_failure_blocks(self):
        rows = self.ledger(); rows[0]["paper_only_boundary_pass"] = False
        self.assertEqual(self.counts(rows)["blocked"], 1)

    def run_gate(self, phase, readiness, observed=53):
        mod = module(phase)
        q = dict(observed=observed, valid=observed, blocked=0, distinct_cycle_dates=observed,
                 duplicate_rows=0, latest_cycle_date="2026-11-03", runtime_supervision_pass=True,
                 paper_only_boundary_pass=True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(mod, "ART_DIR", Path(tmp)), patch.object(mod, "RESULT_PATH", Path(tmp)/"result.json"), patch.object(mod, "SUMMARY_PATH", Path(tmp)/"summary.md"), patch.object(mod, "qualification_snapshot", return_value=q), patch.object(mod, "readiness_snapshot", return_value=readiness), patch("sys.stdout", new_callable=io.StringIO):
            code = mod.main()
            return code, json.loads((Path(tmp)/"result.json").read_text())

    def ready(self, n=53):
        return dict(promotion_ready=True, observed_cycles=n, valid_cycles=n, blocked_cycles=0,
                    runtime_supervision_pass=True, paper_only_boundary_pass=True,
                    broker_order_submission_enabled=False, real_money_trading_enabled=False,
                    historical_rewrite_allowed=False)

    def test_52_to_53_remains_blocked(self):
        for phase in ("3714", "3715"):
            r = self.ready(52); r["promotion_ready"] = False
            code, result = self.run_gate(phase, r)
            self.assertEqual(code, 1)
            self.assertIn("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER", result["blockers"])

    def test_ready_does_not_claim_execution(self):
        code, result = self.run_gate("3715", self.ready())
        self.assertEqual(code, 0)
        self.assertTrue(result["first_live_paper_session_ready"])
        self.assertFalse(result["runtime_active"])
        self.assertTrue(result["validation_only"])

    def test_missing_or_enabled_lock_never_qualifies(self):
        for phase in ("3714", "3715"):
            for value in (None, True, "false"):
                r = self.ready(); r["broker_order_submission_enabled"] = value
                self.assertEqual(self.run_gate(phase, r)[0], 1)

    def test_missing_readiness_blocks(self):
        self.assertEqual(self.run_gate("3715", {})[0], 1)

    def test_readiness_safety_failure_blocks(self):
        r = self.ready(); r["runtime_supervision_pass"] = False
        self.assertEqual(self.run_gate("3715", r)[0], 1)

    def test_current_runtime_failure_cannot_be_overridden_by_ledger(self):
        mod = module("375")
        counts = dict(observed=53, valid=53, blocked=0, unknown=0)
        sources = [("activation", [{"state": "ACTIVE"}], []),
                   ("master", [{"state": "READY"}], []),
                   ("runtime", [{"state": "HALTED"}], []),
                   (None, [], [])]
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                with patch.object(mod, "SUPABASE_URL", "https://example.invalid"), patch.object(mod, "SUPABASE_KEY", "test"), patch.object(mod, "inspect", side_effect=sources), patch.object(mod, "runtime_supervision_reconstruct", return_value=(False, "HALTED", "FAIL")), patch.object(mod, "canonical_qualification_counts", return_value=counts), patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(mod.main(), 1)
                result = json.loads(Path("artifacts/phase375/phase375_result.json").read_text())
                self.assertFalse(result["qualified"])
                self.assertIn("RUNTIME_SUPERVISION_NOT_READY", result["blockers"])
            finally:
                os.chdir(previous)

    def test_reconciliation_uses_fresh_qualified_chain_and_blocks_race(self):
        mod = module("379")
        canonical = dict(observed=53, valid=53, blocked=0, runtime_supervision_pass=True, paper_only_boundary_pass=True)
        p375 = dict(state="MULTI_CYCLE_STABILITY_QUALIFIED", qualified=True, operational=True,
                    evidence_counts=dict(observed=53, valid=53, blocked=0))
        p376 = dict(state="PRODUCTION_PAPER_PROMOTION_AUTHORIZED", promotion_authorized=True, operational=True)
        for race in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                previous = os.getcwd()
                try:
                    os.chdir(tmp)
                    counts = dict(canonical)
                    if race:
                        counts.update(observed=54, valid=54)
                    with patch.object(mod, "load_json", side_effect=[p375, p376]), patch.object(mod, "canonical_evidence_counts", return_value=counts), patch.object(mod, "request") as request, patch("sys.stdout", new_callable=io.StringIO):
                        code = mod.main()
                    result = json.loads(Path("artifacts/phase379/phase379_result.json").read_text())
                    self.assertEqual(result["promotion_ready"], not race)
                    self.assertEqual(code, int(race))
                    self.assertEqual(request.call_args.args[0], "POST")
                    self.assertIn("paper_production_promotion_readiness_v92", request.call_args.args[1])
                finally:
                    os.chdir(previous)

    def test_workflows_recompute_before_validate(self):
        for phase in ("3714", "3715"):
            s = next((ROOT/".github/workflows").glob("*phase"+phase+"-*.yml")).read_text()
            indexes = [s.index("python automation/v92/paper_trading_phase"+n+"_") for n in ("375", "376", "379")]
            self.assertEqual(indexes, sorted(indexes))
            self.assertIn("production-paper-readiness-reconciliation", s)

if __name__ == "__main__":
    unittest.main()
