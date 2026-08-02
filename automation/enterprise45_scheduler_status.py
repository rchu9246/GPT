from __future__ import annotations

import os
from datetime import date
from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

def latest(client: SupabaseRestClient, table: str, field: str):
    rows = client.get(table, f"order={field}.desc&limit=1")
    return rows[0] if rows else {}

def main() -> None:
    client = SupabaseRestClient()
    checks = {
        "risk_governor": latest(client, "risk_governor_status_v41", "status_date"),
        "adaptive_allocation": latest(client, "adaptive_allocation_status_v42", "status_date"),
        "committee": latest(client, "committee_status_v43", "status_date"),
        "portfolio_brain": latest(client, "self_learning_status_v44", "status_date"),
        "learning_cycle": latest(client, "learning_cycle_status_v45", "status_date"),
    }

    stale = [
        name for name, row in checks.items()
        if not row or str(row.get("status_date")) != RUN_DATE
    ]
    for name, row in checks.items():
        print(f"{name}: {row.get('status_date') if row else 'NO DATA'}")

    if stale:
        print(f"Scheduler status WARNING. Missing current-date data: {stale}")
    else:
        print("Scheduler status PASS. All status tables contain current-date data.")

if __name__ == "__main__":
    main()
