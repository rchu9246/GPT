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
OUT = ROOT / "phase364_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE364_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py"

MASTER_JSON = ROOT / "phase360_output/phase360_master_cycle.json"
OP_JSON = ROOT / "phase361_output/phase361_autonomous_operation.json"
HEALTH_JSON = ROOT / "phase362_output/phase362_health_monitoring.json"
SLA_JSON = ROOT / "phase363_output/phase363_observability_sla.json"

READINESS_TABLE = "paper_operational_readiness_v92"
GATE_TABLE = "paper_promotion_gate_audit_v92"

RESULT_JSON = OUT / "phase364_operational_readiness.json"
RESULT_MD = OUT / "phase364_operational_readiness.md"

CONTRACT = "PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE"

READY = "READY"
READY_WITH_OBSERVATION = "READY_WITH_OBSERVATION"
NOT_READY = "NOT_READY"
FAIL_CLOSED = "FAIL_CLOSED"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def run_upstream(approver: str) -> None:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    env["PHASE364_PORTFOLIO_ID"] = PORTFOLIO_ID
    env["PHASE363_PORTFOLIO_ID"] = PORTFOLIO_ID
    env["PHASE362_PORTFOLIO_ID"] = PORTFOLIO_ID
    env["PHASE361_PORTFOLIO_ID"] = PORTFOLIO_ID
    env["PHASE360_PORTFOLIO_ID"] = PORTFOLIO_ID

    proc = subprocess.run(
        [sys.executable, str(UPSTREAM), "--approver", approver],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if proc.returncode != 0:
        raise RuntimeError(f"Phase 3.6.3 failed with exit code {proc.returncode}")


def load_required() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    missing = [
        str(p)
        for p in (MASTER_JSON, OP_JSON, HEALTH_JSON, SLA_JSON)
        if not p.exists()
    ]
    if missing:
        raise RuntimeError(f"Required evidence missing: {missing}")

    return (
        read_json(MASTER_JSON),
        read_json(OP_JSON),
        read_json(HEALTH_JSON),
        read_json(SLA_JSON),
    )


def build_gate_checks(
    master: dict[str, Any],
    operation: dict[str, Any],
    health: dict[str, Any],
    sla: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    min_success_rate = float(os.getenv("PHASE364_MIN_SUCCESS_RATE_7D", "95"))
    min_sla_score = float(os.getenv("PHASE364_MIN_SLA_SCORE", "75"))
    min_health_score = float(os.getenv("PHASE364_MIN_HEALTH_SCORE", "90"))
    min_streak_days = int(os.getenv("PHASE364_MIN_SUCCESSFUL_STREAK_DAYS", "1"))
    max_incidents = int(os.getenv("PHASE364_MAX_INCIDENTS_7D", "0"))

    checks: dict[str, dict[str, Any]] = {}

    def add(name: str, passed: bool, value: Any, expected: Any, severity: str) -> None:
        checks[name] = {
            "passed": bool(passed),
            "value": value,
            "expected": expected,
            "severity": severity,
        }

    add(
        "master_status",
        master.get("status") == "PASS",
        master.get("status"),
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
        "autonomous_operation",
        operation.get("operation_status") == "PASS",
        operation.get("operation_status"),
        "PASS",
        "CRITICAL",
    )

    add(
        "recovery_state",
        operation.get("recovery_state") in {
            "NOT_REQUIRED",
            "RECOVERED_AFTER_RETRY",
        },
        operation.get("recovery_state"),
        "NOT_REQUIRED or RECOVERED_AFTER_RETRY",
        "WARNING",
    )

    add(
        "health_status",
        health.get("health_status") in {
            "HEALTHY",
            "DEGRADED",
        },
        health.get("health_status"),
        "HEALTHY or DEGRADED",
        "CRITICAL",
    )

    add(
        "health_score",
        float(health.get("health_score") or 0) >= min_health_score,
        float(health.get("health_score") or 0),
        f">= {min_health_score}",
        "WARNING",
    )

    add(
        "sla_status",
        sla.get("sla_status") in {
            "SLA_PASS",
            "SLA_WARN",
        },
        sla.get("sla_status"),
        "SLA_PASS or SLA_WARN",
        "CRITICAL",
    )

    add(
        "sla_score",
        float(sla.get("sla_score") or 0) >= min_sla_score,
        float(sla.get("sla_score") or 0),
        f">= {min_sla_score}",
        "WARNING",
    )

    add(
        "success_rate_7d",
        float(sla.get("success_rate_7d") or 0) >= min_success_rate,
        float(sla.get("success_rate_7d") or 0),
        f">= {min_success_rate}",
        "WARNING",
    )

    add(
        "incident_count_7d",
        int(sla.get("incident_count_7d") or 0) <= max_incidents,
        int(sla.get("incident_count_7d") or 0),
        f"<= {max_incidents}",
        "CRITICAL",
    )

    add(
        "successful_streak_days",
        int(sla.get("successful_streak_days") or 0) >= min_streak_days,
        int(sla.get("successful_streak_days") or 0),
        f">= {min_streak_days}",
        "WARNING",
    )

    add(
        "portfolio_cash_nonnegative",
        float(master.get("cash") or 0) >= 0,
        master.get("cash"),
        ">= 0",
        "CRITICAL",
    )

    add(
        "portfolio_nav_nonnegative",
        float(master.get("nav") or 0) >= 0,
        master.get("nav"),
        ">= 0",
        "CRITICAL",
    )

    for payload_name, payload in (
        ("master", master),
        ("operation", operation),
        ("health", health),
        ("sla", sla),
    ):
        for key in (
            "synthetic_market_data",
            "synthetic_signals",
            "fake_prices_allowed",
            "broker_api_used",
            "broker_credentials_used",
            "broker_order_submission_enabled",
            "real_money_trading_enabled",
            "live_money_release_authorized",
        ):
            add(
                f"safety_{payload_name}_{key}",
                payload.get(key) is False,
                payload.get(key),
                False,
                "CRITICAL",
            )

        add(
            f"safety_{payload_name}_fail_closed",
            payload.get("fail_closed_policy") is True,
            payload.get("fail_closed_policy"),
            True,
            "CRITICAL",
        )

    return checks


def classify_readiness(checks: dict[str, dict[str, Any]]) -> tuple[str, float, list[str]]:
    total = len(checks)
    passed = sum(1 for item in checks.values() if item["passed"])
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

    blocking = critical_failed + warning_failed

    safety_critical = [
        name
        for name in critical_failed
        if name.startswith("safety_")
    ]

    if safety_critical:
        return FAIL_CLOSED, score, blocking

    if critical_failed:
        return NOT_READY, score, blocking

    if warning_failed:
        return READY_WITH_OBSERVATION, score, blocking

    return READY, score, []


def persist(
    master: dict[str, Any],
    operation: dict[str, Any],
    health: dict[str, Any],
    sla: dict[str, Any],
    checks: dict[str, dict[str, Any]],
    readiness_status: str,
    readiness_score: float,
    blocking: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    readiness_date = str(sla["observation_date"])

    gate_open = readiness_status in {READY, READY_WITH_OBSERVATION}
    observation_required = readiness_status == READY_WITH_OBSERVATION
    operator_action_required = readiness_status in {NOT_READY, FAIL_CLOSED}

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "readiness_date": readiness_date,
        "readiness_status": readiness_status,
        "readiness_score": readiness_score,
        "blocking": blocking,
        "master_cycle_id": master.get("master_cycle_id"),
        "operation_id": operation.get("operation_id"),
        "health_id": health.get("health_id"),
        "observability_id": sla.get("observability_id"),
    }

    readiness = {
        "readiness_id": "P364R-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "readiness_date": readiness_date,
        "readiness_status": readiness_status,
        "readiness_score": readiness_score,
        "promotion_gate_open": gate_open,
        "observation_required": observation_required,
        "operator_action_required": operator_action_required,
        "master_status": master.get("status"),
        "master_final_state": master.get("final_state"),
        "autonomous_operation_status": operation.get("operation_status"),
        "recovery_state": operation.get("recovery_state"),
        "health_status": health.get("health_status"),
        "health_score": health.get("health_score"),
        "sla_status": sla.get("sla_status"),
        "sla_score": sla.get("sla_score"),
        "success_rate_7d": sla.get("success_rate_7d"),
        "recovery_rate_7d": sla.get("recovery_rate_7d"),
        "incident_count_7d": sla.get("incident_count_7d"),
        "successful_streak_days": sla.get("successful_streak_days"),
        "eligible_signals": master.get("eligible_signals"),
        "sized_candidates": master.get("sized_candidates"),
        "order_intents_created": master.get("order_intents_created"),
        "simulated_fills_created": master.get("simulated_fills_created"),
        "fills_settled": master.get("fills_settled"),
        "cash": master.get("cash"),
        "market_value": master.get("market_value"),
        "nav": master.get("nav"),
        "open_positions": master.get("open_positions"),
        "gate_checks": checks,
        "blocking_reasons": blocking,
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
        READINESS_TABLE,
        [readiness],
        "portfolio_id,readiness_date",
    )

    gate_seed = {
        "readiness_id": readiness["readiness_id"],
        "readiness_status": readiness_status,
        "gate_open": gate_open,
        "blocking": blocking,
    }

    gate = {
        "gate_audit_id": "P364G-" + stable_hash(gate_seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "audit_date": readiness_date,
        "readiness_id": readiness["readiness_id"],
        "readiness_status": readiness_status,
        "promotion_gate_open": gate_open,
        "observation_required": observation_required,
        "operator_action_required": operator_action_required,
        "approved_for_autonomous_paper_operations": gate_open,
        "approved_for_broker_trading": False,
        "approved_for_real_money_trading": False,
        "approved_for_live_money_release": False,
        "blocking_reasons": blocking,
        "evidence_sha256": stable_hash(gate_seed),
    }

    rest_upsert(
        GATE_TABLE,
        [gate],
        "portfolio_id,audit_date",
    )

    return readiness, gate


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.6.4",
        "",
        "## Production Paper Autonomous Operational Readiness + Promotion Gate",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Readiness Date: `{result['readiness_date']}`",
        f"- Readiness Status: **{result['readiness_status']}**",
        f"- Readiness Score: **{result['readiness_score']:.2f}%**",
        f"- Promotion Gate Open: **{'YES' if result['promotion_gate_open'] else 'NO'}**",
        f"- Observation Required: **{'YES' if result['observation_required'] else 'NO'}**",
        f"- Operator Action Required: **{'YES' if result['operator_action_required'] else 'NO'}**",
        "",
        "### Upstream State",
        "",
        f"- Master Status: **{result['master_status']}**",
        f"- Autonomous Operation Status: **{result['autonomous_operation_status']}**",
        f"- Recovery State: **{result['recovery_state']}**",
        f"- Health Status: **{result['health_status']}**",
        f"- SLA Status: **{result['sla_status']}**",
        "",
        "### Reliability",
        "",
        f"- 7-Day Success Rate: **{result['success_rate_7d']:.2f}%**",
        f"- 7-Day Recovery Rate: **{result['recovery_rate_7d']:.2f}%**",
        f"- 7-Day Incident Count: **{result['incident_count_7d']}**",
        f"- Successful Streak: **{result['successful_streak_days']} day(s)**",
        "",
        "### Promotion Scope",
        "",
        "- Autonomous Paper Operations: **ALLOWED only when gate is open**",
        "- Broker Trading: **NOT AUTHORIZED**",
        "- Real-Money Trading: **NOT AUTHORIZED**",
        "- Live-Money Release: **NOT AUTHORIZED**",
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

    if result["blocking_reasons"]:
        lines.extend(["", "### Blocking / Observation Reasons", ""])
        for reason in result["blocking_reasons"]:
            lines.append(f"- `{reason}`")

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
        default=os.getenv("PHASE364_APPROVER", "github-actions"),
    )
    args = parser.parse_args()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    run_upstream(args.approver)
    master, operation, health, sla = load_required()

    checks = build_gate_checks(master, operation, health, sla)
    readiness_status, readiness_score, blocking = classify_readiness(checks)

    readiness, gate = persist(
        master,
        operation,
        health,
        sla,
        checks,
        readiness_status,
        readiness_score,
        blocking,
    )

    result = {
        "version": "3.6.4",
        "status": (
            "PASS"
            if readiness_status in {READY, READY_WITH_OBSERVATION}
            else "FAIL"
        ),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "readiness_id": readiness["readiness_id"],
        "readiness_date": str(readiness["readiness_date"]),
        "readiness_status": readiness["readiness_status"],
        "readiness_score": float(readiness["readiness_score"]),
        "promotion_gate_open": bool(readiness["promotion_gate_open"]),
        "observation_required": bool(readiness["observation_required"]),
        "operator_action_required": bool(readiness["operator_action_required"]),
        "master_status": readiness.get("master_status"),
        "master_final_state": readiness.get("master_final_state"),
        "autonomous_operation_status": readiness.get("autonomous_operation_status"),
        "recovery_state": readiness.get("recovery_state"),
        "health_status": readiness.get("health_status"),
        "health_score": float(readiness.get("health_score") or 0),
        "sla_status": readiness.get("sla_status"),
        "sla_score": float(readiness.get("sla_score") or 0),
        "success_rate_7d": float(readiness.get("success_rate_7d") or 0),
        "recovery_rate_7d": float(readiness.get("recovery_rate_7d") or 0),
        "incident_count_7d": int(readiness.get("incident_count_7d") or 0),
        "successful_streak_days": int(readiness.get("successful_streak_days") or 0),
        "eligible_signals": int(readiness.get("eligible_signals") or 0),
        "sized_candidates": int(readiness.get("sized_candidates") or 0),
        "order_intents_created": int(readiness.get("order_intents_created") or 0),
        "simulated_fills_created": int(readiness.get("simulated_fills_created") or 0),
        "fills_settled": int(readiness.get("fills_settled") or 0),
        "cash": float(readiness.get("cash") or 0),
        "market_value": float(readiness.get("market_value") or 0),
        "nav": float(readiness.get("nav") or 0),
        "open_positions": int(readiness.get("open_positions") or 0),
        "blocking_reasons": blocking,
        "approved_for_autonomous_paper_operations": bool(
            gate["approved_for_autonomous_paper_operations"]
        ),
        "approved_for_broker_trading": False,
        "approved_for_real_money_trading": False,
        "approved_for_live_money_release": False,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": readiness["evidence_sha256"],
    }

    write_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if readiness_status in {NOT_READY, FAIL_CLOSED}:
        print(
            "PHASE364 FAIL-CLOSED: autonomous paper readiness gate is not open."
        )
        return 1

    print(
        "PHASE364 PASS: autonomous paper operational-readiness gate complete. "
        f"readiness={readiness_status}, "
        f"score={readiness_score:.2f}, "
        f"gate_open={result['promotion_gate_open']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
