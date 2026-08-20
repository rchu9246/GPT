#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase362_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE362_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py"
UPSTREAM_JSON = ROOT / "phase361_output/phase361_autonomous_operation.json"
MASTER_JSON = ROOT / "phase360_output/phase360_master_cycle.json"

HEALTH_TABLE = "paper_system_health_v92"
INCIDENT_TABLE = "paper_incident_audit_v92"

RESULT_JSON = OUT / "phase362_health_monitoring.json"
RESULT_MD = OUT / "phase362_health_monitoring.md"

CONTRACT = "PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE"

HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
INCIDENT = "INCIDENT"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def supabase() -> tuple[str, dict[str, str]]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not base or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing")

    return base, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(table: str, params: list[tuple[str, str]]) -> list[dict[str, Any]]:
    base, headers = supabase()
    response = requests.get(
        f"{base}/rest/v1/{quote(table, safe='')}",
        headers=headers,
        params=params,
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:1000]}"
        )

    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"{table}: expected list response")

    return [x for x in data if isinstance(x, dict)]


def rest_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    if not rows:
        return

    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    response = requests.post(
        f"{base}/rest/v1/{quote(table, safe='')}",
        headers=headers,
        params={"on_conflict": on_conflict},
        data=json.dumps(rows, ensure_ascii=False, default=str),
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1400]}"
        )


def run_upstream(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE361_PORTFOLIO_ID"] = PORTFOLIO_ID
    env["PHASE360_PORTFOLIO_ID"] = PORTFOLIO_ID

    proc = subprocess.run(
        [
            sys.executable,
            str(UPSTREAM),
            "--approver",
            approver,
            "--max-attempts",
            os.getenv("PHASE362_MAX_ATTEMPTS", "2"),
            "--retry-delay-seconds",
            os.getenv("PHASE362_RETRY_DELAY_SECONDS", "10"),
        ],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if not UPSTREAM_JSON.exists():
        raise RuntimeError(
            f"Phase 3.6.1 evidence missing; upstream exit={proc.returncode}"
        )

    payload = read_json(UPSTREAM_JSON)

    if proc.returncode != 0 or payload.get("status") != "PASS":
        raise RuntimeError("Phase 3.6.1 autonomous operation did not PASS")

    return payload


def load_master() -> dict[str, Any]:
    if not MASTER_JSON.exists():
        raise RuntimeError("Phase 3.6.0 master evidence missing")
    payload = read_json(MASTER_JSON)
    if payload.get("status") != "PASS":
        raise RuntimeError("Phase 3.6.0 master status is not PASS")
    return payload


def build_checks(operation: dict[str, Any], master: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}

    def add(name: str, passed: bool, value: Any, expected: Any, severity: str) -> None:
        checks[name] = {
            "passed": bool(passed),
            "value": value,
            "expected": expected,
            "severity": severity,
        }

    add(
        "autonomous_operation_status",
        operation.get("operation_status") == "PASS",
        operation.get("operation_status"),
        "PASS",
        "CRITICAL",
    )

    add(
        "master_final_state",
        master.get("final_state") in {
            "DAILY_MASTER_CYCLE_COMPLETED",
            "PAPER_HALT_COMPLETED",
        },
        master.get("final_state"),
        "valid completed master state",
        "CRITICAL",
    )

    add(
        "seven_master_stages",
        isinstance(master.get("stages"), list)
        and len(master["stages"]) == 7
        and all(x.get("status") == "PASS" for x in master["stages"]),
        len(master.get("stages") or []),
        7,
        "CRITICAL",
    )

    add(
        "nonnegative_cash",
        float(master.get("cash") or 0) >= 0,
        master.get("cash"),
        ">= 0",
        "CRITICAL",
    )

    add(
        "nonnegative_nav",
        float(master.get("nav") or 0) >= 0,
        master.get("nav"),
        ">= 0",
        "CRITICAL",
    )

    add(
        "recovery_not_exhausted",
        operation.get("recovery_state") != "RECOVERY_EXHAUSTED",
        operation.get("recovery_state"),
        "NOT_REQUIRED or RECOVERED_AFTER_RETRY",
        "CRITICAL",
    )

    safety_false = {
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }

    for key, expected in safety_false.items():
        add(
            f"safety_{key}",
            master.get(key) is expected and operation.get(key) is expected,
            {
                "master": master.get(key),
                "operation": operation.get(key),
            },
            expected,
            "CRITICAL",
        )

    add(
        "fail_closed_enabled",
        master.get("fail_closed_policy") is True
        and operation.get("fail_closed_policy") is True,
        {
            "master": master.get("fail_closed_policy"),
            "operation": operation.get("fail_closed_policy"),
        },
        True,
        "CRITICAL",
    )

    add(
        "master_activity_counts_nonnegative",
        all(
            int(master.get(k) or 0) >= 0
            for k in (
                "eligible_signals",
                "sized_candidates",
                "order_intents_created",
                "simulated_fills_created",
                "fills_settled",
                "open_positions",
            )
        ),
        {
            k: master.get(k)
            for k in (
                "eligible_signals",
                "sized_candidates",
                "order_intents_created",
                "simulated_fills_created",
                "fills_settled",
                "open_positions",
            )
        },
        "all >= 0",
        "WARNING",
    )

    return checks


def classify_health(checks: dict[str, dict[str, Any]], operation: dict[str, Any]) -> tuple[str, float]:
    total = len(checks)
    passed = sum(1 for x in checks.values() if x["passed"])
    score = round((passed / total) * 100.0, 2) if total else 0.0

    critical_failed = [
        name
        for name, item in checks.items()
        if not item["passed"] and item["severity"] == "CRITICAL"
    ]

    warning_failed = [
        name
        for name, item in checks.items()
        if not item["passed"] and item["severity"] == "WARNING"
    ]

    if critical_failed:
        return INCIDENT, score

    if warning_failed or operation.get("recovery_state") == "RECOVERED_AFTER_RETRY":
        return DEGRADED, score

    return HEALTHY, score


def persist_health(
    operation: dict[str, Any],
    master: dict[str, Any],
    checks: dict[str, dict[str, Any]],
    health_status: str,
    health_score: float,
) -> dict[str, Any]:
    health_date = str(operation["operation_date"])
    failed_checks = [name for name, item in checks.items() if not item["passed"]]

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "health_date": health_date,
        "health_status": health_status,
        "health_score": health_score,
        "failed_checks": failed_checks,
        "master_cycle_id": master.get("master_cycle_id"),
        "operation_id": operation.get("operation_id"),
    }

    row = {
        "health_id": "P362H-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "health_date": health_date,
        "health_status": health_status,
        "health_score": health_score,
        "incident_required": health_status == INCIDENT,
        "autonomous_operation_status": operation.get("operation_status"),
        "recovery_state": operation.get("recovery_state"),
        "master_final_state": master.get("final_state"),
        "market_data_status": None,
        "latest_market_date": None,
        "eligible_signals": int(master.get("eligible_signals") or 0),
        "sized_candidates": int(master.get("sized_candidates") or 0),
        "order_intents_created": int(master.get("order_intents_created") or 0),
        "simulated_fills_created": int(master.get("simulated_fills_created") or 0),
        "fills_settled": int(master.get("fills_settled") or 0),
        "cash": master.get("cash"),
        "market_value": master.get("market_value"),
        "nav": master.get("nav"),
        "realized_pnl": master.get("realized_pnl"),
        "unrealized_pnl": master.get("unrealized_pnl"),
        "open_positions": int(master.get("open_positions") or 0),
        "checks_passed": sum(1 for x in checks.values() if x["passed"]),
        "checks_failed": sum(1 for x in checks.values() if not x["passed"]),
        "check_details": checks,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": stable_hash(seed),
        "updated_at": now_iso(),
    }

    rest_upsert(
        HEALTH_TABLE,
        [row],
        "portfolio_id,health_date",
    )

    rows = rest_get(
        HEALTH_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("health_date", f"eq.{health_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Health snapshot persistence verification failed")

    return rows[0]


def persist_incident(
    health: dict[str, Any],
    checks: dict[str, dict[str, Any]],
    operation: dict[str, Any],
) -> dict[str, Any] | None:
    failed = {
        name: item
        for name, item in checks.items()
        if not item["passed"]
    }

    if not failed:
        return None

    critical = [
        name
        for name, item in failed.items()
        if item["severity"] == "CRITICAL"
    ]

    severity = "CRITICAL" if critical else "WARNING"
    incident_type = (
        "AUTONOMOUS_HEALTH_CONTRACT_VIOLATION"
        if critical
        else "AUTONOMOUS_HEALTH_DEGRADED"
    )

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "incident_date": health["health_date"],
        "severity": severity,
        "failed_checks": sorted(failed),
        "health_id": health["health_id"],
    }

    row = {
        "incident_id": "P362I-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "incident_date": health["health_date"],
        "severity": severity,
        "incident_type": incident_type,
        "incident_state": "OPEN" if critical else "OBSERVED",
        "source_phase": "PHASE362",
        "source_health_id": health["health_id"],
        "summary": f"{severity}: {len(failed)} health check(s) failed",
        "details": failed,
        "autonomous_recovery_attempted": int(operation.get("attempt_count") or 1) > 1,
        "autonomous_recovery_succeeded": operation.get("recovery_state") == "RECOVERED_AFTER_RETRY",
        "operator_action_required": bool(critical),
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "fail_closed_policy": True,
        "evidence_sha256": stable_hash(seed),
        "updated_at": now_iso(),
    }

    rest_upsert(
        INCIDENT_TABLE,
        [row],
        "incident_id",
    )

    return row


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.6.2",
        "",
        "## Production Paper Autonomous Health Monitoring + Incident Audit Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Health Date: `{result['health_date']}`",
        f"- Health Status: **{result['health_status']}**",
        f"- Health Score: **{result['health_score']:.2f}%**",
        f"- Checks Passed: **{result['checks_passed']}**",
        f"- Checks Failed: **{result['checks_failed']}**",
        f"- Incident Created: **{'YES' if result['incident_created'] else 'NO'}**",
        "",
        "### Autonomous Runtime",
        "",
        f"- Operation Status: **{result['autonomous_operation_status']}**",
        f"- Recovery State: **{result['recovery_state']}**",
        f"- Master Final State: **{result['master_final_state']}**",
        "",
        "### Portfolio",
        "",
        f"- Cash: **{result['cash']:.2f}**",
        f"- Market Value: **{result['market_value']:.2f}**",
        f"- NAV: **{result['nav']:.2f}**",
        f"- Open Positions: **{result['open_positions']}**",
        "",
        "### Safety Boundary",
        "",
        "- Synthetic market data: **DISABLED**",
        "- Synthetic signals: **DISABLED**",
        "- Fake prices: **DISABLED**",
        "- Broker API used: **NO**",
        "- Broker credentials used: **NO**",
        "- Broker order submission: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Live-money release authorized: **NO**",
        "- Fail-closed policy: **ENABLED**",
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    text = "\n".join(lines) + "\n"
    RESULT_MD.write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE362_APPROVER", "github-actions"),
    )
    args = parser.parse_args()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    operation = run_upstream(args.approver)
    master = load_master()

    checks = build_checks(operation, master)
    health_status, health_score = classify_health(checks, operation)

    health = persist_health(
        operation,
        master,
        checks,
        health_status,
        health_score,
    )

    incident = persist_incident(
        health,
        checks,
        operation,
    )

    result = {
        "version": "3.6.2",
        "status": "PASS" if health_status in {HEALTHY, DEGRADED} else "FAIL",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "health_id": health["health_id"],
        "health_date": str(health["health_date"]),
        "health_status": health["health_status"],
        "health_score": float(health["health_score"]),
        "checks_passed": int(health["checks_passed"]),
        "checks_failed": int(health["checks_failed"]),
        "incident_created": incident is not None,
        "incident_id": incident["incident_id"] if incident else None,
        "autonomous_operation_status": health.get("autonomous_operation_status"),
        "recovery_state": health.get("recovery_state"),
        "master_final_state": health.get("master_final_state"),
        "eligible_signals": int(health.get("eligible_signals") or 0),
        "sized_candidates": int(health.get("sized_candidates") or 0),
        "order_intents_created": int(health.get("order_intents_created") or 0),
        "simulated_fills_created": int(health.get("simulated_fills_created") or 0),
        "fills_settled": int(health.get("fills_settled") or 0),
        "cash": float(health.get("cash") or 0),
        "market_value": float(health.get("market_value") or 0),
        "nav": float(health.get("nav") or 0),
        "realized_pnl": float(health.get("realized_pnl") or 0),
        "unrealized_pnl": float(health.get("unrealized_pnl") or 0),
        "open_positions": int(health.get("open_positions") or 0),
        "check_details": checks,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": health["evidence_sha256"],
    }

    write_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if health_status == INCIDENT:
        print(
            "PHASE362 FAIL-CLOSED: critical autonomous health incident detected."
        )
        return 1

    print(
        "PHASE362 PASS: autonomous health monitoring complete. "
        f"health={health_status}, "
        f"score={health_score:.2f}, "
        f"incident={'YES' if incident else 'NO'}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
