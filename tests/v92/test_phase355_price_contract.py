"""Offline canonical price and settlement write-boundary regression tests."""
import copy
import io
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from test_phase349_price_contract import load_phase


settlement = load_phase("355")
phase349 = load_phase("349")
READERS = ((settlement, settlement.latest_real_price), (phase349, phase349.load_real_price))


class CanonicalPriceTests(unittest.TestCase):
    def setUp(self):
        for target in ("requests.get", "requests.post", "subprocess.run"):
            guard = patch(target, side_effect=AssertionError("Unexpected external I/O"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_latest_canonical_close_query_matches_merged_phase349_contract(self):
        history = [{"trade_date": "2026-09-23", "close": "90"},
                   {"trade_date": "2026-09-24", "close": "101.25"}]
        for module, reader in READERS:
            with self.subTest(phase=module.__name__):
                def get(table, params):
                    query = dict(params)
                    if table == "stocks":
                        self.assertEqual(query, {"select": "id", "symbol": "eq.2330", "limit": "2"})
                        return [{"id": 42}]
                    self.assertEqual(table, "daily_prices")
                    # Exact query excludes symbol/date and ticker-as-stock_id.
                    self.assertEqual(query, {"select": "trade_date,close", "stock_id": "eq.42",
                                             "order": "trade_date.desc", "limit": "1"})
                    return sorted(history, key=lambda row: row["trade_date"], reverse=True)[:1]
                with patch.object(module, "rest_get", side_effect=get) as read:
                    self.assertEqual(reader("2330"), ("2026-09-24", Decimal("101.25")))
                    self.assertEqual(read.call_count, 2)

    def test_unknown_and_ambiguous_mapping_fail_without_price_query(self):
        for module, reader in READERS:
            for stocks in ([], [{"id": 42}, {"id": 43}], [{"id": 42}, {"id": 42}]):
                with self.subTest(phase=module.__name__, stocks=stocks), \
                        patch.object(module, "rest_get", return_value=stocks) as read:
                    with self.assertRaisesRegex(RuntimeError, "STOCK_MAPPING_NOT_UNIQUE"):
                        reader("2330")
                    read.assert_called_once()

    def test_invalid_stock_id_fails_closed(self):
        for module, reader in READERS:
            for stock_id in (None, "", "2330", 0, -1, 1.5, True):
                with self.subTest(phase=module.__name__, stock_id=stock_id), \
                        patch.object(module, "rest_get", return_value=[{"id": stock_id}]) as read:
                    with self.assertRaisesRegex(RuntimeError, "INVALID_STOCK_ID"):
                        reader("2330")
                    read.assert_called_once()

    def test_missing_price_has_no_fallback(self):
        for module, reader in READERS:
            with self.subTest(phase=module.__name__), \
                    patch.object(module, "rest_get", side_effect=[[{"id": 42}], []]) as read:
                with self.assertRaisesRegex(RuntimeError, "NO_REAL_MARKET_PRICE"):
                    reader("2330")
                self.assertEqual(read.call_count, 2)

    def test_invalid_close_cannot_use_alternate_or_synthetic_price(self):
        for module, reader in READERS:
            for close in (None, "", "invalid", "NaN", "sNaN", "Infinity", "-Infinity", 0, -1, True):
                row = {"trade_date": "2026-09-24", "close": close, "close_price": 100, "price": 100}
                with self.subTest(phase=module.__name__, close=close), \
                        patch.object(module, "rest_get", side_effect=[[{"id": 42}], [row]]) as read:
                    with self.assertRaisesRegex(RuntimeError, "INVALID_REAL_MARKET_PRICE"):
                        reader("2330")
                    self.assertEqual(read.call_count, 2)

    def test_missing_trade_date_fails_closed(self):
        with patch.object(settlement, "rest_get", side_effect=[
                [{"id": 42}], [{"date": "2026-09-24", "close": 100}]]):
            with self.assertRaisesRegex(RuntimeError, "INVALID_REAL_MARKET_PRICE_ROW"):
                settlement.latest_real_price("2330")

    def test_http_database_failure_at_either_lookup_is_not_swallowed(self):
        ok = Mock(status_code=200)
        ok.json.return_value = [{"id": 42}]
        error = Mock(status_code=400, text='{"code":"42703","message":"schema error"}')
        for responses in ([error], [ok, error]):
            with self.subTest(stage=len(responses)), \
                    patch.object(settlement, "supabase", return_value=("https://unused.invalid", {})), \
                    patch.object(settlement.requests, "get", side_effect=responses) as get:
                with self.assertRaisesRegex(RuntimeError, "GET HTTP 400.*42703"):
                    settlement.latest_real_price("2330")
                self.assertEqual(get.call_count, len(responses))

    def test_transport_failure_has_no_fallback(self):
        with patch.object(settlement, "supabase", return_value=("https://unused.invalid", {})), \
                patch.object(settlement.requests, "get", side_effect=settlement.requests.Timeout("test timeout")):
            with self.assertRaises(settlement.requests.Timeout):
                settlement.latest_real_price("2330")

    def exercise_settlement(self, failure=None, new_positions=False):
        positions = [dict(symbol=symbol, quantity="1", avg_entry_price="80", status="OPEN",
                          opened_date="2026-09-23", realized_pnl="0") for symbol in ("2330", "2317")]
        fills = [dict(fill_id=f"fill-{symbol}", symbol=symbol, side="BUY", quantity="1",
                      fill_price="80", fill_notional="80") for symbol in ("2330", "2317")]
        portfolio = dict(cash="1000", realized_pnl="0", initial_cash="1000",
                         broker_trading_enabled=False, real_money_trading_enabled=False)
        original = copy.deepcopy((positions, fills, portfolio))
        trace, stored = [], {}
        execution = dict(status="PASS", cycle_date="2026-09-24", cycle_id="test-cycle",
                         execution_state="PAPER_SIMULATED_EXECUTION_COMPLETED",
                         paper_halt=False, fail_closed_policy=True)
        for flag in ("synthetic_market_data", "synthetic_signals", "fake_prices_allowed", "broker_api_used",
                     "broker_credentials_used", "broker_order_submission_enabled", "real_money_trading_enabled",
                     "live_money_release_authorized"):
            execution[flag] = False

        def get(table, params):
            query = dict(params)
            if table == settlement.PORTFOLIO_TABLE:
                return [portfolio]
            if table == settlement.POSITIONS_TABLE:
                return [] if new_positions else positions
            if table == settlement.FILL_TABLE:
                return fills
            if table == settlement.FILL_SETTLEMENT_TABLE:
                return []
            if table == "stocks":
                if query["symbol"] == "eq.2317" and failure == "unknown":
                    return []
                return [{"id": 42 if query["symbol"] == "eq.2330" else 43}]
            if table == settlement.MARKET_TABLE:
                trace.append(("price", query["stock_id"]))
                if query["stock_id"] == "eq.43":
                    if failure == "missing":
                        return []
                    if failure == "http":
                        raise RuntimeError("daily_prices: GET HTTP 400: 42703")
                    if failure == "invalid":
                        return [{"trade_date": "2026-09-24", "close": "NaN"}]
                return [{"trade_date": "2026-09-24", "close": "100"}]
            if table == settlement.SETTLEMENT_TABLE:
                return stored[table]
            self.fail(f"Unexpected table {table}")

        def upsert(table, rows, conflict):
            trace.append(("write", table))
            stored[table] = copy.deepcopy(rows)

        with patch.object(settlement, "rest_get", side_effect=get), \
                patch.object(settlement, "rest_upsert", side_effect=upsert) as write, \
                patch.object(settlement, "run_upstream", return_value=(0, execution)), \
                patch.object(settlement, "dump_json") as dump, \
                patch.object(settlement, "write_summary"), redirect_stdout(io.StringIO()):
            if failure:
                with self.assertRaises(RuntimeError):
                    settlement.main()
                self.assertIn(("price", "eq.42"), trace)
                write.assert_not_called()
                dump.assert_not_called()
            else:
                self.assertEqual(settlement.main(), 0)
                self.assertEqual(trace[:2], [("price", "eq.42"), ("price", "eq.43")])
                self.assertTrue(all(kind == "write" for kind, _ in trace[2:]))
                self.assertEqual(set(stored), {settlement.PORTFOLIO_TABLE, settlement.POSITIONS_TABLE,
                    settlement.POSITION_EVENTS_TABLE, settlement.SNAPSHOT_TABLE,
                    settlement.SETTLEMENT_TABLE, settlement.FILL_SETTLEMENT_TABLE})
                result = dump.call_args.args[1]
                self.assertEqual(result["execution_cycle_id"], "test-cycle")
                self.assertEqual(result["settlement_date"], "2026-09-24")
                self.assertEqual(result["settlement_state"], "SETTLEMENT_COMPLETED")
                self.assertEqual(result["fills_settled"], 2)
                self.assertEqual(result["cash_after"], 840)
                self.assertEqual(result["trading_mode"], "SHADOW_ONLY_NO_BROKER")
                self.assertIs(result["broker_order_submission_enabled"], False)
                self.assertIs(result["real_money_trading_enabled"], False)
                self.assertEqual(dump.call_args.args[0], settlement.RESULT_JSON)
        self.assertEqual((positions, fills, portfolio), original)

    def test_price_failure_prevents_every_financial_write_after_staged_fills(self):
        for failure in ("unknown", "missing", "invalid", "http"):
            for new_positions in (False, True):
                with self.subTest(failure=failure, new_positions=new_positions):
                    self.exercise_settlement(failure, new_positions)

    def test_success_resolves_all_prices_before_writes_and_preserves_result_contract(self):
        self.exercise_settlement()

    def test_closed_positions_keep_existing_caller_semantics(self):
        closed = dict(symbol="2330", quantity="0", status="CLOSED")
        with patch.object(settlement, "latest_real_price") as price:
            self.assertEqual(settlement.mark_to_market([closed]),
                             ([closed], Decimal("0.00"), Decimal("0.00"), None))
            price.assert_not_called()


if __name__ == "__main__":
    unittest.main()
