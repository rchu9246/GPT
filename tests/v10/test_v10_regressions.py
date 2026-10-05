from __future__ import annotations

import inspect
import unittest
from datetime import date, timedelta
from decimal import Decimal

from automation.v10.backtest import PortfolioBacktest, buy_and_hold_return
from automation.v10.execution import ControlledPaperExecution
from automation.v10.halt_authority import RepositoryHaltAuthority
from automation.v10.ledger import AppendOnlyLedger, LedgerEvent, mark_to_market, replay_account
from automation.v10.market_data import TrustedMarketData
from automation.v10.models import StrategyIntent
from automation.v10.pipeline import ManualDailyPaperPipeline
from automation.v10.reporting import build_report
from automation.v10.research import SEALED_STEP8
from automation.v10.risk import RiskEngine
from automation.v10.safety import SAFETY
from automation.v10.universe import UniverseProvider
from tests.v10.support import bars


class V10RegressionTests(unittest.TestCase):
    def setUp(self):
        self.market = TrustedMarketData(bars())
        self.initial_cash = Decimal("1000000")

    def _fill_ledger(self):
        ledger = AppendOnlyLedger()
        ledger.append("F1", "PAPER_FILL", date(2024, 1, 2),
                      {"fill_id": "F1", "symbol": "S01", "quantity": 10, "price": 100, "fee": 1})
        return ledger

    def test_01_no_cash_reset(self):
        state = replay_account(self._fill_ledger().events, self.initial_cash)
        self.assertEqual(Decimal("998999"), state.cash)

    def test_02_no_duplicate_fills(self):
        ledger = self._fill_ledger()
        with self.assertRaises(RuntimeError):
            ledger.append("E2", "PAPER_FILL", date(2024, 1, 2),
                          {"fill_id": "F1", "symbol": "S01", "quantity": 10, "price": 100, "fee": 1})
            replay_account(ledger.events, self.initial_cash)

    def test_03_no_duplicate_events(self):
        ledger = AppendOnlyLedger()
        ledger.append("E1", "TEST", date(2024, 1, 1), {"x": 1})
        ledger.append("E1", "TEST", date(2024, 1, 1), {"x": 1})
        self.assertEqual(1, len(ledger.events))

    def test_04_realized_pnl_is_replayed(self):
        ledger = self._fill_ledger()
        ledger.append("F2", "PAPER_FILL", date(2024, 1, 3),
                      {"fill_id": "F2", "symbol": "S01", "quantity": -5, "price": 110, "fee": 1})
        self.assertEqual(Decimal("50"), replay_account(ledger.events, self.initial_cash).realized_pnl)

    def test_05_snapshot_is_not_accounting_truth(self):
        self.assertEqual("events", inspect.signature(replay_account).parameters.keys().__iter__().__next__())

    def test_06_events_are_append_only(self):
        self.assertFalse(hasattr(AppendOnlyLedger, "update"))
        self.assertFalse(hasattr(AppendOnlyLedger, "delete"))

    def test_07_restart_replay_is_deterministic(self):
        events = self._fill_ledger().events
        self.assertEqual(replay_account(events, self.initial_cash), replay_account(events, self.initial_cash))

    def test_08_cash_plus_market_value_equals_equity(self):
        state = replay_account(self._fill_ledger().events, self.initial_cash)
        market_value, equity = mark_to_market(state, {"S01": Decimal("101")})
        self.assertEqual(state.cash + market_value, equity)

    def test_09_event_sequence_is_validated(self):
        event = LedgerEvent.create(2, "E", "TEST", date(2024, 1, 1), {}, "GENESIS")
        with self.assertRaises(RuntimeError):
            AppendOnlyLedger((event,))

    def test_10_tamper_fails_closed(self):
        event = LedgerEvent.create(1, "E", "TEST", date(2024, 1, 1), {}, "GENESIS")
        tampered = LedgerEvent(event.sequence, event.event_id, event.event_type, event.event_date,
                               (("x", "1"),), event.previous_hash, event.event_hash)
        with self.assertRaises(RuntimeError):
            AppendOnlyLedger((tampered,))

    def test_11_no_caller_price(self):
        self.assertNotIn("price", inspect.signature(ControlledPaperExecution.fill).parameters)

    def test_12_no_synthetic_price(self):
        self.assertNotIn("synthetic", inspect.signature(TrustedMarketData).parameters)

    def test_13_no_forward_fill(self):
        self.assertIsNone(self.market.bar("S01", date(2030, 1, 1)))

    def test_14_halt_policy_repository_owned(self):
        self.assertEqual([], list(inspect.signature(RepositoryHaltAuthority).parameters))

    def test_15_invalid_observation_fails_closed(self):
        bad = bars(symbols=("BAD",), days=1)[0]
        object.__setattr__(bad, "volume", 0)
        with self.assertRaises(ValueError):
            TrustedMarketData((bad,))

    def test_16_no_lookahead(self):
        cutoff = date(2024, 2, 1)
        self.assertTrue(all(bar.session_date <= cutoff for bar in self.market.history("S01", cutoff)))

    def test_17_provider_lineage_retained(self):
        bar = self.market.history("S01")[0]
        self.assertTrue(bar.provider and bar.provider_observation_id)

    def test_18_signal_executes_next_bar(self):
        intent = StrategyIntent("S01", date(2024, 1, 10), Decimal("0.1"), "REGRESSION")
        decision = RiskEngine().decide(intent, Decimal("0"), Decimal("0"), Decimal("0"))
        order = ControlledPaperExecution(self.market).order(intent, decision)
        self.assertGreater(order.execution_date, intent.signal_date)

    def test_19_risk_does_not_create_signal(self):
        self.assertIn("intent", inspect.signature(RiskEngine.decide).parameters)
        self.assertFalse(hasattr(RiskEngine, "signal"))

    def test_20_step8_rejection_is_preserved(self):
        self.assertEqual("FAIL", SEALED_STEP8.robustness_gate)

    def test_21_benchmark_is_real_market_data(self):
        value = buy_and_hold_return(self.market, "S01", date(2024, 1, 1), date(2024, 3, 1))
        self.assertGreater(value, 0)

    def test_22_manual_pipeline_has_no_broker_order(self):
        ledger = AppendOnlyLedger()
        with self.assertRaises(RuntimeError):
            ManualDailyPaperPipeline(self.market, ledger, self.initial_cash).run(date(2024, 3, 10))
        self.assertEqual((), ledger.events)

    def test_23_safety_remains_paper_only(self):
        SAFETY.assert_safe()
        self.assertTrue(SAFETY.paper_only)
        self.assertFalse(SAFETY.real_money_trading_enabled)


if __name__ == "__main__":
    unittest.main()
