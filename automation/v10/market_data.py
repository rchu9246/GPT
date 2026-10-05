from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from .halt_authority import RepositoryHaltAuthority
from .models import MarketBar


class TrustedMarketData:
    """Validated immutable view of provider bars with repository halt checks."""

    def __init__(self, bars: Iterable[MarketBar]):
        # There is deliberately no authority/evidence parameter: callers cannot
        # provide, replace, or confirm trusted halt state.
        authority = RepositoryHaltAuthority()
        grouped: dict[str, list[MarketBar]] = defaultdict(list)
        seen: set[tuple[str, date]] = set()
        for bar in bars:
            bar.validate()
            key = (bar.symbol, bar.session_date)
            if key in seen:
                raise ValueError("duplicate market observation")
            if authority.decision(*key).confirmed_halt:
                raise ValueError("confirmed halted observation cannot be tradable")
            seen.add(key)
            grouped[bar.symbol].append(bar)
        self._bars = {symbol: tuple(sorted(values, key=lambda b: b.session_date))
                      for symbol, values in grouped.items()}

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._bars))

    def history(self, symbol: str, through: date | None = None) -> tuple[MarketBar, ...]:
        values = self._bars.get(symbol, ())
        if through is None:
            return values
        return tuple(bar for bar in values if bar.session_date <= through)

    def bar(self, symbol: str, session_date: date) -> MarketBar | None:
        return next((bar for bar in self._bars.get(symbol, ()) if bar.session_date == session_date), None)

    def next_tradable_bar(self, symbol: str, after: date) -> MarketBar | None:
        return next((bar for bar in self._bars.get(symbol, ()) if bar.session_date > after), None)
