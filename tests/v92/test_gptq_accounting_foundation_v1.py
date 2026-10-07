"""Deterministic P0 accounting contract tests; no Supabase writes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import importlib
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "automation/v92"))

from gptq_accounting_v1 import AccountingLineage, Event, money  # noqa: E402


DAY1 = date(2026, 10, 1)
DAY2 = date(2026, 10, 2)
SQL = ROOT / "supabase/GPTQ_V92_P0_ACCOUNTING_FOUNDATION_V1.sql"


def opened() -> AccountingLineage:
    ledger = AccountingLineage("V9.1")
    ledger.initialize(DAY1, "1000000", "0", "0", event_key="init:V9.1")
    return ledger


def buy(key: str = "buy:1", when: date = DAY1) -> Event:
    return Event(key, "BUY", when, cash_delta=Decimal("-100142.50"),
                 notional=Decimal("100000"), buy_commission=Decimal("142.50"),
                 slippage=Decimal("100"))


def sell(key: str = "sell:1", when: date = DAY1) -> Event:
    return Event(key, "SELL", when, cash_delta=Decimal("105535.25"),
                 trade_realized_pnl=Decimal("5535.25"),
                 notional=Decimal("106000"), sell_commission=Decimal("151.05"),
                 transaction_tax=Decimal("313.70"), cost_basis=Decimal("100000"))


class AccountingFoundationTests(unittest.TestCase):
    def test_first_initialization_succeeds(self):
        self.assertEqual(opened().states[DAY1].closing_cash, money("1000000"))

    def test_initialization_cannot_happen_twice(self):
        ledger = opened()
        with self.assertRaisesRegex(ValueError, "already initialized"):
            ledger.initialize(DAY2, "1000000", 0, 0, event_key="init:again")

    def test_missing_prior_state_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing prior state"):
            AccountingLineage("V9.1").apply(buy())

    def test_phase1_never_reconstructs_from_initial_capital_after_start(self):
        source = (ROOT / "automation/v92/production_paper_trading_phase1.py").read_text(encoding="utf-8")
        self.assertIn("opening_cash = fnum(prior_snapshots[0][\"cash\"])", source)
        self.assertIn("MISSING_PRIOR_ACCOUNTING_STATE", source)
        self.assertNotIn('cash = INITIAL_CAPITAL\n    for p in existing_positions:', source)

    def test_buy_reduces_cash_once(self):
        self.assertEqual(opened().apply(buy()).closing_cash, money("899857.50"))

    def test_duplicate_buy_replay_is_idempotent(self):
        ledger = opened()
        first = ledger.apply(buy())
        self.assertEqual(ledger.apply(buy()).closing_cash, first.closing_cash)
        self.assertEqual(len(ledger.events), 2)

    def test_sell_increases_cash_once(self):
        ledger = opened()
        ledger.apply(buy())
        self.assertEqual(ledger.apply(sell()).closing_cash, money("1005392.75"))

    def test_duplicate_sell_replay_is_idempotent(self):
        ledger = opened()
        ledger.apply(buy())
        first = ledger.apply(sell())
        self.assertEqual(ledger.apply(sell()).closing_cash, first.closing_cash)
        self.assertEqual(len(ledger.events), 3)

    def test_sell_updates_trade_realized_pnl(self):
        ledger = opened()
        ledger.apply(buy())
        self.assertEqual(ledger.apply(sell()).daily_realized_pnl, money("5535.25"))

    def test_daily_realized_pnl_survives_mark(self):
        ledger = opened()
        ledger.apply(buy())
        ledger.apply(sell())
        mark = Event("mtm:1", "MARK_TO_MARKET", DAY1,
                     market_value=0, unrealized_pnl=0)
        self.assertEqual(ledger.apply(mark).daily_realized_pnl, money("5535.25"))

    def test_cumulative_realized_pnl_is_preserved(self):
        ledger = opened()
        ledger.apply(buy())
        ledger.apply(sell())
        self.assertEqual(ledger.states[DAY1].cumulative_realized_pnl, money("5535.25"))

    def test_later_no_exit_day_cannot_zero_cumulative(self):
        ledger = opened()
        ledger.apply(buy())
        ledger.apply(sell())
        ledger.finalize(DAY1, expected_cash="1005392.75", expected_market_value=0,
                        expected_equity="1005392.75", expected_unrealized_pnl=0,
                        expected_daily_realized_pnl="5535.25")
        next_state = ledger.apply(Event("mtm:2", "MARK_TO_MARKET", DAY2,
                                        market_value=0, unrealized_pnl=0))
        self.assertEqual(next_state.daily_realized_pnl, money(0))
        self.assertEqual(next_state.cumulative_realized_pnl, money("5535.25"))

    def test_equity_is_cash_plus_market_value(self):
        ledger = opened()
        state = ledger.apply(Event("mtm:1", "MARK_TO_MARKET", DAY1,
                                   market_value="250000", unrealized_pnl="1000"))
        self.assertEqual(state.total_equity, state.closing_cash + state.market_value)

    def test_inconsistent_equity_publication_fails(self):
        ledger = opened()
        with self.assertRaisesRegex(ValueError, "publication disagrees"):
            ledger.finalize(DAY1, expected_cash="1000000", expected_market_value=0,
                            expected_equity="1000001", expected_unrealized_pnl=0,
                            expected_daily_realized_pnl=0)

    def test_fee_arithmetic_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "BUY cash"):
            buy().normalized().__class__("bad", "BUY", DAY1,
                cash_delta=Decimal("-100000"), notional=Decimal("100000"),
                buy_commission=Decimal("142.50")).normalized()
        self.assertEqual(sell().normalized().cash_delta,
                         money("106000")-money("151.05")-money("313.70"))

    def test_phase26_uses_top_level_report(self):
        os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
        os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-only")
        module = importlib.import_module("paper_trading_phase26_daily_cycle")
        report = {"run_date": module.RUN_DATE, "strategy_version": module.STRATEGY_VERSION,
                  "ending_cash": 900000, "ending_market_value": 100000,
                  "ending_equity": 1000000, "realized_pnl_today": 700,
                  "unrealized_pnl": 500, "positions_open": 2,
                  "decisions": [{"unrealized_pnl": -100}]}
        from unittest import mock
        path = Path("report.json")
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps(report)):
            self.assertEqual(module.load_phase_report(path, set(report)-{"decisions"}), report)

    def test_nested_decision_cannot_replace_portfolio_pnl(self):
        source = (ROOT / "automation/v92/paper_trading_phase26_daily_cycle.py").read_text(encoding="utf-8")
        self.assertNotIn("last_json_object", source)
        self.assertIn('"unrealized_pnl": phase24["unrealized_pnl"]', source)

    def test_multiple_writers_cannot_replace_finalized_state(self):
        sql = SQL.read_text(encoding="utf-8")
        self.assertIn("NON_OWNER_FINANCIAL_SNAPSHOT_WRITE", sql)
        self.assertIn("FINALIZED_ACCOUNTING_RUN_FINANCIALS_IMMUTABLE", sql)
        self.assertIn("FINALIZED_ACCOUNTING_STATE_IMMUTABLE", sql)

    def test_business_date_rollover_preserves_cash(self):
        ledger = opened()
        ledger.apply(buy())
        ledger.finalize(DAY1, expected_cash="899857.50", expected_market_value=0,
                        expected_equity="899857.50", expected_unrealized_pnl=0,
                        expected_daily_realized_pnl=0)
        next_state = ledger.apply(Event("mtm:2", "MARK_TO_MARKET", DAY2,
                                        market_value=0, unrealized_pnl=0))
        self.assertEqual(next_state.opening_cash, money("899857.50"))

    def test_historical_rows_are_not_touched_by_migration(self):
        sql = SQL.read_text(encoding="utf-8").lower()
        self.assertNotIn("delete from public.gptq_paper_", sql)
        self.assertNotIn("update public.gptq_paper_equity_snapshots", sql)

    def test_migration_is_additive_and_repeatable(self):
        sql = SQL.read_text(encoding="utf-8").lower()
        self.assertEqual(sql.count("create table if not exists"), 3)
        self.assertIn("create or replace function", sql)
        self.assertIn("drop trigger if exists", sql)

    def test_no_phase3_accounting_change(self):
        sql = SQL.read_text(encoding="utf-8").lower()
        self.assertNotIn("public.paper_", sql)

    def test_safety_flags_remain_locked(self):
        import gptq_accounting_v1 as model
        import gptq_accounting_runtime_v1 as runtime
        for module in (model, runtime):
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.BROKER_ORDER_SUBMISSION_ENABLED)
            self.assertFalse(module.REAL_MONEY_TRADING_ENABLED)
            self.assertFalse(module.HISTORICAL_REWRITE_ALLOWED)

    def test_same_key_different_financial_content_fails(self):
        ledger = opened()
        ledger.apply(buy())
        with self.assertRaisesRegex(ValueError, "different financial content"):
            ledger.apply(Event("buy:1", "BUY", DAY1, cash_delta=-200, notional=200))

    def test_cash_adjustment_requires_authorization(self):
        with self.assertRaisesRegex(ValueError, "explicit authorization"):
            opened().apply(Event("adjust:1", "CASH_ADJUSTMENT", DAY1, cash_delta=10))


if __name__ == "__main__":
    unittest.main()
