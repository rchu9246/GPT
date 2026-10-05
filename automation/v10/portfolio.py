from __future__ import annotations

from datetime import date
from decimal import Decimal

from .factors import RankedCandidate
from .models import StrategyIntent


class PortfolioConstructor:
    ALLOWED_TOP_N = (5, 10, 20)

    def equal_weight(self, ranked: tuple[RankedCandidate, ...], as_of: date,
                     top_n: int) -> tuple[StrategyIntent, ...]:
        if top_n not in self.ALLOWED_TOP_N:
            raise ValueError("top_n must be a fixed research candidate")
        selected = ranked[:top_n]
        if not selected:
            return ()
        weight = Decimal("1") / Decimal(len(selected))
        return tuple(StrategyIntent(item.symbol, as_of, weight,
                                    f"V10_MULTIFACTOR:{as_of.isoformat()}:{item.rank}")
                     for item in selected)
