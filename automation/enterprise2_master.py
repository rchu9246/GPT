"""GPT Quant Enterprise 2.0 master orchestrator.

Foundation release:
- creates one run record
- executes registered compatibility modules
- writes unified decisions, positions, snapshots, audit logs and health state
- preserves all legacy engines while enabling gradual migration

No live broker execution.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

from enterprise2.client import SupabaseRestClient
from enterprise2.health import SystemHealthModule
from enterprise2.legacy_bridge import (
    LegacyDecisionBridge,
    LegacyPortfolioBridge,
)
from enterprise2.module import ModuleResult, QuantModule

ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

def main() -> None:
    client = SupabaseRestClient()

    run_row = client.insert(
        "quant_runs",
        {
            "account_name": ACCOUNT,
            "run_date": RUN_DATE,
            "run_type": "ENTERPRISE_2_DAILY",
            "status": "RUNNING",
        },
    )[0]
    run_id = str(run_row["id"])

    modules: list[QuantModule] = [
        LegacyDecisionBridge(client, ACCOUNT),
        LegacyPortfolioBridge(client, ACCOUNT),
        SystemHealthModule(client, ACCOUNT),
    ]

    success_count = 0
    failure_count = 0
    results: list[dict[str, Any]] = []

    for module in modules:
        try:
            module.audit(
                run_id,
                "MODULE_START",
                f"Starting {module.module_key}",
            )
            result = module.run(RUN_DATE)
            success_count += 1
            results.append(
                {
                    "module_key": result.module_key,
                    "status": result.status,
                    "summary": result.summary,
                }
            )
            module.audit(
                run_id,
                "MODULE_COMPLETE",
                f"Completed {module.module_key}",
                details=result.summary,
            )
        except Exception as exc:
            failure_count += 1
            results.append(
                {
                    "module_key": module.module_key,
                    "status": "FAILED",
                    "error": str(exc),
                }
            )
            module.audit(
                run_id,
                "MODULE_FAILED",
                f"Failed {module.module_key}: {exc}",
                severity="ERROR",
            )

    final_status = "SUCCESS" if failure_count == 0 else "PARTIAL_FAILURE"

    client.patch(
        "quant_runs",
        f"id=eq.{run_id}",
        {
            "status": final_status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "module_count": len(modules),
            "success_count": success_count,
            "failure_count": failure_count,
            "summary": {"modules": results},
            "error_message": (
                None if failure_count == 0 else f"{failure_count} module(s) failed"
            ),
        },
    )

    print(
        f"Enterprise 2.0 run {run_id}: "
        f"{success_count} success, {failure_count} failed"
    )

if __name__ == "__main__":
    main()
