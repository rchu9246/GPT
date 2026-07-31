from __future__ import annotations

import os
from datetime import date
from typing import Any

from enterprise2.client import SupabaseRestClient

ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

def exists(client: SupabaseRestClient, table: str) -> bool:
    try:
        client.get(table, "select=id&limit=1")
        return True
    except Exception:
        return False

def main() -> None:
    client = SupabaseRestClient()
    blockers: list[str] = []

    checks = {
        "data_ready": exists(client, "daily_prices"),
        "research_ready": exists(client, "quant_research_reports"),
        "portfolio_ready": exists(client, "quant_portfolio_recommendations"),
        "risk_ready": exists(client, "quant_risk_events"),
        "execution_ready": exists(client, "trade_orders_v13"),
        "reporting_ready": exists(client, "quant_reports"),
        "dashboard_ready": exists(client, "quant_ceo_snapshots"),
    }

    for key, ready in checks.items():
        if not ready:
            blockers.append(key)

    readiness_score = sum(100 if v else 0 for v in checks.values()) / len(checks)

    client.upsert(
        "quant_release_status",
        {
            "account_name": ACCOUNT,
            "release_date": RUN_DATE,
            "release_version": "3.0.0-rc.1",
            "readiness_score": readiness_score,
            **checks,
            "live_trading_enabled": False,
            "blockers": blockers,
        },
        "account_name,release_date,release_version",
    )

    print(f"Release readiness: {readiness_score:.1f}%")
    print(f"Blockers: {blockers}")

if __name__ == "__main__":
    main()
