from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LedgerEvent:
    sequence: int
    event_id: str
    event_type: str
    event_date: date
    payload: tuple[tuple[str, str], ...]
    previous_hash: str
    event_hash: str

    @staticmethod
    def create(sequence: int, event_id: str, event_type: str, event_date: date,
               payload: dict[str, object], previous_hash: str) -> "LedgerEvent":
        canonical_payload = tuple(sorted((key, str(value)) for key, value in payload.items()))
        body = json.dumps({"sequence": sequence, "event_id": event_id, "event_type": event_type,
                           "event_date": event_date.isoformat(), "payload": canonical_payload,
                           "previous_hash": previous_hash}, separators=(",", ":"), sort_keys=True)
        return LedgerEvent(sequence, event_id, event_type, event_date, canonical_payload,
                           previous_hash, hashlib.sha256(body.encode()).hexdigest())

    def verify(self, previous_hash: str, sequence: int) -> None:
        expected = LedgerEvent.create(sequence, self.event_id, self.event_type,
                                      self.event_date, dict(self.payload), previous_hash)
        if self != expected:
            raise RuntimeError("ledger integrity failure")


class AppendOnlyLedger:
    def __init__(self, events: Iterable[LedgerEvent] = ()):
        self._events: list[LedgerEvent] = []
        self._ids: set[str] = set()
        for event in events:
            self._append_existing(event)

    def _append_existing(self, event: LedgerEvent) -> None:
        if event.event_id in self._ids:
            raise RuntimeError("duplicate event")
        previous = self._events[-1].event_hash if self._events else "GENESIS"
        event.verify(previous, len(self._events) + 1)
        self._events.append(event)
        self._ids.add(event.event_id)

    def append(self, event_id: str, event_type: str, event_date: date,
               payload: dict[str, object]) -> LedgerEvent:
        if event_id in self._ids:
            existing = next(event for event in self._events if event.event_id == event_id)
            candidate = LedgerEvent.create(existing.sequence, event_id, event_type, event_date,
                                           payload, existing.previous_hash)
            if candidate != existing:
                raise RuntimeError("conflicting event replay")
            return existing
        previous = self._events[-1].event_hash if self._events else "GENESIS"
        event = LedgerEvent.create(len(self._events) + 1, event_id, event_type, event_date,
                                   payload, previous)
        self._append_existing(event)
        return event

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events)

    def save(self, path: Path) -> None:
        if path.exists():
            raise RuntimeError("historical rewrite forbidden")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            for event in self._events:
                row = asdict(event)
                row["event_date"] = event.event_date.isoformat()
                handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")

    def persist(self, path: Path) -> None:
        """Append only events missing from a verified on-disk prefix."""
        if not path.exists():
            self.save(path)
            return
        persisted = self.load(path)
        prefix = persisted.events
        if self.events[:len(prefix)] != prefix or len(prefix) > len(self.events):
            raise RuntimeError("persisted ledger is not an exact event prefix")
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for event in self.events[len(prefix):]:
                row = asdict(event)
                row["event_date"] = event.event_date.isoformat()
                handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")

    @classmethod
    def load(cls, path: Path) -> "AppendOnlyLedger":
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            row["event_date"] = date.fromisoformat(row["event_date"])
            row["payload"] = tuple(tuple(item) for item in row["payload"])
            events.append(LedgerEvent(**row))
        return cls(events)


@dataclass(frozen=True)
class AccountState:
    cash: Decimal
    positions: tuple[tuple[str, int], ...]
    average_costs: tuple[tuple[str, Decimal], ...]
    realized_pnl: Decimal
    fees: Decimal


def replay_account(events: Iterable[LedgerEvent], initial_cash: Decimal) -> AccountState:
    cash = initial_cash
    positions: dict[str, int] = {}
    realized = Decimal("0")
    fees = Decimal("0")
    average_cost: dict[str, Decimal] = {}
    seen_fills: set[str] = set()
    for event in events:
        if event.event_type != "PAPER_FILL":
            continue
        payload = dict(event.payload)
        fill_id, symbol = payload["fill_id"], payload["symbol"]
        if fill_id in seen_fills:
            raise RuntimeError("duplicate fill")
        seen_fills.add(fill_id)
        quantity, price, fee = int(payload["quantity"]), Decimal(payload["price"]), Decimal(payload["fee"])
        old_qty = positions.get(symbol, 0)
        if old_qty + quantity < 0:
            raise RuntimeError("short position forbidden")
        if quantity > 0:
            new_qty = old_qty + quantity
            average_cost[symbol] = ((average_cost.get(symbol, Decimal("0")) * old_qty) + price * quantity) / new_qty
        elif quantity < 0:
            realized += (price - average_cost[symbol]) * (-quantity)
        cash -= price * quantity + fee
        fees += fee
        positions[symbol] = old_qty + quantity
        if positions[symbol] == 0:
            positions.pop(symbol)
            average_cost.pop(symbol, None)
    return AccountState(cash, tuple(sorted(positions.items())), tuple(sorted(average_cost.items())), realized, fees)


def mark_to_market(state: AccountState, prices: dict[str, Decimal]) -> tuple[Decimal, Decimal]:
    market_value = sum((prices[symbol] * quantity for symbol, quantity in state.positions), Decimal("0"))
    return market_value, state.cash + market_value
