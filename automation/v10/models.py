from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class ObservationState(str, Enum):
    TRADABLE = "TRADABLE"
    NON_TRADING = "NON_TRADING"
    INVALID = "INVALID"


@dataclass(frozen=True, order=True)
class MarketBar:
    symbol: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    state: ObservationState = ObservationState.TRADABLE
    provider: str = ""
    provider_observation_id: str = ""
    synthetic: bool = False

    def validate(self) -> None:
        if not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("invalid symbol")
        if self.synthetic:
            raise ValueError("synthetic market bars are forbidden")
        if not self.provider or not self.provider_observation_id:
            raise ValueError("provider lineage is required")
        if self.state is not ObservationState.TRADABLE:
            raise ValueError("bar is not tradable")
        if self.volume <= 0 or min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLCV must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("inconsistent OHLC")
        if self.low > self.high:
            raise ValueError("low exceeds high")


@dataclass(frozen=True)
class StrategyIntent:
    symbol: str
    signal_date: date
    target_weight: Decimal
    lineage: str


@dataclass(frozen=True)
class RiskDecision:
    symbol: str
    requested_weight: Decimal
    approved_weight: Decimal
    decision: str
    reason: str


@dataclass(frozen=True)
class PaperOrderIntent:
    symbol: str
    signal_date: date
    execution_date: date
    target_weight: Decimal
    lineage: str


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    symbol: str
    execution_date: date
    quantity: int
    price: Decimal
    fee: Decimal
    lineage: str
