"""Offline event -> exact artifact -> explicit dispatch tests; no live I/O."""
import copy
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "automation/v92"))
import phase353_authority_handoff as handoff
import test_canonical_batch_authority as contract_tests

SHA, producer = contract_tests.SHA, contract_tests.producer


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract_tests.AuthorityTests()
        self.contract.setUp()
        self.addCleanup(self.contract.doCleanups)
        self.event = dict(action="completed", repository={"full_name": producer.AUTHORITY_REPOSITORY},
                          workflow_run=dict(id=123, run_attempt=2, head_sha=SHA, head_branch="main",
                                            head_repository={"full_name": producer.AUTHORITY_REPOSITORY},
                                            path=producer.AUTHORITY_WORKFLOW, status="completed",
                                            conclusion="success", event="workflow_dispatch"))
        env = patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run"})
        env.start()
        self.addCleanup(env.stop)

    def artifact(self, **kwargs):
        return self.contract.artifact_mock(mutate_result=lambda r: r.update(handoff_consumer="353"), **kwargs)

    def test_scheduled_request_only_dispatches_dedicated_producer(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(handoff.requests, "post", return_value=Mock(status_code=204)) as post:
            handoff.request_producer("353")
        self.assertTrue(post.call_args.args[0].endswith(producer.AUTHORITY_WORKFLOW.split("/")[-1] + "/dispatches"))
        self.assertEqual(post.call_args.kwargs["json"], {"ref": "main", "inputs": {"handoff_consumer": "368"}})

    def test_completed_scheduled_producer_passes_exact_tuple_without_dispatch_inputs(self):
        with patch.dict(os.environ, {"PHASE353_PRODUCER_RUN_ID": "", "PHASE353_PRODUCER_RUN_ATTEMPT": ""}), \
                self.artifact(), patch.object(handoff.requests, "post", return_value=Mock(status_code=204)) as post:
            handoff.complete_handoff(self.event)
        self.assertEqual(post.call_args.kwargs["json"], {
            "ref": "main", "inputs": {"producer_run_id": "123", "producer_run_attempt": "2"}})
        self.assertTrue(post.call_args.args[0].endswith(handoff.CONSUMERS["353"] + "/dispatches"))

    def test_downstream_targets_preserve_same_producer_identity(self):
        for target in ("354", "355"):
            with self.subTest(target=target), self.contract.artifact_mock(
                    mutate_result=lambda r: r.update(handoff_consumer=target)), patch.object(handoff, "dispatch") as dispatch:
                handoff.complete_handoff(self.event)
                dispatch.assert_called_once_with(handoff.CONSUMERS[target],
                                                 {"producer_run_id": "123", "producer_run_attempt": "2"})

    def test_controller_handoff_uses_exact_authority_trade_date(self):
        with self.contract.artifact_mock(mutate_result=lambda r: r.update(handoff_consumer="368")), \
                patch.object(handoff, "dispatch") as dispatch:
            handoff.complete_handoff(self.event)
        dispatch.assert_called_once_with(handoff.CONSUMERS["368"],
            {"producer_run_id": "123", "producer_run_attempt": "2", "business_date": contract_tests.DAY})

    def test_wrong_workflow_branch_repository_state_or_attempt_rejected(self):
        for changes in ({"path": "other.yml"}, {"head_branch": "untrusted"},
                        {"head_repository": {"full_name": "other/repo"}}, {"conclusion": "failure"},
                        {"status": "in_progress"}, {"run_attempt": 0}, {"id": True}):
            event = copy.deepcopy(self.event)
            event["workflow_run"].update(changes)
            with self.subTest(changes=changes), patch.object(handoff, "dispatch") as dispatch:
                with self.assertRaises(RuntimeError):
                    handoff.complete_handoff(event)
                dispatch.assert_not_called()

    def test_event_sha_must_match_verified_producer_sha(self):
        self.event["workflow_run"]["head_sha"] = "b" * 40
        with self.artifact(), patch.object(handoff, "dispatch") as dispatch:
            with self.assertRaisesRegex(RuntimeError, "SHA_MISMATCH"):
                handoff.complete_handoff(self.event)
            dispatch.assert_not_called()

    def test_attempt_artifact_digest_and_expiration_guards_precede_dispatch(self):
        cases = [dict(mutate_run=lambda r: r.update(run_attempt=3)),
                 dict(mutate_run=lambda r: r.update(path="other.yml")),
                 dict(mutate_run=lambda r: r.update(head_sha="b" * 40)),
                 dict(artifact_count=0), dict(artifact_count=2),
                 dict(mutate_artifact=lambda a: a.update(expired=True)),
                 dict(mutate_artifact=lambda a: a.update(digest="bad"))]
        for case in cases:
            with self.subTest(case=case), self.artifact(**case), patch.object(handoff, "dispatch") as dispatch:
                with self.assertRaises(RuntimeError):
                    handoff.complete_handoff(self.event)
                dispatch.assert_not_called()

    def test_unapproved_consumer_cannot_be_dispatched(self):
        with self.contract.artifact_mock(mutate_result=lambda r: r.update(handoff_consumer="369")), \
                patch.object(handoff, "dispatch") as dispatch:
            with self.assertRaisesRegex(RuntimeError, "HANDOFF_CONSUMER"):
                handoff.complete_handoff(self.event)
            dispatch.assert_not_called()

    def test_manual_dispatch_explicit_tuple_still_validates(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "b" * 40}), \
                self.artifact():
            result = handoff.load_explicit_producer_result()
        self.assertEqual(result["canonical_authority"]["producer_commit_sha"], SHA)

    def test_producer_main_embeds_requested_handoff_in_hashed_result(self):
        evidence = self.contract.e
        snapshot = dict(active_stocks=2, stocks_with_history=2, rows_scanned=2,
                        latest_market_date=contract_tests.DAY, per_symbol=[])
        capture = dict(signal_engine_exit_code=0, signal_engine_stocks_scanned=2,
                       reported_signals_eligible=2, top_symbol="2330", top_score=90)
        env = {"PHASE348451_HANDOFF_CONSUMER": "354", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
               "GITHUB_SHA": SHA, "GITHUB_WORKFLOW_REF": producer.AUTHORITY_REPOSITORY + "/" + producer.AUTHORITY_WORKFLOW + "@refs/heads/main"}

        def adapter(path):
            return evidence["signal_adapter"] if path == producer.CANONICAL_SIGNALS else evidence["price_adapter"]

        with patch.dict(os.environ, env), patch.object(sys, "argv", ["producer", "--approver", "offline"]), \
                patch.object(producer, "run_gate", return_value={"runtime_execution_gate": "OPEN"}), \
                patch.object(producer, "discover_best_market_source", return_value=([{}], "fixture", [])), \
                patch.object(producer, "discover_active_symbols", return_value=(["2330", "2454"], "fixture")), \
                patch.object(producer, "build_market_snapshot", return_value=snapshot), \
                patch.object(producer, "execute_signal_engine", return_value=(evidence["signals"], capture)), \
                patch.object(producer, "latest_prices_for_signals", return_value=evidence["prices"]), \
                patch.object(producer, "persist_canonical", return_value=(contract_tests.BATCH, evidence["signals"], evidence["prices"])), \
                patch.object(producer, "write_phase348_adapters"), \
                patch.object(producer, "run_phase348", return_value=evidence["bridge"]), \
                patch.object(producer, "load_json", side_effect=adapter), \
                patch.object(producer, "dump_json") as dump, \
                patch.object(Path, "write_text"), redirect_stdout(io.StringIO()):
            self.assertEqual(producer.main(), 0)
        result = dump.call_args.args[1]
        self.assertEqual(result["handoff_consumer"], "354")
        self.assertEqual(result["canonical_authority"], self.contract.a)
        self.assertEqual(result["evidence_sha256"], producer.stable_hash({k: v for k, v in result.items() if k != "evidence_sha256"}))

    def test_workflow_wiring_preserves_cron_and_requires_manual_authority(self):
        root = Path(__file__).resolve().parents[2] / ".github/workflows"
        for phase, cron in (("353", "35 9 * * 1-5"), ("354", "50 9 * * 1-5"), ("355", "5 10 * * 1-5")):
            text = (root / handoff.CONSUMERS[phase]).read_text(encoding="utf-8-sig")
            self.assertIn(f'cron: "{cron}"', text)
            self.assertIn("if: github.event_name == 'schedule'", text)
            self.assertIn("if: github.event_name != 'schedule'", text)
            self.assertIn(f"{'request' if phase == '353' else 'ownership'} --consumer {phase}", text)
        for phase in ("353", "354", "355", "360", "361", "362", "363", "364", "368"):
            text = next(root.glob(f"*phase{phase}-production-*.yml")).read_text(encoding="utf-8-sig")
            self.assertIn("PHASE353_PRODUCER_RUN_ID: ${{ inputs.producer_run_id }}", text)
            self.assertIn("PHASE353_PRODUCER_RUN_ATTEMPT: ${{ inputs.producer_run_attempt }}", text)
            self.assertIn("GH_TOKEN: ${{ github.token }}", text)
            self.assertIn("actions: read", text)
            self.assertIn("phase353_authority_handoff.py validate", text)
        completion = (root / "gpt-quant-v92-paper-trading-phase353-producer-completion-handoff.yml").read_text()
        self.assertIn("types: [completed]", completion)
        self.assertIn("branches: [main]", completion)
        self.assertIn("workflow_run.conclusion == 'success'", completion)


if __name__ == "__main__":
    unittest.main()
