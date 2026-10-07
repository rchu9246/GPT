"""Forward-only accounting contract for the gptq shadow-paper lineage.

This module deliberately has no broker interface. Database transactions are
implemented by the matching Supabase migration; the pure functions here are
also used by deterministic tests and by the future accounting publisher.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Literal

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False

CENT = Decimal("0.01")
EVENT_TYPES = frozenset({"INITIALIZATION", "BUY", "SELL", "CASH_ADJUSTMENT", "MARK_TO_MARKET"})


def dec(value: object) -> Decimal:
    return Decimal(str(value))


def money(value: object) -> Decimal:
    return dec(value).quantize(CENT, rounding=ROUND_HALF_UP)


def digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Event:
    key: str
    kind: Literal["INITIALIZATION", "BUY", "SELL", "CASH_ADJUSTMENT", "MARK_TO_MARKET"]
    business_date: date
    cash_delta: Decimal = Decimal("0")
    trade_realized_pnl: Decimal = Decimal("0")
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    notional: Decimal = Decimal("0")
    buy_commission: Decimal = Decimal("0")
    sell_commission: Decimal = Decimal("0")
    transaction_tax: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    authorized_adjustment: bool = False

    def normalized(self) -> "Event":
        if not self.key or self.kind not in EVENT_TYPES:
            raise ValueError("event identity or type is invalid")
        fields = ("cash_delta", "trade_realized_pnl", "notional", "buy_commission",
                  "sell_commission", "transaction_tax", "slippage", "cost_basis")
        result = replace(self, **{name: money(getattr(self, name)) for name in fields})
        if self.market_value is not None:
            result = replace(result, market_value=money(self.market_value))
        if self.unrealized_pnl is not None:
            result = replace(result, unrealized_pnl=money(self.unrealized_pnl))
        if any(getattr(result, name) < 0 for name in
               ("notional", "buy_commission", "sell_commission", "transaction_tax", "cost_basis")):
            raise ValueError("negative transaction amount")
        if result.kind == "BUY":
            expected = -result.notional - result.buy_commission
            if abs(result.cash_delta - expected) > CENT:
                raise ValueError("BUY cash does not include notional and commission")
            if result.trade_realized_pnl:
                raise ValueError("BUY cannot realize P&L")
        elif result.kind == "SELL":
            expected = result.notional - result.sell_commission - result.transaction_tax
            if abs(result.cash_delta - expected) > CENT:
                raise ValueError("SELL cash does not include exit costs")
            if abs(result.trade_realized_pnl - (expected - result.cost_basis)) > CENT:
                raise ValueError("SELL realized P&L disagrees with cost basis")
        elif result.kind == "CASH_ADJUSTMENT":
            if not result.authorized_adjustment:
                raise ValueError("cash adjustment requires explicit authorization")
        elif result.kind == "MARK_TO_MARKET":
            if result.market_value is None or result.unrealized_pnl is None or result.cash_delta:
                raise ValueError("mark-to-market requires values and cannot move cash")
        return result

    def content_hash(self) -> str:
        return digest(self.normalized().__dict__)


@dataclass(frozen=True)
class State:
    strategy_version: str
    business_date: date
    accounting_state_version: int
    owner_run_id: int | None
    owner_run_attempt: int | None
    opening_cash: Decimal
    closing_cash: Decimal
    market_value: Decimal
    total_equity: Decimal
    daily_realized_pnl: Decimal
    cumulative_realized_pnl: Decimal
    unrealized_pnl: Decimal
    state_hash: str
    finalized: bool = False


def state_hash(state: State) -> str:
    fields = {k: v for k, v in state.__dict__.items() if k not in {"state_hash", "finalized"}}
    return digest(fields)


class AccountingLineage:
    """Deterministic model of the SQL transaction contract.

    The production store must lock the lineage, event and state rows in one
    transaction. This class is for contract verification, never live writes.
    """

    def __init__(self, strategy_version: str):
        if not strategy_version:
            raise ValueError("strategy_version required")
        self.strategy_version = strategy_version
        self.states: dict[date, State] = {}
        self.events: dict[str, str] = {}

    def initialize(self, business_date: date, cash: object, market_value: object,
                   unrealized_pnl: object, *, owner_run_id: int | None = None,
                   owner_run_attempt: int | None = None, event_key: str) -> State:
        if self.states or self.events:
            raise ValueError("accounting lineage already initialized")
        cash, mv, upnl = money(cash), money(market_value), money(unrealized_pnl)
        if cash < 0 or mv < 0:
            raise ValueError("opening values must be nonnegative")
        event = Event(event_key, "INITIALIZATION", business_date, market_value=mv,
                      unrealized_pnl=upnl).normalized()
        state = State(self.strategy_version, business_date, 1, owner_run_id,
                      owner_run_attempt, cash, cash, mv, money(cash + mv),
                      Decimal("0.00"), Decimal("0.00"), upnl, "")
        state = replace(state, state_hash=state_hash(state))
        self.states[business_date] = state
        self.events[event.key] = event.content_hash()
        return state

    def apply(self, event: Event, *, owner_run_id: int | None = None,
              owner_run_attempt: int | None = None) -> State:
        event = event.normalized()
        prior_hash = self.events.get(event.key)
        if prior_hash is not None:
            if prior_hash != event.content_hash():
                raise ValueError("event key reused with different financial content")
            return self.states[event.business_date]
        if not self.states:
            raise ValueError("missing prior state; initial capital fallback forbidden")
        latest_date = max(self.states)
        if event.business_date < latest_date:
            raise ValueError("historical rewrite forbidden")
        if event.business_date > latest_date:
            previous = self.states[latest_date]
            if not previous.finalized:
                raise ValueError("prior business date not finalized")
            state = State(self.strategy_version, event.business_date,
                          previous.accounting_state_version + 1, owner_run_id,
                          owner_run_attempt, previous.closing_cash,
                          previous.closing_cash, previous.market_value,
                          previous.total_equity, Decimal("0.00"),
                          previous.cumulative_realized_pnl,
                          previous.unrealized_pnl, "")
        else:
            state = self.states[latest_date]
            if state.finalized:
                raise ValueError("finalized financial state is immutable")
        if event.kind == "INITIALIZATION":
            raise ValueError("initialization cannot happen twice")
        closing_cash = money(state.closing_cash + event.cash_delta)
        if closing_cash < 0:
            raise ValueError("negative cash")
        mv = state.market_value if event.market_value is None else event.market_value
        upnl = state.unrealized_pnl if event.unrealized_pnl is None else event.unrealized_pnl
        updated = replace(state, closing_cash=closing_cash, market_value=mv,
                          total_equity=money(closing_cash + mv),
                          daily_realized_pnl=money(state.daily_realized_pnl + event.trade_realized_pnl),
                          cumulative_realized_pnl=money(state.cumulative_realized_pnl + event.trade_realized_pnl),
                          unrealized_pnl=upnl, owner_run_id=owner_run_id,
                          owner_run_attempt=owner_run_attempt)
        updated = replace(updated, state_hash=state_hash(updated))
        self.states[event.business_date] = updated
        self.events[event.key] = event.content_hash()
        return updated

    def finalize(self, business_date: date, *, expected_equity: object,
                 expected_cash: object, expected_market_value: object,
                 expected_unrealized_pnl: object, expected_daily_realized_pnl: object) -> State:
        state = self.states[business_date]
        expected = (money(expected_cash), money(expected_market_value),
                    money(expected_equity), money(expected_unrealized_pnl),
                    money(expected_daily_realized_pnl))
        actual = (state.closing_cash, state.market_value, state.total_equity,
                  state.unrealized_pnl, state.daily_realized_pnl)
        if any(abs(a - b) > CENT for a, b in zip(actual, expected)):
            raise ValueError("publication disagrees with committed accounting state")
        if abs(state.total_equity - state.closing_cash - state.market_value) > CENT:
            raise ValueError("equity identity failed")
        finalized = replace(state, finalized=True)
        self.states[business_date] = finalized
        return finalized
