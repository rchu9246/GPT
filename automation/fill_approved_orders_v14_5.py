from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from urllib.parse import quote
import requests

sys.path.insert(0, os.path.dirname(__file__))
import paper_trading_engine_v13_1 as engine

account_name = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")
config = engine.load_config()
if not config:
    raise SystemExit("No autotrader config")
config = {**config, "auto_fill": True}

account = engine.load_or_create_account(config)
positions = engine.load_positions()
positions_by_symbol = {str(row["symbol"]): row for row in positions}

orders = engine.get_rows(
    "trade_orders_v13",
    f"account_name=eq.{quote(account_name)}&mode=eq.PAPER"
    "&status=eq.APPROVED&order=created_at.asc&limit=100",
)

fills = 0
for order in orders:
    account, count = engine.fill_order(
        order, config, account, positions_by_symbol
    )
    fills += count

_, _, _, price_by_symbol = engine.load_market_data()
market_value, unrealized = engine.mark_to_market(
    positions_by_symbol, price_by_symbol
)
equity = engine.money(engine.number(account.get("cash")) + market_value)
account_payload = {
    **account,
    "account_name": account_name,
    "equity": equity,
    "unrealized_pnl": unrealized,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
engine.upsert_rows(
    "paper_accounts_v13", account_payload, "account_name"
)
print(f"Approved orders processed. fills={fills}, equity={equity:.2f}")
