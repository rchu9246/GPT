from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import pstdev

from .market_data import TrustedMarketData
from .universe import UniverseSnapshot


FACTOR_NAMES = ("trend", "momentum", "relative_strength", "liquidity", "low_volatility", "breakout")
FACTOR_VERSION = "V10_OHLCV_FACTORS_V1"

HYPOTHESIS_WEIGHTS = {
    "H1_EQUAL_FACTOR": {name: Decimal("1") for name in FACTOR_NAMES},
    "H2_TREND_MOMENTUM": {
        "trend": Decimal("2"), "momentum": Decimal("2"),
        "relative_strength": Decimal("1"), "liquidity": Decimal("1"),
        "low_volatility": Decimal("1"), "breakout": Decimal("1"),
    },
    "H3_RISK_ADJUSTED": {
        "trend": Decimal("1"), "momentum": Decimal("1"),
        "relative_strength": Decimal("1"), "liquidity": Decimal("1"),
        "low_volatility": Decimal("3"), "breakout": Decimal("1"),
    },
}


@dataclass(frozen=True)
class RankedCandidate:
    symbol: str
    as_of: date
    raw: tuple[tuple[str, Decimal], ...]
    normalized: tuple[tuple[str, Decimal], ...]
    composite: Decimal
    rank: int


def _returns(closes: list[Decimal]) -> list[float]:
    return [float(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]


class MultiFactorRankingEngine:
    def __init__(self, market: TrustedMarketData, lookback: int = 20):
        if lookback < 5:
            raise ValueError("lookback too short")
        self._market = market
        self._lookback = lookback

    def _raw(self, symbol: str, as_of: date) -> dict[str, Decimal]:
        bars = list(self._market.history(symbol, as_of))[-self._lookback:]
        if len(bars) < self._lookback:
            raise ValueError("insufficient factor history")
        closes = [b.close for b in bars]
        avg = sum(closes, Decimal("0")) / len(closes)
        returns = _returns(closes)
        volatility = Decimal(str(pstdev(returns))) if len(returns) > 1 else Decimal("0")
        return {
            "trend": closes[-1] / avg - 1,
            "momentum": closes[-1] / closes[0] - 1,
            "relative_strength": closes[-1] / closes[-6] - 1,
            "liquidity": sum((b.close * b.volume for b in bars), Decimal("0")) / len(bars),
            "low_volatility": -volatility,
            "breakout": closes[-1] / max(closes[:-1]) - 1,
        }

    def rank(self, universe: UniverseSnapshot,
             hypothesis: str = "H1_EQUAL_FACTOR") -> tuple[RankedCandidate, ...]:
        if hypothesis not in HYPOTHESIS_WEIGHTS:
            raise ValueError("unknown pre-registered hypothesis")
        raw = {symbol: self._raw(symbol, universe.as_of) for symbol in universe.symbols}
        if not raw:
            return ()
        normalized: dict[str, dict[str, Decimal]] = {symbol: {} for symbol in raw}
        for factor in FACTOR_NAMES:
            ordered = sorted(raw, key=lambda symbol: (raw[symbol][factor], symbol))
            denominator = max(1, len(ordered) - 1)
            for index, symbol in enumerate(ordered):
                normalized[symbol][factor] = Decimal(index) / Decimal(denominator)
        scored = []
        for symbol in sorted(raw):
            weights = HYPOTHESIS_WEIGHTS[hypothesis]
            composite = (sum((normalized[symbol][name] * weights[name] for name in FACTOR_NAMES),
                             Decimal("0")) / sum(weights.values(), Decimal("0")))
            scored.append((symbol, composite))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return tuple(RankedCandidate(
            symbol=symbol, as_of=universe.as_of,
            raw=tuple((name, raw[symbol][name]) for name in FACTOR_NAMES),
            normalized=tuple((name, normalized[symbol][name]) for name in FACTOR_NAMES),
            composite=composite, rank=index,
        ) for index, (symbol, composite) in enumerate(scored, 1))
