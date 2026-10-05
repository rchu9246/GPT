from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .execution import ControlledPaperExecution
from .factors import MultiFactorRankingEngine, RankedCandidate
from .ledger import AppendOnlyLedger
from .market_data import TrustedMarketData
from .models import PaperFill, RiskDecision
from .portfolio import PortfolioConstructor
from .risk import RiskEngine
from .research import PROMOTED_PAPER_STRATEGIES
from .safety import SAFETY
from .universe import UniverseProvider, UniverseSnapshot


@dataclass(frozen=True)
class DailyPaperReport:
    as_of: date
    label: str
    universe: UniverseSnapshot
    ranked_candidates: tuple[RankedCandidate, ...]
    risk_decisions: tuple[RiskDecision, ...]
    fills: tuple[PaperFill, ...]
    broker_orders_created: int = 0


class ManualDailyPaperPipeline:
    """Manual-only V10 composition root. It has no scheduler or broker adapter."""

    def __init__(self, market: TrustedMarketData, ledger: AppendOnlyLedger,
                 initial_equity: Decimal):
        SAFETY.assert_safe()
        if initial_equity <= 0:
            raise ValueError("initial equity must be positive")
        self.market = market
        self.ledger = ledger
        self.initial_equity = initial_equity

    def run(self, as_of: date, top_n: int = 5) -> DailyPaperReport:
        if "V10_MULTIFACTOR" not in PROMOTED_PAPER_STRATEGIES:
            raise RuntimeError("no V10 paper strategy has passed the promotion gate")
        universe = UniverseProvider(self.market).snapshot(as_of)
        ranked = MultiFactorRankingEngine(self.market).rank(universe)
        intents = PortfolioConstructor().equal_weight(ranked, as_of, top_n)
        risk, execution = RiskEngine(), ControlledPaperExecution(self.market)
        decisions, fills = [], []
        exposure = Decimal("0")
        for intent in intents:
            decision = risk.decide(intent, exposure, Decimal("0"), Decimal("0"), True)
            decisions.append(decision)
            exposure += decision.approved_weight
            order = execution.order(intent, decision)
            if order is None:
                continue
            fill = execution.fill(order, self.initial_equity)
            self.ledger.append(fill.fill_id, "PAPER_FILL", fill.execution_date, {
                "fill_id": fill.fill_id, "symbol": fill.symbol, "quantity": fill.quantity,
                "price": fill.price, "fee": fill.fee, "lineage": fill.lineage,
            })
            fills.append(fill)
        return DailyPaperReport(as_of, "PAPER TRADING", universe, ranked,
                                tuple(decisions), tuple(fills))
