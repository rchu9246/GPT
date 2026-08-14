#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.1
Production Operations Automation + Incident Guard

Purpose:
- Run/consume Phase 3.0 Control Center state.
- Detect operational incidents.
- Fail closed on unhealthy conditions.
- Keep an incident/audit artifact.
- Evaluate automatic recovery readiness without automatically resuming broker execution.
- Preserve SHADOW_ONLY_NO_BROKER safety.

This module never enables broker connectivity or real-money execution.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE30 = ROOT / "automation/v92/paper_trading_phase30_control_center.py"

MODE = os.getenv("PAPER_TRADING_MODE", "SHADOW_ONLY_NO_BROKER")
VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")

INCIDENT_FAIL_CLOSED = os.getenv("PHASE31_FAIL_CLOSED", "true").lower() == "true"
RECOVERY_REQUIRED_PASSES = max(1, int(os.getenv("PHASE31_RECOVERY_REQUIRED_PASSES", "2")))
MAX_STALE_DAYS = max(0, int(os.getenv("PHASE31_MAX_MARKET_STALE_DAYS", "3")))
MAX_DAILY_DRAWDOWN = float(os.getenv("PHASE31_MAX_DAILY_DRAWDOWN", "0.08"))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def run_phase30():
    if not PHASE30.exists():
        raise RuntimeError(f"Missing Phase 3.0 control center: {PHASE30}")

    proc = subprocess.run(
        [sys.executable, str(PHASE30)],
        cwd=ROOT,
        env=os.environ.copy(),
    )
    return proc.returncode


def incident_from_phase30(result: dict, phase30_rc: int):
    checks = result.get("checks") if isinstance(result.get("checks"), dict) else {}
    incidents = []

    def add(code, severity, message, observed=None):
        incidents.append({
            "code": code,
            "severity": severity,
            "message": message,
            "observed": observed,
            "detected_at": now_iso(),
        })

    if phase30_rc != 0:
        add("PHASE30_NONZERO_EXIT", "CRITICAL", "Phase 3.0 returned non-zero exit code.", phase30_rc)

    if result.get("system_health") != "PASS":
        add("SYSTEM_HEALTH_FAIL", "CRITICAL", "Phase 3.0 system health is not PASS.", result.get("system_health"))

    if not checks.get("status_completed", False):
        add("SNAPSHOT_INCOMPLETE", "CRITICAL", "Daily snapshot status is not completed.")

    if not checks.get("pipeline_completed", False):
        add("PIPELINE_INCOMPLETE", "CRITICAL", "Daily trading pipeline is not completed.")

    if not checks.get("latest_market_date_present", False):
        add("MARKET_DATE_MISSING", "CRITICAL", "Latest market date is missing.")

    if not checks.get("market_data_fresh", False):
        add(
            "MARKET_DATA_STALE",
            "HIGH",
            "Market data freshness check failed.",
            result.get("market_stale_days"),
        )

    if not checks.get("equity_non_negative", False):
        add("EQUITY_INVALID", "CRITICAL", "Equity check failed.", result.get("ledger", {}).get("equity"))

    if not checks.get("positions_within_limit", False):
        add("POSITION_LIMIT_BREACH", "HIGH", "Open positions exceed configured limit.")

    if not checks.get("daily_drawdown_within_limit", False):
        add(
            "DRAWDOWN_LIMIT_BREACH",
            "CRITICAL",
            "Daily drawdown exceeds configured limit.",
            result.get("daily_drawdown"),
        )

    if not checks.get("safety_mode_locked", False):
        add("SAFETY_MODE_UNLOCKED", "CRITICAL", "Safety mode lock failed.", result.get("mode"))

    stale_days = result.get("market_stale_days")
    if stale_days is not None:
        try:
            if int(stale_days) > MAX_STALE_DAYS:
                add("MARKET_STALE_HARD_LIMIT", "CRITICAL", "Market stale days exceed Phase 3.1 hard limit.", stale_days)
        except Exception:
            pass

    try:
        dd = float(result.get("daily_drawdown", 0))
        if dd > MAX_DAILY_DRAWDOWN:
            add("DRAWDOWN_HARD_LIMIT", "CRITICAL", "Daily drawdown exceeds Phase 3.1 hard limit.", dd)
    except Exception:
        add("DRAWDOWN_PARSE_ERROR", "HIGH", "Daily drawdown could not be parsed.")

    return incidents


def evaluate_recovery(phase30_result: dict, incidents: list):
    """
    Recovery is advisory only:
    - no critical/high incident
    - current Phase 3.0 health PASS
    - observation streak is at least the configured recovery threshold
    """
    blocking = [i for i in incidents if i.get("severity") in {"CRITICAL", "HIGH"}]
    streak = int(phase30_result.get("consecutive_pass_days", 0) or 0)

    ready = (
        not blocking
        and phase30_result.get("system_health") == "PASS"
        and streak >= RECOVERY_REQUIRED_PASSES
    )
    return {
        "recovery_ready": ready,
        "required_passes": RECOVERY_REQUIRED_PASSES,
        "observed_passes": streak,
        "automatic_resume_enabled": False,
        "manual_review_required": True,
    }


def build_summary(result):
    incidents = result["incidents"]
    recovery = result["recovery"]

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.1",
        "",
        "## Production Operations Automation + Incident Guard",
        "",
        f"- Status: **{result['status']}**",
        f"- Operations State: **{result['operations_state']}**",
        f"- Incident State: **{result['incident_state']}**",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['mode']}`",
        f"- Phase 3.0 Control State: `{result['phase30_control_state']}`",
        f"- Consecutive PASS days: **{result['consecutive_pass_days']}**",
        f"- Recovery Ready: **{'YES' if recovery['recovery_ready'] else 'NO'}**",
        "",
        "### Incident Guard",
        "",
    ]

    if incidents:
        lines += [
            "| Severity | Code | Message |",
            "|---|---|---|",
        ]
        for inc in incidents:
            lines.append(
                f"| {inc['severity']} | `{inc['code']}` | {inc['message']} |"
            )
    else:
        lines.append("- ✅ No active incidents.")

    lines += [
        "",
        "### Recovery Evaluation",
        "",
        f"- Required healthy passes: **{recovery['required_passes']}**",
        f"- Observed healthy passes: **{recovery['observed_passes']}**",
        f"- Automatic resume: **DISABLED**",
        f"- Manual review required: **YES**",
        "",
        "### Safety Controls",
        "",
        "- Fail Closed: **YES**",
        "- Kill Switch: **ARMED**",
        "- Broker Trading: **DISABLED**",
        "- Real Money: **DISABLED**",
        "- Automatic Broker Resume: **DISABLED**",
        "",
        "> Phase 3.1 automates operational monitoring and incident handling only. "
        "It does not connect to a broker and does not enable real-money trading.",
    ]

    return "\n".join(lines) + "\n"


def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety lock: Phase 3.1 requires PAPER_TRADING_MODE=SHADOW_ONLY_NO_BROKER"
        )

    phase30_rc = run_phase30()
    phase30_result = load_json(ROOT / "phase30_result.json", {})

    if not phase30_result:
        raise RuntimeError("Missing or invalid phase30_result.json")

    incidents = incident_from_phase30(phase30_result, phase30_rc)
    recovery = evaluate_recovery(phase30_result, incidents)

    blocking = [i for i in incidents if i.get("severity") in {"CRITICAL", "HIGH"}]

    if blocking:
        incident_state = "ACTIVE"
        operations_state = "LOCKED"
        status = "FAIL" if INCIDENT_FAIL_CLOSED else "WARN"
    else:
        incident_state = "CLEAR"
        control_state = phase30_result.get("control_state", "BLOCKED")
        if control_state == "READY":
            operations_state = "READY"
        elif control_state == "OBSERVATION":
            operations_state = "OBSERVATION"
        else:
            operations_state = "LOCKED"
        status = "PASS"

    result = {
        "version": "3.1",
        "checked_at": now_iso(),
        "strategy_version": VERSION,
        "mode": MODE,
        "status": status,
        "operations_state": operations_state,
        "incident_state": incident_state,
        "fail_closed": INCIDENT_FAIL_CLOSED,
        "phase30_exit_code": phase30_rc,
        "phase30_control_state": phase30_result.get("control_state"),
        "system_health": phase30_result.get("system_health"),
        "consecutive_pass_days": phase30_result.get("consecutive_pass_days", 0),
        "latest_market_date": phase30_result.get("latest_market_date"),
        "market_stale_days": phase30_result.get("market_stale_days"),
        "daily_drawdown": phase30_result.get("daily_drawdown"),
        "incidents": incidents,
        "recovery": recovery,
        "ledger": phase30_result.get("ledger", {}),
        "safety": {
            "kill_switch": "ARMED",
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "automatic_resume_enabled": False,
            "manual_review_required": True,
        },
    }

    (ROOT / "phase31_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ROOT / "phase31_incidents.json").write_text(
        json.dumps(incidents, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ROOT / "phase31_summary.md").write_text(
        build_summary(result),
        encoding="utf-8",
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if status == "FAIL" and INCIDENT_FAIL_CLOSED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
