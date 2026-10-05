from dataclasses import dataclass
from decimal import Decimal

from .models import RiskDecision, StrategyIntent


@dataclass(frozen=True)
class RiskPolicy:
    max_position_weight: Decimal = Decimal("0.20")
    max_portfolio_exposure: Decimal = Decimal("0.90")
    cash_reserve: Decimal = Decimal("0.10")
    maximum_volatility: Decimal = Decimal("0.08")
    maximum_drawdown: Decimal = Decimal("0.25")


class RiskEngine:
    def __init__(self, policy: RiskPolicy = RiskPolicy()):
        if policy.max_portfolio_exposure + policy.cash_reserve > 1:
            raise ValueError("exposure and reserve are inconsistent")
        self.policy = policy

    def decide(self, intent: StrategyIntent, current_exposure: Decimal,
               volatility: Decimal, drawdown: Decimal, liquid: bool = True) -> RiskDecision:
        if intent.target_weight <= 0:
            return RiskDecision(intent.symbol, intent.target_weight, Decimal("0"), "REJECT", "LONG_ONLY")
        if not liquid:
            return RiskDecision(intent.symbol, intent.target_weight, Decimal("0"), "REJECT", "LIQUIDITY")
        if volatility > self.policy.maximum_volatility:
            return RiskDecision(intent.symbol, intent.target_weight, Decimal("0"), "REJECT", "VOLATILITY")
        if drawdown > self.policy.maximum_drawdown:
            return RiskDecision(intent.symbol, intent.target_weight, Decimal("0"), "REJECT", "DRAWDOWN")
        room = max(Decimal("0"), self.policy.max_portfolio_exposure - current_exposure)
        approved = min(intent.target_weight, self.policy.max_position_weight, room)
        decision = "APPROVE" if approved == intent.target_weight else ("REDUCE" if approved > 0 else "REJECT")
        return RiskDecision(intent.symbol, intent.target_weight, approved, decision,
                            "WITHIN_POLICY" if decision == "APPROVE" else "EXPOSURE_LIMIT")
