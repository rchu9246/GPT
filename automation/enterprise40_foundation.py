from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

from enterprise2.client import SupabaseRestClient

RELEASE = "4.0.0-foundation.1"
RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())

REQUIRED_TABLES = [
    "enterprise_portfolios_v40",
    "enterprise_strategies_v40",
    "enterprise_strategy_versions_v40",
    "enterprise_runs_v40",
    "enterprise_run_stages_v40",
    "audit_logs_v40",
    "market_regimes_v40",
    "market_regime_features_v40",
    "strategy_regime_allocations_v40",
    "release_status_v40",
]

def table_exists(client: SupabaseRestClient, table: str) -> bool:
    try:
        client.get(table, "select=*&limit=1")
        return True
    except Exception:
        return False

def audit(
    client: SupabaseRestClient,
    *,
    action: str,
    entity_type: str,
    entity_key: str,
    run_id: str | None = None,
    severity: str = "INFO",
    metadata: dict[str, Any] | None = None,
) -> None:
    client.insert(
        "audit_logs_v40",
        {
            "actor_type": "SYSTEM",
            "actor_key": "enterprise40-foundation",
            "action": action,
            "entity_type": entity_type,
            "entity_key": entity_key,
            "run_id": run_id,
            "severity": severity,
            "metadata": metadata or {},
        },
    )

def main() -> None:
    client = SupabaseRestClient()

    idempotency_key = f"{RELEASE}:{RUN_DATE}:FOUNDATION"
    existing = client.get(
        "enterprise_runs_v40",
        f"idempotency_key=eq.{idempotency_key}&limit=1",
    )
    if existing and existing[0].get("status") == "SUCCESS":
        print("Foundation run already completed; exiting idempotently.")
        return

    if existing:
        run_id = str(existing[0]["id"])
        client.patch(
            "enterprise_runs_v40",
            f"id=eq.{run_id}",
            {
                "status": "RUNNING",
                "current_stage": "SCHEMA_GATE",
                "completed_at": None,
                "blockers": [],
                "error_message": None,
            },
        )
    else:
        run = client.insert(
            "enterprise_runs_v40",
            {
                "run_key": f"foundation-{RUN_DATE}",
                "run_date": RUN_DATE,
                "run_type": "FOUNDATION_VALIDATION",
                "release_version": RELEASE,
                "status": "RUNNING",
                "current_stage": "SCHEMA_GATE",
                "idempotency_key": idempotency_key,
                "metadata": {"mode": "PAPER_ONLY"},
            },
        )[0]
        run_id = str(run["id"])

    stage_defs = [
        ("SCHEMA_GATE", 1, True),
        ("REGISTRY_CHECK", 2, True),
        ("REGIME_FOUNDATION", 3, True),
        ("COMPATIBILITY_CHECK", 4, True),
        ("RELEASE_STATUS", 5, True),
    ]

    for key, order, critical in stage_defs:
        client.upsert(
            "enterprise_run_stages_v40",
            {
                "run_id": run_id,
                "stage_key": key,
                "stage_order": order,
                "status": "PENDING",
                "critical": critical,
            },
            "run_id,stage_key",
        )

    blockers: list[str] = []

    try:
        for table in REQUIRED_TABLES:
            if not table_exists(client, table):
                blockers.append(f"missing_table:{table}")

        stage_status = "FAILED" if blockers else "SUCCESS"
        client.patch(
            "enterprise_run_stages_v40",
            f"run_id=eq.{run_id}&stage_key=eq.SCHEMA_GATE",
            {
                "status": stage_status,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "output_summary": {"blockers": blockers},
                "error_message": "Required schema missing" if blockers else None,
            },
        )

        if blockers:
            raise RuntimeError("Required Enterprise 4.0 schema is missing.")

        portfolios = client.get(
            "enterprise_portfolios_v40",
            "select=id,portfolio_key,lifecycle_status&limit=100",
        )
        strategies = client.get(
            "enterprise_strategies_v40",
            "select=id,strategy_key,lifecycle_status,paper_approved,live_approved&limit=100",
        )

        registry_blockers = []
        if not portfolios:
            registry_blockers.append("no_portfolios")
        if not strategies:
            registry_blockers.append("no_strategies")
        if any(bool(row.get("live_approved")) for row in strategies):
            registry_blockers.append("live_strategy_enabled")

        client.patch(
            "enterprise_run_stages_v40",
            f"run_id=eq.{run_id}&stage_key=eq.REGISTRY_CHECK",
            {
                "status": "FAILED" if registry_blockers else "SUCCESS",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "output_summary": {
                    "portfolio_count": len(portfolios),
                    "strategy_count": len(strategies),
                    "blockers": registry_blockers,
                },
            },
        )
        if registry_blockers:
            blockers.extend(registry_blockers)
            raise RuntimeError("Registry validation failed.")

        signals = client.get(
            "signals",
            "select=trade_date,trend_score,momentum_score,risk_score,total_score"
            "&order=trade_date.desc&limit=500",
        )
        if signals:
            latest_date = str(signals[0]["trade_date"])
            latest = [r for r in signals if str(r.get("trade_date")) == latest_date]
            trend = sum(float(r.get("trend_score") or 50) for r in latest) / len(latest)
            momentum = sum(float(r.get("momentum_score") or 50) for r in latest) / len(latest)
            risk = sum(float(r.get("risk_score") or 50) for r in latest) / len(latest)
            total = sum(float(r.get("total_score") or 50) for r in latest) / len(latest)

            if risk >= 70:
                regime = "RISK_OFF"
            elif risk >= 60:
                regime = "HIGH_VOLATILITY"
            elif trend >= 60 and momentum >= 55:
                regime = "BULL"
            elif trend < 40 and momentum < 45:
                regime = "BEAR"
            else:
                regime = "SIDEWAYS"

            confidence = max(
                0.0,
                min(
                    100.0,
                    100.0 - abs(trend - momentum) * 0.5 - abs(50 - total) * 0.2,
                ),
            )
            client.upsert(
                "market_regimes_v40",
                {
                    "regime_date": latest_date,
                    "market_key": "TWSE",
                    "regime": regime,
                    "confidence": confidence,
                    "trend_score": trend,
                    "breadth_score": total,
                    "volatility_score": risk,
                    "momentum_score": momentum,
                    "drawdown_score": 0,
                    "rationale": (
                        f"Foundation regime inferred from internal signal aggregates: "
                        f"trend {trend:.1f}, momentum {momentum:.1f}, risk {risk:.1f}."
                    ),
                    "features": {
                        "signal_count": len(latest),
                        "source": "signals",
                    },
                },
                "regime_date,market_key",
            )
            regime_summary = {
                "regime_date": latest_date,
                "regime": regime,
                "confidence": confidence,
            }
        else:
            regime_summary = {
                "regime_date": RUN_DATE,
                "regime": "UNKNOWN",
                "confidence": 0,
            }
            client.upsert(
                "market_regimes_v40",
                {
                    "regime_date": RUN_DATE,
                    "market_key": "TWSE",
                    "regime": "UNKNOWN",
                    "confidence": 0,
                    "trend_score": 0,
                    "breadth_score": 0,
                    "volatility_score": 0,
                    "momentum_score": 0,
                    "drawdown_score": 0,
                    "rationale": "No signals were available during foundation validation.",
                    "features": {"source": "none"},
                },
                "regime_date,market_key",
            )

        client.patch(
            "enterprise_run_stages_v40",
            f"run_id=eq.{run_id}&stage_key=eq.REGIME_FOUNDATION",
            {
                "status": "SUCCESS",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "output_summary": regime_summary,
            },
        )

        compat_portfolios = client.get("compat_portfolios_v40", "select=*&limit=10")
        compat_strategies = client.get("compat_strategies_v40", "select=*&limit=10")

        client.patch(
            "enterprise_run_stages_v40",
            f"run_id=eq.{run_id}&stage_key=eq.COMPATIBILITY_CHECK",
            {
                "status": "SUCCESS",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "output_summary": {
                    "compat_portfolios": len(compat_portfolios),
                    "compat_strategies": len(compat_strategies),
                },
            },
        )

        readiness_score = 100
        client.upsert(
            "release_status_v40",
            {
                "release_date": RUN_DATE,
                "release_version": RELEASE,
                "foundation_ready": True,
                "registry_ready": True,
                "run_tracking_ready": True,
                "audit_ready": True,
                "regime_ready": True,
                "compatibility_ready": True,
                "live_trading_enabled": False,
                "readiness_score": readiness_score,
                "blockers": [],
            },
            "release_date,release_version",
        )

        client.patch(
            "enterprise_run_stages_v40",
            f"run_id=eq.{run_id}&stage_key=eq.RELEASE_STATUS",
            {
                "status": "SUCCESS",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "output_summary": {
                    "readiness_score": readiness_score,
                    "live_trading_enabled": False,
                },
            },
        )

        client.patch(
            "enterprise_runs_v40",
            f"id=eq.{run_id}",
            {
                "status": "SUCCESS",
                "current_stage": "COMPLETE",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "blockers": [],
            },
        )
        audit(
            client,
            action="FOUNDATION_VALIDATION_COMPLETED",
            entity_type="RELEASE",
            entity_key=RELEASE,
            run_id=run_id,
            metadata={"readiness_score": readiness_score},
        )
        print("GPT Quant Enterprise 4.0 Foundation validation completed.")

    except Exception as exc:
        client.patch(
            "enterprise_runs_v40",
            f"id=eq.{run_id}",
            {
                "status": "FAILED",
                "current_stage": "FAILED",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "blockers": blockers,
                "error_message": str(exc),
            },
        )
        audit(
            client,
            action="FOUNDATION_VALIDATION_FAILED",
            entity_type="RELEASE",
            entity_key=RELEASE,
            run_id=run_id,
            severity="CRITICAL",
            metadata={"error": str(exc), "blockers": blockers},
        )
        raise

if __name__ == "__main__":
    main()
