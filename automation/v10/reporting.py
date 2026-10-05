from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .ledger import AccountState, mark_to_market


@dataclass(frozen=True)
class PaperReportingContract:
    as_of: date
    label: str
    equity: Decimal
    cash: Decimal
    positions: tuple[tuple[str, int], ...]
    daily_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    drawdown: Decimal
    orders: tuple[str, ...]
    fills: tuple[str, ...]
    strategy_signals: tuple[str, ...]
    universe: tuple[str, ...]
    ranked_candidates: tuple[str, ...]
    risk_decisions: tuple[str, ...]


def build_report(as_of: date, state: AccountState, prices: dict[str, Decimal],
                 prior_equity: Decimal, peak_equity: Decimal, **lineage) -> PaperReportingContract:
    market_value, equity = mark_to_market(state, prices)
    costs = dict(state.average_costs)
    unrealized = sum(((prices[symbol] - costs[symbol]) * quantity
                      for symbol, quantity in state.positions), Decimal("0"))
    return PaperReportingContract(
        as_of=as_of, label="PAPER TRADING", equity=equity, cash=state.cash,
        positions=state.positions, daily_pnl=equity - prior_equity,
        realized_pnl=state.realized_pnl, unrealized_pnl=unrealized,
        drawdown=(peak_equity - equity) / peak_equity if peak_equity else Decimal("0"),
        orders=tuple(lineage.get("orders", ())), fills=tuple(lineage.get("fills", ())),
        strategy_signals=tuple(lineage.get("strategy_signals", ())),
        universe=tuple(lineage.get("universe", ())),
        ranked_candidates=tuple(lineage.get("ranked_candidates", ())),
        risk_decisions=tuple(lineage.get("risk_decisions", ())),
    )
