from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def n(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_get(
    client: SupabaseRestClient,
    table: str,
    query: str,
) -> list[dict[str, Any]]:
    try:
        rows = client.get(table, query)
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        print(f"Optional source unavailable: {table}: {exc}")
        return []


def latest(
    client: SupabaseRestClient,
    table: str,
    field: str,
    where: str = "",
) -> dict[str, Any]:
    query = (
        f"{where}&order={field}.desc&limit=1"
        if where
        else f"order={field}.desc&limit=1"
    )
    rows = safe_get(client, table, query)
    return rows[0] if rows else {}


def publish_event(
    client: SupabaseRestClient,
    cycle_id: str,
    event_type: str,
    topic: str,
    source_engine: str,
    payload: dict[str, Any],
    severity: str = "INFO",
    priority: int = 100,
    target_engine: str | None = None,
    status: str = "PROCESSED",
) -> str:
    event_id = str(uuid.uuid4())
    client.insert(
        "event_bus_v50",
        {
            "event_id": event_id,
            "cycle_id": cycle_id,
            "event_time": utc_now(),
            "event_date": RUN_DATE,
            "event_type": event_type,
            "event_topic": topic,
            "source_engine": source_engine,
            "target_engine": target_engine,
            "event_status": status,
            "priority": priority,
            "severity": severity,
            "payload": payload,
            "metadata": {
                "enterprise_version": "5.0.0",
                "operating_mode": "PAPER",
            },
            "retry_count": 0,
            "max_retries": 0,
            "processed_at": utc_now() if status == "PROCESSED" else None,
        },
    )
    return event_id


def timeline(
    client: SupabaseRestClient,
    cycle_id: str,
    sequence_no: int,
    engine_key: str,
    stage: str,
    decision_type: str,
    status: str,
    decision: str,
    rationale: str,
    confidence: float = 0.0,
    severity: str = "INFO",
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    blockers: list[str] | None = None,
) -> None:
    client.upsert(
        "decision_timeline_v50",
        {
            "cycle_id": cycle_id,
            "event_time": utc_now(),
            "event_date": RUN_DATE,
            "sequence_no": sequence_no,
            "engine_key": engine_key,
            "stage": stage,
            "decision_type": decision_type,
            "decision_status": status,
            "portfolio_id": None,
            "entity_type": "ENGINE",
            "entity_key": engine_key,
            "decision": decision,
            "rationale": rationale,
            "confidence": max(0.0, min(100.0, confidence)),
            "severity": severity,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "evidence": evidence or {},
            "blockers": blockers or [],
        },
        "cycle_id,sequence_no,engine_key,decision_type",
    )


def summarize_engine_output(
    client: SupabaseRestClient,
    engine_key: str,
) -> dict[str, Any]:
    if engine_key == "RISK_GOVERNOR":
        row = latest(client, "risk_governor_status_v41", "status_date")
        return {
            "status": row.get("overall_status", "UNKNOWN"),
            "confidence": max(0.0, 100 - n(row.get("overall_risk_score"), 50)),
            "summary": row.get("summary", ""),
            "blockers": row.get("blockers", []),
        }

    if engine_key == "MARKET_REGIME_AI":
        row = latest(client, "market_regime_ai_v46", "regime_date")
        return {
            "status": "PASS" if row else "WARNING",
            "confidence": n(row.get("regime_confidence"), 0),
            "summary": row.get("rationale", ""),
            "market_regime": row.get("market_regime", "UNKNOWN"),
            "posture": row.get("recommended_posture", "UNKNOWN"),
            "blockers": [],
        }

    if engine_key == "STRATEGY_SCORING":
        row = latest(client, "strategy_engine_status_v47", "status_date")
        return {
            "status": row.get("overall_status", "UNKNOWN"),
            "confidence": n(row.get("average_confidence"), 0),
            "summary": row.get("summary", ""),
            "blockers": row.get("blockers", []),
        }

    if engine_key == "PORTFOLIO_OPTIMIZER":
        row = latest(
            client,
            "optimization_runs_v49",
            "run_date",
            "run_key=eq.PORTFOLIO_OPTIMIZER",
        )
        return {
            "status": row.get("status", "UNKNOWN"),
            "confidence": n(row.get("objective_score"), 0),
            "summary": row.get("remarks", ""),
            "blockers": [],
        }

    if engine_key == "LEARNING_ENGINE":
        row = latest(client, "learning_cycle_status_v45", "status_date")
        return {
            "status": row.get("overall_status", "UNKNOWN"),
            "confidence": 50.0,
            "summary": row.get("summary", ""),
            "blockers": row.get("blockers", []),
        }

    return {
        "status": "UNKNOWN",
        "confidence": 0.0,
        "summary": "",
        "blockers": [],
    }


def run_engine(
    engine: dict[str, Any],
) -> tuple[bool, float, str, str]:
    module_path = ROOT / str(engine["module_path"])
    if not module_path.exists():
        return False, 0.0, "", f"Module not found: {module_path}"

    started = time.perf_counter()
    timeout = int(n(engine.get("timeout_seconds"), 1800))

    env = os.environ.copy()
    env["QUANT_RUN_DATE"] = RUN_DATE
    env["PYTHONPATH"] = str(ROOT / "automation")

    try:
        process = subprocess.run(
            [sys.executable, str(module_path)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        duration = time.perf_counter() - started
        stdout = process.stdout[-12000:]
        stderr = process.stderr[-12000:]
        return process.returncode == 0, duration, stdout, stderr
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - started
        return False, duration, exc.stdout or "", f"Timeout after {timeout}s"


def main() -> None:
    started = time.perf_counter()
    client = SupabaseRestClient()
    cycle_id = str(uuid.uuid4())
    workflow_key = "enterprise-5-0-operating-system"

    engines = client.get(
        "engine_registry_v50",
        (
            "enabled=eq.true"
            "&engine_key=neq.ENTERPRISE50_ORCHESTRATOR"
            "&order=execution_order.asc&limit=100"
        ),
    )
    required_engines = [row for row in engines if bool(row.get("required"))]

    client.insert(
        "execution_context_v50",
        {
            "cycle_id": cycle_id,
            "context_date": RUN_DATE,
            "workflow_key": workflow_key,
            "operating_mode": "PAPER",
            "initiated_by": "GITHUB_ACTIONS",
            "started_at": utc_now(),
            "current_stage": "INITIALIZE",
            "context_status": "RUNNING",
            "environment": {
                "python_version": sys.version,
                "repository_root": str(ROOT),
                "quant_run_date": RUN_DATE,
            },
            "engine_inputs": {},
            "engine_outputs": {},
            "shared_memory": {},
            "blockers": [],
            "warnings": [],
            "error_details": {},
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
            "broker_submission_enabled": False,
        },
    )

    client.upsert(
        "workflow_history_v50",
        {
            "cycle_id": cycle_id,
            "workflow_key": workflow_key,
            "workflow_version": "5.0.0",
            "run_date": RUN_DATE,
            "started_at": utc_now(),
            "duration_seconds": 0,
            "workflow_status": "RUNNING",
            "current_step": "INITIALIZE",
            "completed_steps": 0,
            "total_steps": len(engines),
            "engines_invoked": [],
            "step_results": [],
            "blockers": [],
            "warnings": [],
            "diagnostics": {},
        },
        "cycle_id,workflow_key",
    )

    client.upsert(
        "operating_state_v50",
        {
            "state_date": RUN_DATE,
            "system_state": "RUNNING",
            "operating_mode": "PAPER",
            "current_cycle_id": cycle_id,
            "current_workflow_key": workflow_key,
            "current_stage": "INITIALIZE",
            "market_regime": "UNKNOWN",
            "risk_status": "UNKNOWN",
            "strategy_status": "UNKNOWN",
            "allocation_status": "UNKNOWN",
            "execution_status": "UNKNOWN",
            "learning_status": "UNKNOWN",
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
            "broker_submission_enabled": False,
            "blockers": [],
            "warnings": [],
            "active_engines": [row["engine_key"] for row in engines],
            "state_snapshot": {"cycle_started_at": utc_now()},
            "summary": "Enterprise 5.0 orchestration cycle is running.",
        },
        "state_date",
    )

    publish_event(
        client,
        cycle_id,
        "WORKFLOW_STARTED",
        "enterprise50.lifecycle",
        "ENTERPRISE50_ORCHESTRATOR",
        {"workflow_key": workflow_key, "engine_count": len(engines)},
        priority=10,
    )
    timeline(
        client,
        cycle_id,
        0,
        "ENTERPRISE50_ORCHESTRATOR",
        "INITIALIZE",
        "WORKFLOW_START",
        "PASS",
        "Orchestration cycle initialized.",
        f"Loaded {len(engines)} enabled engine(s).",
        confidence=100,
    )

    step_results: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    invoked: list[str] = []
    confidence_values: list[float] = []
    succeeded = failed = skipped = 0

    for sequence, engine in enumerate(engines, start=1):
        engine_key = str(engine["engine_key"])
        invoked.append(engine_key)

        client.patch(
            "execution_context_v50",
            f"cycle_id=eq.{cycle_id}",
            {"current_stage": engine_key},
        )
        client.upsert(
            "operating_state_v50",
            {
                "state_date": RUN_DATE,
                "system_state": "RUNNING",
                "operating_mode": "PAPER",
                "current_cycle_id": cycle_id,
                "current_workflow_key": workflow_key,
                "current_stage": engine_key,
                "market_regime": "UNKNOWN",
                "risk_status": "UNKNOWN",
                "strategy_status": "UNKNOWN",
                "allocation_status": "UNKNOWN",
                "execution_status": "UNKNOWN",
                "learning_status": "UNKNOWN",
                "live_trading_enabled": False,
                "autonomous_execution_enabled": False,
                "broker_submission_enabled": False,
                "blockers": blockers,
                "warnings": warnings,
                "active_engines": [row["engine_key"] for row in engines],
                "state_snapshot": {"current_engine": engine_key},
                "summary": f"Running {engine_key}.",
            },
            "state_date",
        )

        publish_event(
            client,
            cycle_id,
            "ENGINE_STARTED",
            "enterprise50.engine.lifecycle",
            "ENTERPRISE50_ORCHESTRATOR",
            {"engine_key": engine_key},
            target_engine=engine_key,
            priority=20,
        )

        success, duration, stdout, stderr = run_engine(engine)
        result = summarize_engine_output(client, engine_key)
        status = str(result.get("status") or "UNKNOWN")
        confidence = n(result.get("confidence"), 0)
        confidence_values.append(confidence)

        engine_success = success and status not in ("CRITICAL", "FAILED")
        severity = "INFO"
        timeline_status = "PASS"

        if engine_success:
            succeeded += 1
            health_status = (
                "WARNING" if status == "WARNING" else "PASS"
            )
            timeline_status = (
                "WARNING" if status == "WARNING" else "PASS"
            )
            severity = "WARNING" if status == "WARNING" else "INFO"
            if status == "WARNING":
                warnings.append(f"{engine_key}:WARNING")
        else:
            failed += 1
            health_status = "FAILED"
            timeline_status = "FAILED"
            severity = "CRITICAL" if bool(engine.get("required")) else "WARNING"
            message = (
                f"{engine_key}:{stderr[-500:] or status or 'FAILED'}"
            )
            if bool(engine.get("required")):
                blockers.append(message)
            else:
                warnings.append(message)

        client.patch(
            "engine_registry_v50",
            f"engine_key=eq.{engine_key}",
            {
                "health_status": health_status,
                "last_run_at": utc_now(),
                "last_success_at": utc_now() if engine_success else engine.get("last_success_at"),
                "last_failure_at": None if engine_success else utc_now(),
            },
        )

        step = {
            "sequence": sequence,
            "engine_key": engine_key,
            "required": bool(engine.get("required")),
            "success": engine_success,
            "source_process_success": success,
            "engine_status": status,
            "confidence": confidence,
            "duration_seconds": duration,
            "summary": result.get("summary", ""),
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
        }
        step_results.append(step)

        timeline(
            client,
            cycle_id,
            sequence,
            engine_key,
            engine_key,
            "ENGINE_RESULT",
            timeline_status,
            (
                f"{engine_key} completed."
                if engine_success
                else f"{engine_key} failed."
            ),
            str(result.get("summary") or stderr[-1000:] or status),
            confidence=confidence,
            severity=severity,
            outputs=result,
            evidence={
                "duration_seconds": duration,
                "process_success": success,
            },
            blockers=result.get("blockers", []),
        )

        publish_event(
            client,
            cycle_id,
            "ENGINE_COMPLETED" if engine_success else "ENGINE_FAILED",
            "enterprise50.engine.lifecycle",
            engine_key,
            step,
            severity=severity,
            priority=30 if engine_success else 5,
            target_engine="ENTERPRISE50_ORCHESTRATOR",
        )

        client.patch(
            "workflow_history_v50",
            (
                f"cycle_id=eq.{cycle_id}"
                f"&workflow_key=eq.{workflow_key}"
            ),
            {
                "current_step": engine_key,
                "completed_steps": sequence,
                "engines_invoked": invoked,
                "step_results": step_results,
                "blockers": blockers,
                "warnings": warnings,
            },
        )

        if blockers:
            remaining = engines[sequence:]
            skipped = len(remaining)
            for later in remaining:
                later_key = str(later["engine_key"])
                timeline(
                    client,
                    cycle_id,
                    sequence + skipped,
                    later_key,
                    later_key,
                    "ENGINE_RESULT",
                    "SKIPPED",
                    f"{later_key} skipped.",
                    "A required upstream engine failed.",
                    severity="WARNING",
                    blockers=blockers,
                )
            break

    runtime = time.perf_counter() - started
    required_failed = any(
        not row["success"] and row["required"] for row in step_results
    )

    if required_failed or blockers:
        workflow_status = "BLOCKED"
        system_state = "BLOCKED"
        overall_status = "CRITICAL"
    elif failed or warnings:
        workflow_status = "WARNING"
        system_state = "DEGRADED"
        overall_status = "WARNING"
    else:
        workflow_status = "PASS"
        system_state = "READY"
        overall_status = "PASS"

    risk = latest(client, "risk_governor_status_v41", "status_date")
    regime = latest(client, "market_regime_ai_v46", "regime_date")
    strategy = latest(client, "strategy_engine_status_v47", "status_date")
    allocation = latest(client, "allocation_engine_status_v48", "status_date")
    optimizer = latest(
        client,
        "optimization_runs_v49",
        "run_date",
        "run_key=eq.PORTFOLIO_OPTIMIZER",
    )
    learning = latest(client, "learning_cycle_status_v45", "status_date")

    summary = (
        f"Enterprise 5.0 cycle {cycle_id} finished with "
        f"{workflow_status}; succeeded {succeeded}, failed {failed}, "
        f"skipped {skipped}, duration {runtime:.2f}s."
    )

    client.patch(
        "execution_context_v50",
        f"cycle_id=eq.{cycle_id}",
        {
            "completed_at": utc_now(),
            "current_stage": "COMPLETE",
            "context_status": (
                "BLOCKED"
                if overall_status == "CRITICAL"
                else "WARNING"
                if overall_status == "WARNING"
                else "COMPLETED"
            ),
            "engine_outputs": {
                row["engine_key"]: row for row in step_results
            },
            "shared_memory": {
                "market_regime": regime.get("market_regime"),
                "risk_status": risk.get("overall_status"),
                "strategy_status": strategy.get("overall_status"),
                "allocation_status": allocation.get("overall_status"),
                "optimizer_status": optimizer.get("status"),
            },
            "blockers": blockers,
            "warnings": warnings,
            "error_details": {
                "failed_engines": [
                    row for row in step_results if not row["success"]
                ]
            },
        },
    )

    client.patch(
        "workflow_history_v50",
        (
            f"cycle_id=eq.{cycle_id}"
            f"&workflow_key=eq.{workflow_key}"
        ),
        {
            "completed_at": utc_now(),
            "duration_seconds": runtime,
            "workflow_status": workflow_status,
            "current_step": "COMPLETE",
            "completed_steps": len(step_results),
            "engines_invoked": invoked,
            "step_results": step_results,
            "blockers": blockers,
            "warnings": warnings,
            "diagnostics": {
                "succeeded": succeeded,
                "failed": failed,
                "skipped": skipped,
            },
        },
    )

    client.upsert(
        "operating_state_v50",
        {
            "state_date": RUN_DATE,
            "system_state": system_state,
            "operating_mode": "PAPER",
            "current_cycle_id": cycle_id,
            "current_workflow_key": workflow_key,
            "current_stage": "COMPLETE",
            "market_regime": regime.get("market_regime", "UNKNOWN"),
            "risk_status": risk.get("overall_status", "UNKNOWN"),
            "strategy_status": strategy.get("overall_status", "UNKNOWN"),
            "allocation_status": allocation.get("overall_status", "UNKNOWN"),
            "execution_status": optimizer.get("status", "UNKNOWN"),
            "learning_status": learning.get("overall_status", "UNKNOWN"),
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
            "broker_submission_enabled": False,
            "blockers": blockers,
            "warnings": warnings,
            "active_engines": [row["engine_key"] for row in engines],
            "state_snapshot": {
                "cycle_id": cycle_id,
                "workflow_status": workflow_status,
                "runtime_seconds": runtime,
            },
            "summary": summary,
        },
        "state_date",
    )

    pending_events = safe_get(
        client,
        "event_bus_v50",
        "event_status=eq.PENDING&select=id&limit=1000",
    )
    failed_events = safe_get(
        client,
        "event_bus_v50",
        "event_status=eq.FAILED&select=id&limit=1000",
    )

    health_score = max(
        0.0,
        min(
            100.0,
            100
            - failed * 20
            - skipped * 10
            - len(warnings) * 5
            - len(blockers) * 25,
        ),
    )

    client.insert(
        "system_health_v50",
        {
            "health_date": RUN_DATE,
            "health_time": utc_now(),
            "overall_status": overall_status,
            "overall_health_score": health_score,
            "database_health_score": 100,
            "workflow_health_score": health_score,
            "engine_health_score": max(
                0,
                100 - failed * 20 - skipped * 10,
            ),
            "data_freshness_score": 100 if succeeded else 50,
            "risk_control_score": (
                100 if risk.get("overall_status") == "PASS" else 70
            ),
            "active_engines": len(engines),
            "degraded_engines": len(warnings),
            "failed_engines": failed,
            "pending_events": len(pending_events),
            "failed_events": len(failed_events),
            "critical_findings": len(blockers),
            "warning_findings": len(warnings),
            "blockers": blockers,
            "warnings": warnings,
            "component_status": {
                row["engine_key"]: {
                    "success": row["success"],
                    "status": row["engine_status"],
                }
                for row in step_results
            },
            "diagnostics": {
                "cycle_id": cycle_id,
                "runtime_seconds": runtime,
            },
            "summary": summary,
        },
    )

    event_rows = safe_get(
        client,
        "event_bus_v50",
        f"cycle_id=eq.{cycle_id}&limit=1000",
    )
    processed_events = [
        row for row in event_rows
        if row.get("event_status") == "PROCESSED"
    ]
    failed_cycle_events = [
        row for row in event_rows
        if row.get("event_status") == "FAILED"
    ]

    client.upsert(
        "orchestrator_status_v50",
        {
            "status_date": RUN_DATE,
            "overall_status": overall_status,
            "current_cycle_id": cycle_id,
            "workflows_started": 1,
            "workflows_completed": 0 if blockers else 1,
            "workflows_failed": 1 if blockers else 0,
            "engines_registered": len(engines) + 1,
            "engines_executed": len(step_results),
            "engines_succeeded": succeeded,
            "engines_failed": failed,
            "engines_skipped": skipped,
            "events_published": len(event_rows),
            "events_processed": len(processed_events),
            "events_failed": len(failed_cycle_events),
            "average_cycle_duration_seconds": runtime,
            "overall_confidence": (
                mean(confidence_values) if confidence_values else 0
            ),
            "live_trading_enabled": False,
            "autonomous_execution_enabled": False,
            "broker_submission_enabled": False,
            "blockers": blockers,
            "highlights": [
                f"Workflow status: {workflow_status}",
                f"Engines succeeded: {succeeded}",
                f"Market regime: {regime.get('market_regime', 'UNKNOWN')}",
                f"Optimizer status: {optimizer.get('status', 'UNKNOWN')}",
            ],
            "diagnostics": {
                "cycle_id": cycle_id,
                "step_results": step_results,
            },
            "summary": summary,
        },
        "status_date",
    )

    timeline(
        client,
        cycle_id,
        len(step_results) + 1,
        "ENTERPRISE50_ORCHESTRATOR",
        "COMPLETE",
        "WORKFLOW_COMPLETE",
        (
            "CRITICAL"
            if overall_status == "CRITICAL"
            else "WARNING"
            if overall_status == "WARNING"
            else "PASS"
        ),
        "Enterprise 5.0 orchestration cycle completed.",
        summary,
        confidence=mean(confidence_values) if confidence_values else 0,
        severity=(
            "CRITICAL"
            if overall_status == "CRITICAL"
            else "WARNING"
            if overall_status == "WARNING"
            else "INFO"
        ),
        outputs={
            "workflow_status": workflow_status,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
        blockers=blockers,
    )

    publish_event(
        client,
        cycle_id,
        "WORKFLOW_COMPLETED",
        "enterprise50.lifecycle",
        "ENTERPRISE50_ORCHESTRATOR",
        {
            "workflow_status": workflow_status,
            "summary": summary,
        },
        severity=(
            "CRITICAL"
            if overall_status == "CRITICAL"
            else "WARNING"
            if overall_status == "WARNING"
            else "INFO"
        ),
        priority=10,
    )

    print(summary)
    print(f"Enterprise 5.0 Orchestrator status: {overall_status}")

    if overall_status == "CRITICAL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
