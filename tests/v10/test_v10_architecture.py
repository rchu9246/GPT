from __future__ import annotations

import inspect
import json
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from automation.v10.execution import ControlledPaperExecution
from automation.v10.backtest import PortfolioBacktest, buy_and_hold_return
from automation.v10.factors import FACTOR_NAMES, MultiFactorRankingEngine
from automation.v10.halt_authority import RepositoryHaltAuthority
from automation.v10.ledger import AppendOnlyLedger, LedgerEvent, mark_to_market, replay_account
from automation.v10.market_data import TrustedMarketData
from automation.v10.models import MarketBar, ObservationState, StrategyIntent
from automation.v10.pipeline import ManualDailyPaperPipeline
from automation.v10.portfolio import PortfolioConstructor
from automation.v10.research import PromotionEvidence, SEALED_STEP8, chronological_split, performance, promotion_allowed
from automation.v10.risk import RiskEngine, RiskPolicy
from automation.v10.reporting import build_report
from automation.v10.safety import SAFETY
from automation.v10.universe import UniverseProvider
from tests.v10.support import bars


class SafetyAndHaltTests(unittest.TestCase):
    def test_safety_constitution(self):
        SAFETY.assert_safe()
        self.assertTrue(SAFETY.paper_only)
        self.assertFalse(SAFETY.production_execution_available)
        self.assertFalse(SAFETY.broker_order_submission_enabled)
        self.assertFalse(SAFETY.real_money_trading_enabled)

    def test_halt_authority_accepts_no_trust_input(self):
        self.assertEqual([], list(inspect.signature(RepositoryHaltAuthority).parameters))
        self.assertEqual(["bars"], list(inspect.signature(TrustedMarketData).parameters))

    def test_halt_decision_is_repository_controlled(self):
        decision = RepositoryHaltAuthority().decision("2330", date(2025, 1, 2))
        self.assertEqual("REPOSITORY_CONTROLLED", decision.authority)
        self.assertFalse(decision.confirmed_halt)

    def test_halt_registry_is_hash_pinned(self):
        source = inspect.getsource(RepositoryHaltAuthority.__init__)
        self.assertIn("sha256", source)
        self.assertNotIn("issue_confirmation", source)

    def test_caller_cannot_subclass_or_inject_authority(self):
        with self.assertRaises(TypeError):
            TrustedMarketData(bars(), RepositoryHaltAuthority())  # type: ignore[arg-type]


class MarketUniverseFactorTests(unittest.TestCase):
    def setUp(self):
        self.market = TrustedMarketData(bars())
        self.as_of = date(2024, 3, 10)

    def test_no_future_bars_in_history(self):
        self.assertTrue(all(bar.session_date <= self.as_of for bar in self.market.history("S01", self.as_of)))

    def test_next_bar_is_strictly_later(self):
        self.assertGreater(self.market.next_tradable_bar("S01", self.as_of).session_date, self.as_of)

    def test_universe_deterministic(self):
        provider = UniverseProvider(self.market)
        self.assertEqual(provider.snapshot(self.as_of), provider.snapshot(self.as_of))

    def test_universe_documents_survivorship_limit(self):
        self.assertIn("unavailable", UniverseProvider(self.market).snapshot(self.as_of).survivorship_bias_limitation)

    def test_insufficient_history_rejected(self):
        snap = UniverseProvider(self.market, minimum_observations=100).snapshot(self.as_of)
        self.assertEqual((), snap.symbols)

    def test_factors_are_complete(self):
        ranked = MultiFactorRankingEngine(self.market).rank(UniverseProvider(self.market).snapshot(self.as_of))
        self.assertEqual(FACTOR_NAMES, tuple(name for name, _ in ranked[0].raw))

    def test_ranking_is_deterministic(self):
        engine = MultiFactorRankingEngine(self.market)
        snapshot = UniverseProvider(self.market).snapshot(self.as_of)
        self.assertEqual(engine.rank(snapshot), engine.rank(snapshot))

    def test_ranking_is_point_in_time(self):
        snapshot = UniverseProvider(self.market).snapshot(self.as_of)
        original = MultiFactorRankingEngine(self.market).rank(snapshot)
        future = bars(start=date(2025, 1, 1), days=5)
        expanded = MultiFactorRankingEngine(TrustedMarketData(bars() + future)).rank(snapshot)
        self.assertEqual(original, expanded)

    def test_normalized_scores_bounded(self):
        ranked = MultiFactorRankingEngine(self.market).rank(UniverseProvider(self.market).snapshot(self.as_of))
        self.assertTrue(all(Decimal("0") <= value <= Decimal("1") for item in ranked for _, value in item.normalized))

    def test_tie_break_is_symbol(self):
        flat = TrustedMarketData(bars(symbols=("B", "A")))
        ranked = MultiFactorRankingEngine(flat).rank(UniverseProvider(flat).snapshot(self.as_of))
        self.assertEqual(sorted((item.rank, item.symbol) for item in ranked), [(1, "B"), (2, "A")])


class RiskExecutionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.market = TrustedMarketData(bars())
        self.intent = StrategyIntent("S01", date(2024, 3, 1), Decimal("0.2"), "TEST")

    def test_risk_cannot_increase_weight(self):
        decision = RiskEngine().decide(self.intent, Decimal("0"), Decimal("0"), Decimal("0"))
        self.assertLessEqual(decision.approved_weight, self.intent.target_weight)

    def test_long_only(self):
        intent = replace(self.intent, target_weight=Decimal("-0.1"))
        self.assertEqual("REJECT", RiskEngine().decide(intent, Decimal("0"), Decimal("0"), Decimal("0")).decision)

    def test_liquidity_rejects(self):
        self.assertEqual("LIQUIDITY", RiskEngine().decide(self.intent, Decimal("0"), Decimal("0"), Decimal("0"), False).reason)

    def test_volatility_rejects(self):
        self.assertEqual("VOLATILITY", RiskEngine().decide(self.intent, Decimal("0"), Decimal("1"), Decimal("0")).reason)

    def test_drawdown_rejects(self):
        self.assertEqual("DRAWDOWN", RiskEngine().decide(self.intent, Decimal("0"), Decimal("0"), Decimal("1")).reason)

    def test_execution_uses_next_open(self):
        decision = RiskEngine().decide(self.intent, Decimal("0"), Decimal("0"), Decimal("0"))
        execution = ControlledPaperExecution(self.market)
        order = execution.order(self.intent, decision)
        fill = execution.fill(order, Decimal("100000"))
        self.assertEqual(self.market.bar("S01", order.execution_date).open, fill.price)
        self.assertGreater(fill.execution_date, self.intent.signal_date)

    def test_ledger_idempotent_replay(self):
        ledger = AppendOnlyLedger()
        event = ledger.append("e1", "TEST", date(2024, 1, 1), {"a": 1})
        self.assertEqual(event, ledger.append("e1", "TEST", date(2024, 1, 1), {"a": 1}))
        self.assertEqual(1, len(ledger.events))

    def test_ledger_conflict_fails_closed(self):
        ledger = AppendOnlyLedger()
        ledger.append("e1", "TEST", date(2024, 1, 1), {"a": 1})
        with self.assertRaises(RuntimeError):
            ledger.append("e1", "TEST", date(2024, 1, 1), {"a": 2})

    def test_ledger_restart_roundtrip(self):
        ledger = AppendOnlyLedger()
        ledger.append("e1", "TEST", date(2024, 1, 1), {"a": 1})
        path = Path.cwd() / ".v10-ledger-roundtrip.jsonl"
        try:
            ledger.save(path)
            self.assertEqual(ledger.events, AppendOnlyLedger.load(path).events)
        finally:
            path.unlink(missing_ok=True)

    def test_ledger_rewrite_forbidden(self):
        path = Path.cwd() / ".v10-ledger-rewrite.jsonl"
        try:
            ledger = AppendOnlyLedger()
            ledger.save(path)
            with self.assertRaises(RuntimeError):
                ledger.save(path)
        finally:
            path.unlink(missing_ok=True)

    def test_ledger_restart_can_append_verified_suffix(self):
        path = Path.cwd() / ".v10-ledger-append.jsonl"
        try:
            ledger = AppendOnlyLedger()
            ledger.append("e1", "TEST", date(2024, 1, 1), {"a": 1})
            ledger.persist(path)
            restarted = AppendOnlyLedger.load(path)
            restarted.append("e2", "TEST", date(2024, 1, 2), {"a": 2})
            restarted.persist(path)
            self.assertEqual(restarted.events, AppendOnlyLedger.load(path).events)
        finally:
            path.unlink(missing_ok=True)

    def test_accounting_identity(self):
        ledger = AppendOnlyLedger()
        ledger.append("f1", "PAPER_FILL", date(2024, 1, 2),
                      {"fill_id": "f1", "symbol": "S01", "quantity": 10, "price": 100, "fee": 1})
        state = replay_account(ledger.events, Decimal("10000"))
        mv, equity = mark_to_market(state, {"S01": Decimal("110")})
        self.assertEqual(state.cash + mv, equity)


class ResearchPipelineTests(unittest.TestCase):
    def test_step8_remains_failed(self):
        self.assertEqual("FAIL", SEALED_STEP8.robustness_gate)
        self.assertLess(SEALED_STEP8.median_excess_return_pct, 0)

    def test_chronological_split(self):
        dates = tuple(date(2024, 1, 1) + timedelta(days=i) for i in range(10))
        split = chronological_split(dates)
        self.assertLess(max(split.train), min(split.validation))
        self.assertLess(max(split.validation), min(split.test))

    def test_weak_strategy_not_promoted(self):
        evidence = PromotionEvidence(Decimal("1"), Decimal("-0.01"), Decimal("2"), Decimal("0.1"),
                                     Decimal("1"), True, True, True, True)
        self.assertFalse(promotion_allowed(evidence))

    def test_strong_complete_evidence_promoted(self):
        evidence = PromotionEvidence(Decimal("0.1"), Decimal("0.02"), Decimal("1.2"), Decimal("0.1"),
                                     Decimal("1"), True, True, True, True)
        self.assertTrue(promotion_allowed(evidence))

    def test_portfolio_top_n_is_fixed(self):
        with self.assertRaises(ValueError):
            PortfolioConstructor().equal_weight((), date.today(), 7)

    def test_unpromoted_pipeline_fails_closed(self):
        ledger = AppendOnlyLedger()
        pipeline = ManualDailyPaperPipeline(TrustedMarketData(bars()), ledger, Decimal("1000000"))
        with self.assertRaises(RuntimeError):
            pipeline.run(date(2024, 3, 20))
        self.assertEqual((), ledger.events)

    def test_performance_metrics(self):
        curve = ((date(2024, 1, 1), Decimal("100")), (date(2024, 1, 2), Decimal("110")),
                 (date(2024, 1, 3), Decimal("105")))
        metrics = performance(curve, Decimal("0.2"), (Decimal("0.5"), Decimal("0.6")))
        self.assertEqual(Decimal("0.05"), metrics.total_return)
        self.assertGreater(metrics.max_drawdown, 0)

    def test_portfolio_backtest_preserves_daily_identity(self):
        market = TrustedMarketData(bars())
        intent = StrategyIntent("S01", date(2024, 1, 10), Decimal("0.2"), "BACKTEST")
        sessions = tuple(date(2024, 1, 10) + timedelta(days=i) for i in range(1, 20))
        result = PortfolioBacktest(market).run((intent,), sessions)
        self.assertTrue(all(row.cash + row.market_value == row.equity for row in result.daily))
        self.assertGreater(result.metrics.total_return, Decimal("-1"))

    def test_backtest_rejects_unsorted_sessions(self):
        with self.assertRaises(ValueError):
            PortfolioBacktest(TrustedMarketData(bars())).run((), (date(2024, 1, 2), date(2024, 1, 1)))

    def test_buy_and_hold_uses_trusted_closes(self):
        value = buy_and_hold_return(TrustedMarketData(bars()), "S01", date(2024, 1, 1), date(2024, 3, 1))
        self.assertGreater(value, 0)

    def test_reporting_contract_is_paper_labeled(self):
        ledger = AppendOnlyLedger()
        ledger.append("f1", "PAPER_FILL", date(2024, 1, 2),
                      {"fill_id": "f1", "symbol": "S01", "quantity": 10, "price": 100, "fee": 1})
        state = replay_account(ledger.events, Decimal("10000"))
        report = build_report(date(2024, 1, 3), state, {"S01": Decimal("110")},
                              Decimal("10000"), Decimal("10100"), universe=("S01",))
        self.assertEqual("PAPER TRADING", report.label)
        self.assertEqual(report.cash + Decimal("1100"), report.equity)


class GeneratedBoundaryTests(unittest.TestCase):
    """Distinct deterministic boundary vectors; generated to keep the matrix auditable."""


def _invalid_bar_test(index):
    def test(self):
        base = bars(symbols=(f"X{index:02d}",), days=1)[0]
        if index % 4 == 0:
            candidate = replace(base, volume=0)
        elif index % 4 == 1:
            candidate = replace(base, synthetic=True)
        elif index % 4 == 2:
            candidate = replace(base, provider="")
        else:
            candidate = replace(base, state=ObservationState.INVALID)
        with self.assertRaises(ValueError):
            TrustedMarketData((candidate,))
    return test


def _risk_vector_test(index):
    def test(self):
        requested = Decimal(index + 1) / Decimal("100")
        intent = StrategyIntent(f"R{index:02d}", date(2024, 1, 1), requested, "VECTOR")
        decision = RiskEngine().decide(intent, Decimal("0"), Decimal("0"), Decimal("0"))
        self.assertGreaterEqual(decision.approved_weight, 0)
        self.assertLessEqual(decision.approved_weight, requested)
        self.assertLessEqual(decision.approved_weight, Decimal("0.20"))
    return test


def _ledger_vector_test(index):
    def test(self):
        ledger = AppendOnlyLedger()
        for number in range(index + 1):
            ledger.append(f"E{index}-{number}", "VECTOR", date(2024, 1, 1), {"number": number})
        replayed = AppendOnlyLedger(ledger.events)
        self.assertEqual(ledger.events, replayed.events)
        self.assertEqual(index + 1, ledger.events[-1].sequence)
    return test


def _point_in_time_test(index):
    def test(self):
        market = TrustedMarketData(bars(symbols=(f"P{index:02d}",), days=80))
        cutoff = date(2024, 2, 1) + timedelta(days=index % 20)
        self.assertTrue(all(bar.session_date <= cutoff for bar in market.history(f"P{index:02d}", cutoff)))
        self.assertTrue(all(bar.session_date > cutoff for bar in market.history(f"P{index:02d}") if bar not in market.history(f"P{index:02d}", cutoff)))
    return test


for _index in range(25):
    setattr(GeneratedBoundaryTests, f"test_invalid_market_vector_{_index:02d}", _invalid_bar_test(_index))
    setattr(GeneratedBoundaryTests, f"test_risk_vector_{_index:02d}", _risk_vector_test(_index))
    setattr(GeneratedBoundaryTests, f"test_ledger_vector_{_index:02d}", _ledger_vector_test(_index))
    setattr(GeneratedBoundaryTests, f"test_point_in_time_vector_{_index:02d}", _point_in_time_test(_index))


if __name__ == "__main__":
    unittest.main()
