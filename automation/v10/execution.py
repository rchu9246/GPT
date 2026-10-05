from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_DOWN

from .market_data import TrustedMarketData
from .models import PaperFill, PaperOrderIntent, RiskDecision, StrategyIntent


class ControlledPaperExecution:
    def __init__(self, market: TrustedMarketData, fee_rate: Decimal = Decimal("0.001")):
        if fee_rate < 0:
            raise ValueError("negative fee")
        self._market = market
        self._fee_rate = fee_rate

    def order(self, intent: StrategyIntent, decision: RiskDecision) -> PaperOrderIntent | None:
        if decision.symbol != intent.symbol or decision.requested_weight != intent.target_weight:
            raise ValueError("risk decision identity mismatch")
        if decision.approved_weight <= 0:
            return None
        bar = self._market.next_tradable_bar(intent.symbol, intent.signal_date)
        if bar is None:
            return None
        return PaperOrderIntent(intent.symbol, intent.signal_date, bar.session_date,
                                decision.approved_weight, intent.lineage)

    def fill(self, order: PaperOrderIntent, equity: Decimal) -> PaperFill:
        bar = self._market.bar(order.symbol, order.execution_date)
        if bar is None:
            raise ValueError("execution bar missing")
        quantity = int((equity * order.target_weight / bar.open).to_integral_value(rounding=ROUND_DOWN))
        if quantity <= 0:
            raise ValueError("paper order quantity is zero")
        fee = (bar.open * quantity * self._fee_rate).quantize(Decimal("0.0001"))
        identity = f"{order.symbol}|{order.signal_date}|{order.execution_date}|{quantity}|{bar.open}|{order.lineage}"
        fill_id = hashlib.sha256(identity.encode()).hexdigest()
        return PaperFill(fill_id, order.symbol, order.execution_date, quantity, bar.open, fee, order.lineage)
