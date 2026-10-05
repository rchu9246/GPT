"""Repository-owned halt authority.

Callers provide only symbol/date queries. They cannot supply confirmation state,
tokens, constructors, evidence objects, paths, or registry content.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "v10" / "halt_registry.json"
_REGISTRY_SHA256 = "38f89b9ded2cd19bcf2bcbcc1de8062ff91c5ef95622b34f019201fb358b61b9"


@dataclass(frozen=True)
class HaltDecision:
    symbol: str
    session_date: date
    confirmed_halt: bool
    evidence_id: str | None
    authority: str = "REPOSITORY_CONTROLLED"


class RepositoryHaltAuthority:
    """Loads one hash-pinned repository file; has no injectable trust inputs."""

    __slots__ = ("_halts",)

    def __init__(self) -> None:
        document = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(canonical).hexdigest() != _REGISTRY_SHA256:
            raise RuntimeError("halt registry integrity failure")
        if document != {"schema_version": 1, "authority": "REPOSITORY_CONTROLLED",
                        "confirmed_halts": document.get("confirmed_halts")}:
            raise RuntimeError("halt registry schema failure")
        halts: dict[tuple[str, date], str] = {}
        for entry in document["confirmed_halts"]:
            if set(entry) != {"symbol", "session_date", "evidence_id"}:
                raise RuntimeError("halt evidence schema failure")
            key = (entry["symbol"], date.fromisoformat(entry["session_date"]))
            if key in halts or not entry["evidence_id"]:
                raise RuntimeError("invalid halt evidence")
            halts[key] = entry["evidence_id"]
        self._halts = halts

    def decision(self, symbol: str, session_date: date) -> HaltDecision:
        if not symbol or symbol.strip() != symbol:
            raise ValueError("invalid symbol")
        evidence_id = self._halts.get((symbol, session_date))
        return HaltDecision(symbol, session_date, evidence_id is not None, evidence_id)
