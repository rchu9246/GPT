"""Offline/manual V10 entry point. No broker and no schedule are reachable."""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .ledger import AppendOnlyLedger
from .market_data import TrustedMarketData
from .models import MarketBar, ObservationState
from .pipeline import ManualDailyPaperPipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--initial-equity", type=Decimal, default=Decimal("1000000"))
    args = parser.parse_args()
    rows = json.loads(args.bars.read_text(encoding="utf-8"))
    bars = [MarketBar(symbol=row["symbol"], session_date=date.fromisoformat(row["session_date"]),
                      open=Decimal(row["open"]), high=Decimal(row["high"]),
                      low=Decimal(row["low"]), close=Decimal(row["close"]),
                      volume=int(row["volume"]), state=ObservationState(row.get("state", "TRADABLE")),
                      provider=row["provider"], provider_observation_id=row["provider_observation_id"],
                      synthetic=bool(row.get("synthetic", False))) for row in rows]
    report = ManualDailyPaperPipeline(TrustedMarketData(bars), AppendOnlyLedger(), args.initial_equity).run(args.as_of)
    print(json.dumps({"label": report.label, "as_of": report.as_of.isoformat(),
                      "universe": report.universe.symbols,
                      "ranked_candidates": [candidate.symbol for candidate in report.ranked_candidates],
                      "risk_decisions": [decision.decision for decision in report.risk_decisions],
                      "paper_fills": len(report.fills), "broker_orders_created": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
