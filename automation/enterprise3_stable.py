"""GPT Quant Enterprise 3.0 Stable orchestrator.

Stable guarantees:
- validates required schema before running
- records a release run and each stage result
- critical stages fail closed
- noncritical reporting stages may fail without corrupting the run
- remains PAPER_ONLY
"""
from __future__ import annotations

import importlib.util
import os
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from enterprise2.client import SupabaseRestClient

ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ROOT = Path(__file__).resolve().parent

REQUIRED_TABLES = [
    "daily_prices",
    "signals",
    "trade_orders_v13",
    "paper_positions_v13",
    "quant_runs",
    "quant_operational_status",
    "quant_research_reports",
    "quant_portfolio_recommendations",
    "quant_risk_events",
    "quant_reports",
    "quant_ceo_snapshots",
    "quant_release_status",
]

def load_main(filename: str) -> Callable[[], None]:
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main = getattr(module, "main", None)
    if not callable(main):
        raise RuntimeError(f"{filename} has no main()")
    return main

def table_exists(client: SupabaseRestClient, table: str) -> bool:
    try:
        client.get(table, "select=*&limit=1")
        return True
    except Exception:
        return False

def upsert_quality(
    client: SupabaseRestClient,
    key: str,
    status: str,
    message: str,
    *,
    severity: str = "INFO",
    observed: str | None = None,
    expected: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    client.upsert(
        "quant_data_quality_checks",
        {
            "account_name": ACCOUNT,
            "check_date": RUN_DATE,
            "check_key": key,
            "check_status": status,
            "observed_value": observed,
            "expected_value": expected,
            "severity": severity,
            "message": message,
            "details": details or {},
        },
        "account_name,check_date,check_key",
    )

def main() -> None:
    client = SupabaseRestClient()

    release_run = client.insert(
        "quant_release_runs",
        {
            "account_name": ACCOUNT,
            "release_version": "3.0.0",
            "run_date": RUN_DATE,
            "run_status": "RUNNING",
            "current_stage": "SCHEMA_VALIDATION",
        },
    )[0]
    run_id = str(release_run["id"])

    blockers: list[str] = []
    stage_results: list[dict[str, Any]] = []

    for table in REQUIRED_TABLES:
        ready = table_exists(client, table)
        upsert_quality(
            client,
            f"schema_{table}",
            "PASS" if ready else "FAIL",
            f"{table} is {'available' if ready else 'missing'}.",
            severity="INFO" if ready else "CRITICAL",
            observed="AVAILABLE" if ready else "MISSING",
            expected="AVAILABLE",
        )
        if not ready:
            blockers.append(f"missing_table:{table}")

    if blockers:
        client.patch(
            "quant_release_runs",
            f"id=eq.{run_id}",
            {
                "run_status": "FAILED",
                "current_stage": "SCHEMA_VALIDATION",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "stage_results": stage_results,
                "blockers": blockers,
                "error_message": "Required schema missing",
            },
        )
        raise SystemExit(f"Stable run blocked: {blockers}")

    stages = [
        ("V16_ORDERS", "generate_orders_v16.py", True),
        ("V17_PORTFOLIO", "portfolio_os_v17.py", True),
        ("V18_AI_FUND", "ai_fund_manager_v18.py", True),
        ("V19_HEDGE_RISK", "hedge_fund_manager_v19.py", True),
        ("V20_INSTITUTION_REPORT", "institutional_report_v20.py", False),
        ("V21_COUNCIL", "multi_agent_council_v21.py", True),
        ("V22_DIRECTOR", "trading_director_v22.py", True),
        ("E20_CONSOLIDATION", "enterprise2_master.py", True),
        ("E21_OPERATIONS", "enterprise2_operational.py", True),
        ("E30_RESEARCH", "enterprise3_research_alpha1.py", True),
        ("E30_PORTFOLIO_RECOMMENDATIONS", "enterprise3_portfolio_recommendations.py", True),
        ("E30_RESEARCH_OUTCOMES", "enterprise3_research_outcomes.py", False),
        ("E30_CEO_SNAPSHOT", "enterprise3_ceo_snapshot_alpha1.py", True),
        ("E30_RELEASE_READINESS", "enterprise3_release_readiness.py", True),
    ]

    critical_failure = False
    error_message = None

    for stage_name, filename, critical in stages:
        client.patch(
            "quant_release_runs",
            f"id=eq.{run_id}",
            {"current_stage": stage_name},
        )
        try:
            load_main(filename)()
            stage_results.append({
                "stage": stage_name,
                "status": "SUCCESS",
                "critical": critical,
            })
        except Exception as exc:
            stage_results.append({
                "stage": stage_name,
                "status": "FAILED",
                "critical": critical,
                "error": str(exc),
            })
            if critical:
                critical_failure = True
                error_message = f"{stage_name}: {exc}"
                blockers.append(f"critical_stage_failed:{stage_name}")
                break

    final_status = "FAILED" if critical_failure else "SUCCESS"

    client.patch(
        "quant_release_runs",
        f"id=eq.{run_id}",
        {
            "run_status": final_status,
            "current_stage": "COMPLETE" if not critical_failure else "FAILED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "stage_results": stage_results,
            "blockers": blockers,
            "error_message": error_message,
        },
    )

    if critical_failure:
        raise SystemExit(error_message or "Stable run failed")

    print("GPT Quant Enterprise 3.0 Stable cycle completed successfully.")

if __name__ == "__main__":
    main()
