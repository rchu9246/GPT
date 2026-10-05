from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .execution import ControlledPaperExecution
from .ledger import AppendOnlyLedger, mark_to_market, replay_account
from .market_data import TrustedMarketData
from .models import StrategyIntent
from .research import PerformanceMetrics, performance
from .risk import RiskEngine


@dataclass(frozen=True)
class DailyEquity:
    session_date: date
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    exposure: Decimal


@dataclass(frozen=True)
class BacktestResult:
    daily: tuple[DailyEquity, ...]
    metrics: PerformanceMetrics
    ledger: AppendOnlyLedger


class PortfolioBacktest:
    """Long-only next-tradable-open backtest using the canonical event ledger."""

    def __init__(self, market: TrustedMarketData, initial_cash: Decimal = Decimal("1000000")):
        if initial_cash <= 0:
            raise ValueError("initial cash must be positive")
        self.market = market
        self.initial_cash = initial_cash

    def run(self, intents: tuple[StrategyIntent, ...], sessions: tuple[date, ...]) -> BacktestResult:
        if tuple(sorted(set(sessions))) != sessions:
            raise ValueError("sessions must be unique and chronological")
        ledger, risk, execution = AppendOnlyLedger(), RiskEngine(), ControlledPaperExecution(self.market)
        exposure = Decimal("0")
        turnover = Decimal("0")
        for intent in sorted(intents, key=lambda item: (item.signal_date, item.symbol)):
            decision = risk.decide(intent, exposure, Decimal("0"), Decimal("0"), True)
            exposure += decision.approved_weight
            order = execution.order(intent, decision)
            if order is None or order.execution_date not in sessions:
                continue
            fill = execution.fill(order, self.initial_cash)
            ledger.append(fill.fill_id, "PAPER_FILL", fill.execution_date, {
                "fill_id": fill.fill_id, "symbol": fill.symbol, "quantity": fill.quantity,
                "price": fill.price, "fee": fill.fee, "lineage": fill.lineage,
            })
            turnover += fill.price * fill.quantity / self.initial_cash
        daily = []
        for session in sessions:
            state = replay_account((event for event in ledger.events if event.event_date <= session), self.initial_cash)
            prices = {}
            for symbol, _ in state.positions:
                history = self.market.history(symbol, session)
                if not history:
                    raise RuntimeError("position lacks trusted mark")
                prices[symbol] = history[-1].close
            market_value, equity = mark_to_market(state, prices)
            if state.cash + market_value != equity:
                raise RuntimeError("accounting identity failure")
            daily.append(DailyEquity(session, state.cash, market_value, equity,
                                     market_value / equity if equity else Decimal("0")))
        curve = tuple((row.session_date, row.equity) for row in daily)
        metrics = performance(curve, turnover, tuple(row.exposure for row in daily))
        return BacktestResult(tuple(daily), metrics, ledger)


def buy_and_hold_return(market: TrustedMarketData, symbol: str, start: date, end: date) -> Decimal:
    values = [bar.close for bar in market.history(symbol, end) if bar.session_date >= start]
    if len(values) < 2:
        raise ValueError("benchmark history unavailable")
    return values[-1] / values[0] - 1
