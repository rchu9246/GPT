"""Offline Phase 3.4.9 schema and pre-persistence price contract tests."""
import importlib.util
import io
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]


def load_phase(phase):
    path = next((ROOT / "automation/v92").glob(f"paper_trading_phase{phase}_*.py"))
    spec = importlib.util.spec_from_file_location(f"phase{phase}_price_test", path)
    module = importlib.util.module_from_spec(spec)
    # Runtime imports create output directories; tests must not create evidence.
    with patch.object(Path, "mkdir"):
        spec.loader.exec_module(module)
    return module


engine = load_phase("349")
orchestrator = load_phase("350")


def upstream_evidence():
    return dict(
        status="PASS", daily_cycle_status="COMPLETED",
        canonical_runtime_state=engine.EXECUTED_STATE,
        latest_market_date="2026-09-25", market_data_source="daily_prices",
        stocks_with_history=2, signal_engine_stocks_scanned=2, eligible_v91_signals=2,
        synthetic_market_data=False, synthetic_fallback_allowed=False,
        synthetic_evidence_present=False, fake_prices_allowed=False,
        broker_api_used=False, broker_credentials_used=False,
        broker_order_submission_enabled=False, real_money_trading_enabled=False,
        live_money_release_authorized=False, fail_closed_policy=True,
    )


class PriceContractTests(unittest.TestCase):
    def setUp(self):
        # A missed mock must fail locally, never contact a database or run upstream.
        for target in ("requests.get", "requests.post", "subprocess.run"):
            guard = patch(target, side_effect=AssertionError("Unexpected external I/O"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_canonical_id_query_returns_latest_close_and_market_date(self):
        history = [
            {"trade_date": "2026-09-24", "close": "98.50"},
            {"trade_date": "2026-09-25", "close": "101.25"},
        ]

        def get(table, params):
            query = dict(params)
            if table == "stocks":
                self.assertEqual(query, {"select": "id", "symbol": "eq.2330", "limit": "2"})
                return [{"id": 42}]
            self.assertEqual(table, "daily_prices")
            self.assertEqual(query, {"select": "trade_date,close", "stock_id": "eq.42",
                                     "order": "trade_date.desc", "limit": "1"})
            self.assertNotIn("symbol", query)
            self.assertNotIn("symbol", query["select"])
            return sorted(history, key=lambda row: row["trade_date"], reverse=True)[:1]

        with patch.object(engine, "rest_get", side_effect=get) as read:
            self.assertEqual(engine.load_real_price("2330"), ("2026-09-25", Decimal("101.25")))
        self.assertEqual(read.call_count, 2)

    def test_unknown_and_ambiguous_symbols_fail_before_price_query(self):
        for stocks in ([], [{"id": 42}, {"id": 43}], [{"id": 42}, {"id": 42}]):
            with self.subTest(stocks=stocks), patch.object(engine, "rest_get", return_value=stocks) as read:
                with self.assertRaisesRegex(RuntimeError, "STOCK_MAPPING_NOT_UNIQUE: 2330"):
                    engine.load_real_price("2330")
                read.assert_called_once()

    def test_invalid_stock_id_fails_closed(self):
        for stock_id in (None, "", "2330", True, 0, -1, 1.5):
            with self.subTest(stock_id=stock_id), patch.object(engine, "rest_get", return_value=[{"id": stock_id}]):
                with self.assertRaisesRegex(RuntimeError, "INVALID_STOCK_ID"):
                    engine.load_real_price("2330")

    def test_missing_price_fails_without_fallback(self):
        with patch.object(engine, "rest_get", side_effect=[[{"id": 42}], []]) as read:
            with self.assertRaisesRegex(RuntimeError, "NO_REAL_MARKET_PRICE: 2330 stock_id=42"):
                engine.load_real_price("2330")
            self.assertEqual(read.call_count, 2)

    def test_invalid_close_never_uses_alternate_or_synthetic_price(self):
        for close in (None, "", "invalid", "NaN", "sNaN", "Infinity", "-Infinity", 0, -1, True):
            row = {"trade_date": "2026-09-25", "close": close, "close_price": 100, "price": 100}
            with self.subTest(close=close), patch.object(engine, "rest_get", side_effect=[[{"id": 42}], [row]]) as read:
                with self.assertRaisesRegex(RuntimeError, "INVALID_REAL_MARKET_PRICE"):
                    engine.load_real_price("2330")
                self.assertEqual(read.call_count, 2)

    def test_missing_canonical_date_fails_closed(self):
        with patch.object(engine, "rest_get", side_effect=[[{"id": 42}], [{"date": "2026-09-25", "close": 100}]]):
            with self.assertRaisesRegex(RuntimeError, "INVALID_REAL_MARKET_PRICE_ROW"):
                engine.load_real_price("2330")

    def test_http_database_errors_fail_at_either_lookup_without_fallback(self):
        ok = Mock(status_code=200)
        ok.json.return_value = [{"id": 42}]
        failure = Mock(status_code=400, text='{"code":"42703","message":"schema error"}')
        for responses in ([failure], [ok, failure]):
            with self.subTest(stage=len(responses)), patch.object(engine, "supabase", return_value=("https://unused.invalid", {})), \
                    patch.object(engine.requests, "get", side_effect=responses) as get:
                with self.assertRaisesRegex(RuntimeError, "GET HTTP 400.*42703"):
                    engine.load_real_price("2330")
                self.assertEqual(get.call_count, len(responses))

    def test_transport_error_fails_closed(self):
        with patch.object(engine, "supabase", return_value=("https://unused.invalid", {})), \
                patch.object(engine.requests, "get", side_effect=engine.requests.Timeout("test timeout")):
            with self.assertRaises(engine.requests.Timeout):
                engine.load_real_price("2330")

    def exercise_main(self, *, new_portfolio, fail_second_price):
        trace = []
        positions = [dict(symbol=symbol, quantity="1", avg_entry_price="80", status="OPEN")
                     for symbol in ("2330", "2317")]
        fills = [dict(symbol=p["symbol"], quantity="1", fill_price="80", side="BUY") for p in positions]

        def get(table, params):
            query = dict(params)
            trace.append(("read", table))
            if table == engine.PORTFOLIO_TABLE:
                return [] if new_portfolio else [{"cash": "1000000", "realized_pnl": "0"}]
            if table == engine.POSITIONS_TABLE:
                return [] if new_portfolio else positions
            if table == engine.EVENTS_TABLE:
                return []
            if table == "stocks":
                return [{"id": 42 if query["symbol"] == "eq.2330" else 43}]
            if table == engine.MARKET_TABLE:
                if query["stock_id"] == "eq.43" and fail_second_price:
                    return []
                return [{"trade_date": "2026-09-24", "close": "100"}]
            self.fail(f"Unexpected table: {table}")

        with patch.object(engine, "rest_get", side_effect=get), \
                patch.object(engine, "rest_upsert", side_effect=lambda table, *args: trace.append(("write", table))) as write, \
                patch.object(engine, "persist_state", wraps=engine.persist_state) as persist, \
                patch.object(engine, "snapshot", wraps=engine.snapshot) as snapshot, \
                patch.object(engine, "run_upstream", return_value=(0, upstream_evidence())), \
                patch.object(engine, "get_phase348_fills", return_value=fills if new_portfolio else []), \
                patch.object(engine, "dump_json") as dump, patch.object(engine, "write_summary"), \
                patch.object(sys, "argv", ["phase349", "--approver", "test-operator"]), redirect_stdout(io.StringIO()):
            if fail_second_price:
                with self.assertRaisesRegex(RuntimeError, "NO_REAL_MARKET_PRICE: 2317"):
                    engine.main()
                persist.assert_not_called()
                snapshot.assert_not_called()
                write.assert_not_called()
                dump.assert_not_called()
                self.assertEqual(trace.count(("read", engine.MARKET_TABLE)), 2)
                return
            self.assertEqual(engine.main(), 0)
            first_write = next(i for i, item in enumerate(trace) if item[0] == "write")
            self.assertEqual(trace[:first_write].count(("read", engine.MARKET_TABLE)), 2)
            self.assertFalse(any(item[0] == "read" for item in trace[first_write:]))
            self.assertEqual([call.args[0] for call in write.call_args_list],
                             [engine.PORTFOLIO_TABLE, engine.POSITIONS_TABLE,
                              engine.EVENTS_TABLE, engine.SNAPSHOT_TABLE])
            self.assertEqual(snapshot.call_args.args[-1],
                             "2026-09-24")
            return dump.call_args.args[1]

    def test_no_financial_persistence_when_second_required_price_fails(self):
        for new in (False, True):
            with self.subTest(new_portfolio=new):
                self.exercise_main(new_portfolio=new, fail_second_price=True)

    def test_all_prices_precede_writes_and_phase350_interface_is_unchanged(self):
        result = self.exercise_main(new_portfolio=True, fail_second_price=False)
        self.assertEqual(result["trading_mode"], "SHADOW_ONLY_NO_BROKER")
        self.assertEqual(result["latest_market_date"], "2026-09-25")
        self.assertEqual(result["positions"][0]["last_mark_date"], "2026-09-24")
        self.assertEqual(orchestrator.UPSTREAM, Path(engine.__file__))
        self.assertEqual(orchestrator.UPSTREAM_JSON, engine.RESULT_JSON)
        with patch.object(orchestrator, "PORTFOLIO_ID", engine.PORTFOLIO_ID):
            orchestrator.validate_safety(result)
        with patch.object(orchestrator.subprocess, "run", return_value=Mock(returncode=0, stdout="", stderr="")) as run, \
                patch.object(Path, "exists", return_value=True), patch.object(orchestrator, "load_json", return_value=result):
            self.assertEqual(orchestrator.run_upstream("test-operator"), (0, result))
        self.assertEqual(run.call_args.args[0], [sys.executable, str(orchestrator.UPSTREAM), "--approver", "test-operator"])
        self.assertEqual(run.call_args.kwargs["env"]["PAPER_TRADING_MODE"], "SHADOW_ONLY_NO_BROKER")
        self.assertEqual(run.call_args.kwargs["env"]["PHASE349_PORTFOLIO_ID"], orchestrator.PORTFOLIO_ID)


if __name__ == "__main__":
    unittest.main()
