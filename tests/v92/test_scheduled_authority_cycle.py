"""Offline scheduled graph regression: real handoff and subprocess wiring, shared DB."""
import copy
from contextlib import redirect_stdout
from decimal import Decimal
import importlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import test_canonical_batch_authority as contract
import test_phase353_authority_handoff as event_tests
import phase353_authority_handoff as handoff

with patch.object(Path, "mkdir"):
    execution = importlib.import_module("paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine")
    settlement = importlib.import_module("paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine")
sizing = contract.sizing


class ScheduledCycleTests(unittest.TestCase):
    def setUp(self):
        self.events = event_tests.HandoffTests()
        self.events.setUp()
        self.addCleanup(self.events.doCleanups)
        self.contract = self.events.contract
        self.rows = {sizing.PLAN_TABLE: [], sizing.ITEM_TABLE: []}
        self.writes = []
        self.tuples = []
        self.emitted = {}

    def read(self, table, params):
        if table not in self.rows:
            return self.contract.database(table, params)
        params = dict(params)
        rows = copy.deepcopy(self.rows[table])
        for key in ("portfolio_id", "plan_date", "plan_id"):
            if key in params:
                rows = [r for r in rows if r[key] == params[key][3:]]
        offset = int(params.get("offset", "0"))
        return rows[offset:offset + 500]

    def insert(self, table, rows):
        self.writes.append(table)
        values = copy.deepcopy(rows)
        if table == sizing.ITEM_TABLE:
            for row in values:
                for key in ("score", "real_market_price", "paper_quantity", "estimated_notional", "raw_target_capital"):
                    row[key] = Decimal(row[key])
        self.rows[table].extend(values)

    def record_output(self, path, text, **kwargs):
        self.emitted[path.name] = text
        return len(text)

    def execute_sizing_chain(self):
        governance = dict(status="PASS", risk_state="NORMAL", governance_date=contract.DAY,
                          risk_reduction_factor=1, new_paper_entries_authorized=True, paper_halt=False,
                          fail_closed_policy=True)
        for flag in ("synthetic_market_data", "synthetic_signals", "fake_prices_allowed", "broker_api_used",
                     "broker_credentials_used", "broker_order_submission_enabled", "real_money_trading_enabled",
                     "live_money_release_authorized"):
            governance[flag] = False
        ledger = dict(ledger_date=contract.DAY, nav=1000000, cash=1000000, market_value=0)

        def subprocess_boundary(argv, **kwargs):
            # Execute actual 355 and 354 run_upstream environment propagation.
            # Only the OS process boundary is replaced; 353 main/allocator/persistence run.
            env = kwargs["env"]
            phase = "354" if Path(argv[1]) == settlement.UPSTREAM else "353"
            self.tuples.append((phase, env["PHASE353_PRODUCER_RUN_ID"], env["PHASE353_PRODUCER_RUN_ATTEMPT"]))
            with patch.dict(os.environ, env):
                if phase == "354":
                    execution.run_upstream()
                else:
                    self.assertEqual(sizing.main(), 0)
            return Mock(returncode=0, stdout="", stderr="")

        with self.contract.artifact_mock(), patch.object(sizing, "rest_get", side_effect=self.read), \
                patch.object(sizing, "rest_insert_only", side_effect=self.insert), \
                patch.object(sizing, "latest_ledger", return_value=ledger), \
                patch.object(sizing, "open_positions", return_value=[]), \
                patch.object(sizing, "run_upstream", return_value=(0, governance)), \
                patch.object(Path, "write_text", autospec=True, side_effect=self.record_output), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(execution, "load_json", return_value={"status": "PASS"}), \
                patch.object(settlement, "load_json", return_value={"status": "PASS"}), \
                patch.object(execution.subprocess, "run", side_effect=subprocess_boundary), \
                patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}), redirect_stdout(io.StringIO()):
            self.tuples.append(("355", os.environ["PHASE353_PRODUCER_RUN_ID"], os.environ["PHASE353_PRODUCER_RUN_ATTEMPT"]))
            settlement.run_upstream()
        return json.loads(self.emitted[sizing.RESULT_JSON.name])

    def test_whole_scheduled_graph_and_completion_replay_share_one_authority(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(handoff.requests, "post", return_value=Mock(status_code=204)) as post:
            handoff.request_producer("353")
            handoff.verify_scheduled_ownership("354")
            handoff.verify_scheduled_ownership("355")
            post.assert_called_once()
            self.assertEqual(post.call_args.kwargs["json"]["inputs"], {"handoff_consumer": "368"})

        results = []
        def delivery(workflow, inputs):
            self.assertEqual(workflow, handoff.CONSUMERS["368"])
            self.assertEqual(inputs, {"producer_run_id": "123", "producer_run_attempt": "2", "business_date": contract.DAY})
            results.append(self.execute_sizing_chain())

        for _ in range(2):
            with self.contract.artifact_mock(mutate_result=lambda r: r.update(handoff_consumer="368")), \
                    patch.object(handoff, "dispatch", side_effect=delivery):
                handoff.complete_handoff(self.events.event)
        self.assertEqual(self.tuples, [(phase, "123", "2") for _ in range(2) for phase in ("355", "354", "353")])
        self.assertEqual(results[0]["plan_id"], results[1]["plan_id"])
        self.assertEqual(results[0]["canonical_authority"], results[1]["canonical_authority"])
        self.assertEqual(self.writes, [sizing.PLAN_TABLE, sizing.ITEM_TABLE])
        self.assertEqual(len(self.rows[sizing.PLAN_TABLE]), 1)
        self.assertEqual(len(self.rows[sizing.ITEM_TABLE]), 2)
        self.assertEqual(results[1]["items"][0]["raw_target_capital"], str(self.rows[sizing.ITEM_TABLE][0]["raw_target_capital"]))

    def test_later_schedules_and_owner_retry_cannot_request_another_producer(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}), patch.object(handoff, "dispatch") as dispatch:
            for phase in ("354", "355"):
                with self.assertRaisesRegex(RuntimeError, "INVALID_SCHEDULED_AUTHORITY_REQUEST"):
                    handoff.request_producer(phase)
            with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "2"}):
                with self.assertRaisesRegex(RuntimeError, "OWNER_RETRY"):
                    handoff.request_producer("353")
            dispatch.assert_not_called()

    def test_new_run_or_attempt_is_distinct_and_same_day_fails_closed(self):
        plan, items = self.contract.plan()
        with patch.object(sizing, "rest_get", side_effect=self.read), patch.object(sizing, "rest_insert_only", side_effect=self.insert):
            sizing.persist_plan(plan, items)
            old = self.contract.a
            for field, value in (("producer_run_id", "124"), ("producer_run_attempt", "3")):
                context = {k: old[k] for k in ("repository", "workflow", "producer_run_id", "producer_run_attempt", "producer_commit_sha")}
                context[field] = value
                e = self.contract.e
                self.contract.a, _ = contract.producer.build_authority(contract.BATCH, contract.DAY,
                    e["signals"], e["prices"], e["signal_adapter"], e["price_adapter"], e["bridge"], context)
                self.assertNotEqual(self.contract.a["authority_hash"], old["authority_hash"])
                new_plan, new_items = self.contract.plan()
                with self.assertRaisesRegex(RuntimeError, "SAME_DAY_PLAN_AUTHORITY_CONFLICT"):
                    sizing.persist_plan(new_plan, new_items)
        self.assertEqual(self.writes, [sizing.PLAN_TABLE, sizing.ITEM_TABLE])

    def test_retry_same_tuple_uses_existing_plan_without_writes(self):
        self.execute_sizing_chain()
        first_writes = list(self.writes)
        self.execute_sizing_chain()
        self.assertEqual(self.writes, first_writes)

    def test_old_incomplete_date_does_not_match_future_plan_date(self):
        self.rows[sizing.PLAN_TABLE] = [{"portfolio_id": sizing.PORTFOLIO_ID,
            "plan_date": "2026-09-15", "plan_id": "legacy-incomplete"}]
        plan, items = self.contract.plan()
        with patch.object(sizing, "rest_get", side_effect=self.read), patch.object(sizing, "rest_insert_only", side_effect=self.insert):
            sizing.persist_plan(plan, items)
        self.assertEqual(len(self.rows[sizing.PLAN_TABLE]), 2)
        self.assertEqual(self.rows[sizing.PLAN_TABLE][0]["plan_id"], "legacy-incomplete")

    def test_valid_producer_rerun_propagates_new_attempt_artifact(self):
        e = self.contract.e
        context = {k: self.contract.a[k] for k in ("repository", "workflow", "producer_run_id", "producer_run_attempt", "producer_commit_sha")}
        context["producer_run_attempt"] = "3"
        self.contract.a, _ = contract.producer.build_authority(contract.BATCH, contract.DAY,
            e["signals"], e["prices"], e["signal_adapter"], e["price_adapter"], e["bridge"], context)
        event = copy.deepcopy(self.events.event)
        event["workflow_run"]["run_attempt"] = 3
        with self.contract.artifact_mock(
                mutate_run=lambda r: r.update(run_attempt=3),
                mutate_artifact=lambda a: a.update(name="phase348451-market-source-discovery-123-attempt-3"),
                mutate_result=lambda r: r.update(handoff_consumer="355")) as get, \
                patch.object(handoff, "dispatch") as dispatch:
            fixture_get = get.side_effect
            def exact_attempt_get(url, **kwargs):
                if "/attempts/" in url:
                    self.assertTrue(url.endswith("/runs/123/attempts/3"))
                    url = url.replace("/attempts/3", "/attempts/2")
                return fixture_get(url, **kwargs)
            get.side_effect = exact_attempt_get
            handoff.complete_handoff(event)
            dispatch.assert_called_once_with(handoff.CONSUMERS["355"],
                {"producer_run_id": "123", "producer_run_attempt": "3"})

    def test_changed_inputs_on_same_authority_retry_fail_closed_without_writes(self):
        plan, items = self.contract.plan()
        with patch.object(sizing, "rest_get", side_effect=self.read), patch.object(sizing, "rest_insert_only", side_effect=self.insert):
            sizing.persist_plan(plan, items)
            changed = copy.deepcopy(plan)
            changed["evidence_sha256"] = "changed-ledger-or-governance"
            with self.assertRaisesRegex(RuntimeError, "SAME_AUTHORITY_PLAN_CONTENT_CONFLICT"):
                sizing.persist_plan(changed, items)
        self.assertEqual(self.writes, [sizing.PLAN_TABLE, sizing.ITEM_TABLE])

    def test_manual_dispatch_cannot_enter_scheduled_request_or_observer(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch"}), patch.object(handoff, "dispatch") as dispatch:
            with self.assertRaisesRegex(RuntimeError, "INVALID_SCHEDULED"):
                handoff.request_producer("353")
            with self.assertRaisesRegex(RuntimeError, "INVALID_SCHEDULED"):
                handoff.verify_scheduled_ownership("355")
            dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
