"""Offline producer/artifact/consumer contract tests; all I/O is mocked."""
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "automation/v92"))
producer = importlib.import_module("paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix")
sizing = importlib.import_module("paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine")
DAY = "2026-09-16"
BATCH = "P348451-fixture"
SHA = "a" * 40


def fixture():
    signals, prices = [], []
    for symbol, score in (("2330", 90), ("2454", 80)):
        common = dict(symbol=symbol, trade_date=DAY, canonical_batch_id=BATCH,
                      source_table="real_fixture", source_row_hash=hashlib.sha256(symbol.encode()).hexdigest(),
                      synthetic_evidence=False)
        signals.append(dict(common, strategy_version="V9.1", signal="BUY", total_score=score))
        prices.append(dict(common, close=100))
    sig_adapter, px_adapter = producer.adapter_payloads(signals, prices)
    bridge = dict(status="PASS", strategy_version="V9.1", runtime_execution_gate="OPEN",
                  execution_state="REAL_CANONICAL_EVIDENCE_EXECUTED",
                  canonical_signal_source=producer.SIGNAL_ADAPTER_PATH,
                  canonical_signals_found=2, signals_with_real_market_price=2,
                  fail_closed_policy=True, errors=[], canonical_candidates=[])
    for flag in ("synthetic_fallback_allowed", "synthetic_evidence_present", "broker_api_used",
                 "broker_credentials_used", "broker_order_submission_enabled", "real_money_trading_enabled",
                 "live_money_release_authorized", "fail_closed_triggered"):
        bridge[flag] = False
    for signal in signals:
        bridge["canonical_candidates"].append(dict(
            symbol=signal["symbol"], trade_date=DAY, strategy_version="V9.1", signal="BUY",
            score=signal["total_score"], market_price=100, synthetic_evidence=False,
            signal_source=producer.SIGNAL_ADAPTER_PATH, market_price_source=producer.PRICE_ADAPTER_PATH))
    bridge["evidence_sha256"] = producer.stable_hash(bridge)
    context = dict(repository=producer.AUTHORITY_REPOSITORY, workflow=producer.AUTHORITY_WORKFLOW,
                   producer_run_id="123", producer_run_attempt="2", producer_commit_sha=SHA)
    authority, evidence = producer.build_authority(BATCH, DAY, signals, prices, sig_adapter, px_adapter, bridge, context)
    return authority, evidence


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.a, self.e = fixture()
        env = patch.dict(os.environ, {"GITHUB_REPOSITORY": producer.AUTHORITY_REPOSITORY,
                                      "PHASE353_PRODUCER_RUN_ID": "123", "PHASE353_PRODUCER_RUN_ATTEMPT": "2",
                                      "GH_TOKEN": "offline-token"})
        env.start()
        self.addCleanup(env.stop)
        # Unexpected live network or subprocess execution is a test failure.
        for target in ("requests.sessions.Session.request", "subprocess.run"):
            guard = patch(target, side_effect=AssertionError("Production I/O forbidden in offline tests"))
            guard.start()
            self.addCleanup(guard.stop)

    def database(self, table, params):
        params = dict(params)
        self.assertEqual(params["canonical_batch_id"], "eq." + BATCH)
        self.assertEqual(params["trade_date"], "eq." + DAY)
        self.assertNotIn("total_score", params.get("order", ""))
        if table == sizing.SIGNALS_TABLE:
            self.assertEqual(params["strategy_version"], "eq.V9.1")
            rows = self.e["signals"]
        elif table == sizing.PRICES_TABLE:
            rows = [r for r in self.e["prices"] if r["symbol"] == params["symbol"][3:]]
        else:
            self.fail("Unexpected table: " + table)
        # Simulate a server page cap smaller than our requested limit.
        offset = int(params["offset"])
        return copy.deepcopy(rows[offset:offset + 1])

    def plan(self):
        governance = dict(risk_state="NORMAL", risk_reduction_factor=1, governance_date=DAY,
                          new_paper_entries_authorized=True, paper_halt=False)
        ledger = dict(ledger_date=DAY, nav=1000000, cash=1000000, market_value=0)
        with patch.object(sizing, "rest_get", side_effect=self.database):
            return sizing.build_plan(governance, ledger, [], self.a)

    def artifact_mock(self, mutate_run=None, mutate_artifact=None, mutate_result=None, artifact_count=1):
        result = dict(status="PASS", version="3.4.8.4.5.1", canonical_batch_id=BATCH,
                      strategy_version="V9.1", execution_state=self.a["bridge_execution_state"],
                      canonical_authority=self.a, canonical_authority_evidence=self.e)
        if mutate_result:
            mutate_result(result)
        result["evidence_sha256"] = producer.stable_hash(result)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("phase348451_output/phase348451_signal_input_contract_fix.json", json.dumps(result))
        content = buf.getvalue()
        run = dict(id=123, run_attempt=2, repository={"full_name": producer.AUTHORITY_REPOSITORY},
                   head_repository={"full_name": producer.AUTHORITY_REPOSITORY},
                   path=producer.AUTHORITY_WORKFLOW + "@main", head_sha=SHA, status="completed", conclusion="success")
        artifact = dict(id=456, name="phase348451-market-source-discovery-123-attempt-2", expired=False,
                        digest="sha256:" + hashlib.sha256(content).hexdigest(), workflow_run={"id": 123, "head_sha": SHA})
        if mutate_run:
            mutate_run(run)
        if mutate_artifact:
            mutate_artifact(artifact)

        def get(url, **kwargs):
            if url.endswith("/actions/runs/123/attempts/2"):
                return Mock(status_code=200, json=lambda: run)
            if url.endswith("/actions/runs/123/artifacts"):
                return Mock(status_code=200, json=lambda: {"total_count": artifact_count, "artifacts": [artifact] * artifact_count})
            if url.endswith("/actions/artifacts/456/zip"):
                return Mock(status_code=200, content=content)
            self.fail("Non-explicit authority lookup: " + url)
        return patch.object(sizing.requests, "get", side_effect=get)

    def test_valid_explicit_authority_and_exact_artifact(self):
        with self.artifact_mock():
            self.assertEqual(sizing.load_explicit_authority(), self.a)

    def test_missing_reference_fails_before_any_upstream_or_database(self):
        for name in ("PHASE353_PRODUCER_RUN_ID", "PHASE353_PRODUCER_RUN_ATTEMPT"):
            with self.subTest(name=name), patch.dict(os.environ, {name: ""}), \
                    patch.object(sizing, "rest_get") as read, patch.object(sizing, "run_upstream") as upstream:
                with self.assertRaisesRegex(RuntimeError, "EXPLICIT_PRODUCER"):
                    sizing.main()
                read.assert_not_called()
                upstream.assert_not_called()

    def test_wrong_run_attempt_repository_workflow_or_commit(self):
        mutations = [lambda r: r.update(run_attempt=3), lambda r: r.update(id=124),
                     lambda r: r.update(repository={"full_name": "other/GPT"}),
                     lambda r: r.update(path=".github/workflows/other.yml"), lambda r: r.update(head_sha="b" * 40)]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.artifact_mock(mutate_run=mutate):
                with self.assertRaises(RuntimeError):
                    sizing.load_explicit_authority()

    def test_invalid_authority_hash_schema_or_strategy(self):
        for key, value in (("authority_hash", "bad"), ("authority_schema_version", 99), ("strategy_version", "V9.2")):
            with self.subTest(key=key), self.artifact_mock(mutate_result=lambda r: r["canonical_authority"].update({key: value})):
                with self.assertRaises(RuntimeError):
                    sizing.load_explicit_authority()
            self.a, self.e = fixture()

    def test_missing_expired_wrong_attempt_or_digest_artifact(self):
        for fields in ({"expired": True}, {"name": "phase348451-market-source-discovery-123-attempt-1"}, {"digest": "bad"}):
            with self.subTest(fields=fields), self.artifact_mock(mutate_artifact=lambda a: a.update(fields)):
                with self.assertRaises(RuntimeError):
                    sizing.load_explicit_authority()

    def test_same_batch_signal_price_success_and_full_pagination(self):
        with patch.object(sizing, "rest_get", side_effect=self.database) as read:
            signals, prices = sizing.same_batch_inputs(self.a, DAY)
        self.assertEqual(len(signals), 2)
        self.assertEqual(set(prices), {"2330", "2454"})
        self.assertGreater(read.call_count, 3)

    def test_wrong_date_before_queries(self):
        with patch.object(sizing, "rest_get") as read:
            with self.assertRaisesRegex(RuntimeError, "TRADE_DATE"):
                sizing.same_batch_inputs(self.a, "2026-09-15")
            read.assert_not_called()

    def test_missing_and_duplicate_price(self):
        for rows in ([], self.e["prices"] + [dict(self.e["prices"][0], id=999)]):
            with self.subTest(rows=rows):
                saved = self.e["prices"]
                self.e["prices"] = rows
                with patch.object(sizing, "rest_get", side_effect=self.database):
                    with self.assertRaisesRegex(RuntimeError, "EXACTLY_ONE"):
                        sizing.same_batch_inputs(self.a, DAY)
                self.e["prices"] = saved

    def test_cross_batch_wrong_date_symbol_and_invalid_price(self):
        for field, value in (("canonical_batch_id", "other"), ("trade_date", "2026-09-15"),
                             ("close", "NaN"), ("close", "Infinity"), ("close", 0), ("synthetic_evidence", True)):
            with self.subTest(field=field, value=value):
                self.e["prices"][0][field] = value
                with patch.object(sizing, "rest_get", side_effect=self.database):
                    with self.assertRaises(RuntimeError):
                        sizing.same_batch_inputs(self.a, DAY)
                self.a, self.e = fixture()

    def test_duplicate_normalized_signal_before_max_candidates(self):
        duplicate = dict(self.e["signals"][0], symbol=" ２３３０ ", id=987, total_score=1)
        self.e["signals"].append(duplicate)
        with patch.object(sizing, "MAX_CANDIDATES", 1):
            with self.assertRaisesRegex(RuntimeError, "DUPLICATE_NORMALIZED_SYMBOL.*P348451-fixture.*987"):
                self.plan()

    def test_signal_synthetic_wrong_strategy_and_batch(self):
        for key, value in (("synthetic_evidence", True), ("strategy_version", "V9.2"), ("canonical_batch_id", "other")):
            with self.subTest(key=key):
                self.e["signals"][0][key] = value
                with patch.object(sizing, "rest_get", side_effect=self.database):
                    with self.assertRaises(RuntimeError):
                        sizing.same_batch_inputs(self.a, DAY)
                self.a, self.e = fixture()

    def test_bridge_fallback_or_safe_zero_prevents_authority(self):
        for mutate in (lambda b: b.update(execution_state="NO_REAL_MARKET_PRICE_ZERO_ORDERS"),
                       lambda b: b["canonical_candidates"][0].update(market_price_source="market_data/latest_market.json"),
                       lambda b: b.update(canonical_signal_source="other.json")):
            with self.subTest(mutate=mutate):
                b = copy.deepcopy(self.e["bridge"])
                mutate(b)
                b["evidence_sha256"] = producer.stable_hash({k: v for k, v in b.items() if k != "evidence_sha256"})
                with self.assertRaises(RuntimeError):
                    producer.build_authority(BATCH, DAY, self.e["signals"], self.e["prices"],
                                             self.e["signal_adapter"], self.e["price_adapter"], b,
                                             {k: self.a[k] for k in ("repository", "workflow", "producer_run_id", "producer_run_attempt", "producer_commit_sha")})

    def test_zero_sized_real_evidence_can_authorize(self):
        self.e["bridge"]["execution_state"] = "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS"
        b = self.e["bridge"]
        b["evidence_sha256"] = producer.stable_hash({k: v for k, v in b.items() if k != "evidence_sha256"})
        authority, _ = producer.build_authority(BATCH, DAY, self.e["signals"], self.e["prices"],
                                               self.e["signal_adapter"], self.e["price_adapter"], b,
                                               {k: self.a[k] for k in ("repository", "workflow", "producer_run_id", "producer_run_attempt", "producer_commit_sha")})
        self.assertEqual(authority["bridge_execution_state"], "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS")

    def test_duplicate_items_precede_header_write(self):
        plan, items = self.plan()
        with patch.object(sizing, "rest_insert_only") as write, patch.object(sizing, "rest_get") as read:
            with self.assertRaisesRegex(RuntimeError, "DUPLICATE"):
                sizing.persist_plan(plan, items + [items[0]])
            write.assert_not_called()
            read.assert_not_called()

    def test_duplicate_item_id_precedes_header_write(self):
        plan, items = self.plan()
        with patch.object(sizing, "stable_hash", return_value="0" * 64), patch.object(sizing, "rest_insert_only") as write:
            with self.assertRaisesRegex(RuntimeError, "DUPLICATE_PLAN_ITEM"):
                sizing.persist_plan(plan, items)
            write.assert_not_called()

    def test_item_authority_mismatch_precedes_write(self):
        plan, items = self.plan()
        items[0]["canonical_authority_hash"] = "other"
        with patch.object(sizing, "rest_insert_only") as write:
            with self.assertRaisesRegex(RuntimeError, "ITEM_AUTHORITY"):
                sizing.persist_plan(plan, items)
            write.assert_not_called()

    def test_same_authority_rerun_stable_without_writes(self):
        plan, items = self.plan()
        with patch.object(sizing, "rest_get", return_value=[]), patch.object(sizing, "rest_insert_only"):
            header, stored_items = sizing.persist_plan(plan, items)
        with patch.object(sizing, "rest_get", return_value=[header]), \
                patch.object(sizing, "complete_rows_by_plan", return_value=stored_items), \
                patch.object(sizing, "rest_insert_only") as write:
            repeated = sizing.persist_plan(plan, items)
            self.assertEqual(repeated, (header, stored_items))
            write.assert_not_called()

    def test_different_authority_or_legacy_same_day_plan_fails(self):
        plan, items = self.plan()
        with patch.object(sizing, "rest_get", return_value=[{"plan_id": "legacy-or-other-authority"}]), \
                patch.object(sizing, "rest_insert_only") as write:
            with self.assertRaisesRegex(RuntimeError, "SAME_DAY_PLAN_AUTHORITY_CONFLICT"):
                sizing.persist_plan(plan, items)
            write.assert_not_called()

    def test_incomplete_same_authority_plan_fails_without_repair(self):
        plan, items = self.plan()
        with patch.object(sizing, "rest_get", return_value=[]), patch.object(sizing, "rest_insert_only"):
            header, _ = sizing.persist_plan(plan, items)
        with patch.object(sizing, "rest_get", return_value=[header]), patch.object(sizing, "complete_rows_by_plan", return_value=[]), \
                patch.object(sizing, "rest_insert_only") as write:
            with self.assertRaisesRegex(RuntimeError, "INCOMPLETE"):
                sizing.persist_plan(plan, items)
            write.assert_not_called()

    def test_changed_persisted_content_is_not_overwritten(self):
        plan, items = self.plan()
        with patch.object(sizing, "rest_get", return_value=[]), patch.object(sizing, "rest_insert_only"):
            header, stored = sizing.persist_plan(plan, items)
        stored[0]["paper_quantity"] = "999999"
        with patch.object(sizing, "rest_get", return_value=[header]), \
                patch.object(sizing, "complete_rows_by_plan", return_value=stored), \
                patch.object(sizing, "rest_insert_only") as write:
            with self.assertRaisesRegex(RuntimeError, "ITEM_CONTENT"):
                sizing.persist_plan(plan, items)
            write.assert_not_called()

    def test_producer_reads_all_pages_and_rejects_repeated_page(self):
        rows = self.e["signals"]
        with patch.object(producer, "rest_get", side_effect=[([rows[0]], None), ([rows[1]], None), ([], None)]):
            self.assertEqual(producer.read_canonical_batch(producer.SIGNAL_STORE, BATCH), rows)
        with patch.object(producer, "rest_get", return_value=([rows[0]], None)):
            with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_CANONICAL"):
                producer.read_canonical_batch(producer.SIGNAL_STORE, BATCH)

    def test_adapter_or_bridge_evidence_tampering_fails(self):
        for key in ("signal_adapter", "price_adapter", "bridge"):
            with self.subTest(key=key):
                evidence = copy.deepcopy(self.e)
                evidence[key]["tampered"] = True
                with self.assertRaises(RuntimeError):
                    producer.validate_authority(self.a, evidence, "123", "2", SHA)

    def test_numeric_read_preserves_rerun_precision(self):
        response = sizing.requests.Response()
        response.status_code = 200
        response._content = b'[{"current_portfolio_exposure":0.1234567890123456789012345678}]'
        with patch.object(sizing, "supabase", return_value=("https://offline.invalid", {})), \
                patch.object(sizing.requests, "get", return_value=response):
            rows = sizing.rest_get("fixture", [])
        self.assertTrue(sizing.persisted_row_matches(
            {"current_portfolio_exposure": "0.1234567890123456789012345678"}, rows[0]))

    def test_missing_or_ambiguous_artifact_fails(self):
        for count in (0, 2):
            with self.subTest(count=count), self.artifact_mock(artifact_count=count):
                with self.assertRaisesRegex(RuntimeError, "MISSING_EXPIRED_OR_AMBIGUOUS"):
                    sizing.load_explicit_authority()

    def test_header_conflict_cannot_write_items(self):
        plan, items = self.plan()
        with patch.object(sizing, "rest_get", return_value=[]), \
                patch.object(sizing, "rest_insert_only", side_effect=RuntimeError("HTTP=409")) as write:
            with self.assertRaisesRegex(RuntimeError, "409"):
                sizing.persist_plan(plan, items)
            self.assertEqual(write.call_count, 1)
            self.assertEqual(write.call_args[0][0], sizing.PLAN_TABLE)

    def test_paper_halt_and_no_authorization_still_size_zero(self):
        ledger = dict(ledger_date=DAY, nav=1000000, cash=1000000, market_value=0)
        for halt in (True, False):
            governance = dict(risk_state="PAPER_HALT" if halt else "NORMAL", risk_reduction_factor=1,
                              governance_date=DAY, new_paper_entries_authorized=False, paper_halt=halt)
            with self.subTest(halt=halt), patch.object(sizing, "rest_get", side_effect=self.database):
                plan, items = sizing.build_plan(governance, ledger, [], self.a)
                self.assertEqual(sizing.D(plan["total_allocated_capital"]), 0)
                self.assertTrue(all(sizing.D(item["paper_quantity"]) == 0 for item in items))

    def test_safety_invariants(self):
        plan, items = self.plan()
        for module in (producer, sizing):
            self.assertIs(module.PAPER_ONLY, True)
            self.assertIs(module.BROKER_ORDER_SUBMISSION_ENABLED, False)
            self.assertIs(module.REAL_MONEY_TRADING_ENABLED, False)
            self.assertIs(module.HISTORICAL_REWRITE_ALLOWED, False)
        for obj in [plan, *items, self.a]:
            self.assertIs(obj["broker_order_submission_enabled"], False)
            self.assertIs(obj["real_money_trading_enabled"], False)
        self.assertLessEqual(sizing.D(plan["total_allocated_capital"]), sizing.D(plan["max_new_capital"]))


if __name__ == "__main__":
    unittest.main()
