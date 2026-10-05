from datetime import date, timedelta
from decimal import Decimal

from automation.v10.models import MarketBar


def bars(symbols=tuple(f"S{i:02d}" for i in range(1, 7)), days=80, start=date(2024, 1, 1)):
    result = []
    for offset in range(days):
        for number, symbol in enumerate(symbols, 1):
            close = Decimal(100 + offset + number) + Decimal(number * offset) / Decimal("100")
            result.append(MarketBar(symbol, start + timedelta(days=offset), close, close + 1,
                                    close - 1, close, 100000 + number * 1000 + offset,
                                    provider="TEST_PROVIDER",
                                    provider_observation_id=f"{symbol}-{offset}"))
    return result
