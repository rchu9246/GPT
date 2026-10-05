from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from .market_data import TrustedMarketData


class UniverseExclusionReason(str, Enum):
    INVALID_SYMBOL = "INVALID_SYMBOL"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INVALID_CURRENT_OBSERVATION = "INVALID_CURRENT_OBSERVATION"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    INVALID_PRICE = "INVALID_PRICE"
    NOT_TRADABLE = "NOT_TRADABLE"
    CONFIRMED_HALT = "CONFIRMED_HALT"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"


@dataclass(frozen=True)
class UniverseEligibility:
    symbol: str
    eligible: bool
    observations: int
    median_turnover: Decimal
    reasons: tuple[UniverseExclusionReason, ...]


@dataclass(frozen=True)
class UniverseSnapshot:
    as_of: date
    symbols: tuple[str, ...]
    eligibility: tuple[UniverseEligibility, ...]
    point_in_time_safe: bool = True
    survivorship_bias_limitation: str = (
        "Historical constituent completeness is not established for this provider."
    )

    @property
    def requested_count(self) -> int:
        return len(self.eligibility)

    @property
    def valid_count(self) -> int:
        return len(self.symbols)

    @property
    def excluded_count(self) -> int:
        return self.requested_count - self.valid_count


class UniverseProvider:
    def __init__(self, market: TrustedMarketData, minimum_observations: int = 60,
                 minimum_median_turnover: Decimal = Decimal("1000000"),
                 point_in_time_membership_complete: bool = False):
        if minimum_observations < 2 or minimum_median_turnover < 0:
            raise ValueError("invalid universe policy")
        self._market = market
        self._minimum_observations = minimum_observations
        self._minimum_turnover = minimum_median_turnover
        self._membership_complete = point_in_time_membership_complete

    def snapshot(self, as_of: date) -> UniverseSnapshot:
        decisions = []
        for symbol in self._market.symbols:
            history = self._market.history(symbol, as_of)
            reasons = []
            if len(history) < self._minimum_observations:
                reasons.append(UniverseExclusionReason.INSUFFICIENT_HISTORY)
            turnovers = sorted(bar.close * bar.volume for bar in history)
            median = (turnovers[(len(turnovers) - 1) // 2] if turnovers else Decimal("0"))
            if median < self._minimum_turnover:
                reasons.append(UniverseExclusionReason.INSUFFICIENT_LIQUIDITY)
            decisions.append(UniverseEligibility(symbol, not reasons, len(history), median, tuple(reasons)))
        eligible = tuple(sorted(d.symbol for d in decisions if d.eligible))
        limitation = ("NONE: membership is reconstructed from the complete official daily TWSE security table."
                      if self._membership_complete else
                      "Historical constituent completeness is not established for this provider.")
        return UniverseSnapshot(as_of, eligible, tuple(sorted(decisions, key=lambda d: d.symbol)),
                                point_in_time_safe=True, survivorship_bias_limitation=limitation)
