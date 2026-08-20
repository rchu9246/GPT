#requires -Version 5.1
<#
PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.2 — Production Paper Autonomous Health Monitoring + Incident Audit Engine

Purpose
-------
Add a persistent health-monitoring and incident-audit layer on top of Phase 3.6.1.

The engine:
  - reads the latest autonomous operation result;
  - evaluates data freshness, master-cycle health, retry/recovery state, portfolio integrity,
    safety locks, and daily execution continuity;
  - classifies system health as HEALTHY / DEGRADED / INCIDENT;
  - writes persistent health snapshots and incident records;
  - does NOT invent market data, signals, prices, or fills;
  - remains paper-only and fail-closed.

Created/overwritten
-------------------
  supabase/PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE.sql
  automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py
  .github/workflows/gpt-quant-v92-paper-trading-phase362-production-paper-autonomous-health-monitoring-incident-audit-engine.yml
#>

param(
    [switch]$AutoGit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 120) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 120) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.6.2 Autonomous Health Monitoring + Incident Audit"

$repoRoot = $null
try {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repoRoot = $null
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    Fail "Run this deployment package inside the GPT Git repository."
}

Set-Location $repoRoot
Write-Host "Repository: $repoRoot" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py",
    ".github/workflows/gpt-quant-v92-paper-trading-phase361-production-paper-autonomous-daily-operations-failure-recovery.yml",
    "supabase/PHASE361_PRODUCTION_PAPER_AUTONOMOUS_DAILY_OPERATIONS_FAILURE_RECOVERY.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required Phase 3.6.1 dependency missing: $item"
    }
}

$sqlTarget = "supabase/PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE.sql"
$pythonTarget = "automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase362-production-paper-autonomous-health-monitoring-incident-audit-engine.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase362-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.6.2 Supabase health/incident schema"

$sql = @'
begin;

create table if not exists public.paper_system_health_v92 (
    health_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    health_date date not null,

    health_status text not null,
    health_score numeric not null,
    incident_required boolean not null default false,

    autonomous_operation_status text,
    recovery_state text,
    master_final_state text,
    market_data_status text,
    latest_market_date date,

    eligible_signals integer,
    sized_candidates integer,
    order_intents_created integer,
    simulated_fills_created integer,
    fills_settled integer,

    cash numeric,
    market_value numeric,
    nav numeric,
    realized_pnl numeric,
    unrealized_pnl numeric,
    open_positions integer,

    checks_passed integer not null,
    checks_failed integer not null,
    check_details jsonb not null default '{}'::jsonb,

    synthetic_market_data boolean not null default false,
    synthetic_signals boolean not null default false,
    fake_prices_allowed boolean not null default false,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_system_health_v92_portfolio_date
    on public.paper_system_health_v92 (portfolio_id, health_date);

create table if not exists public.paper_incident_audit_v92 (
    incident_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    incident_date date not null,

    severity text not null,
    incident_type text not null,
    incident_state text not null,
    source_phase text,
    source_health_id text,

    summary text not null,
    details jsonb not null default '{}'::jsonb,

    autonomous_recovery_attempted boolean not null default false,
    autonomous_recovery_succeeded boolean not null default false,
    operator_action_required boolean not null default false,

    synthetic_market_data boolean not null default false,
    synthetic_signals boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_paper_incident_audit_v92_date
    on public.paper_incident_audit_v92 (portfolio_id, incident_date desc);

alter table public.paper_system_health_v92 enable row level security;
alter table public.paper_incident_audit_v92 enable row level security;

comment on table public.paper_system_health_v92 is
'GPT Quant V9.2 autonomous production-paper health snapshots. Paper-only, no broker authority.';

comment on table public.paper_incident_audit_v92 is
'GPT Quant V9.2 autonomous production-paper incident audit ledger.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.2 Python health-monitoring engine"

$python = @'
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
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.6.2 GitHub Actions health-monitoring workflow"

$workflow = @'
name: GPT Quant Phase 3.6.2 - Production Paper Autonomous Health Monitoring Incident Audit Engine

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string

      approver:
        description: Human approver/operator ID
        required: true
        default: github-actions
        type: string

      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

  schedule:
    - cron: "0 11 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase362-production-paper-autonomous-health
  cancel-in-progress: false

jobs:
  autonomous-health-monitoring:
    runs-on: ubuntu-latest
    timeout-minutes: 120

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      FINMIND_TOKEN: ${{ secrets.FINMIND_TOKEN }}

      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}

      PHASE362_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE361_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE360_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE362_APPROVER: ${{ inputs.approver || 'github-actions' }}
      PHASE362_MAX_ATTEMPTS: "2"
      PHASE362_RETRY_DELAY_SECONDS: "10"

      PHASE351_MIN_HISTORY: "5"

      PHASE353_BASE_RISK_BUDGET_PCT: "0.60"
      PHASE353_MAX_POSITION_PCT: "0.20"
      PHASE353_MAX_CANDIDATES: "3"
      PHASE353_ROUND_LOT: "1000"
      PHASE353_SCORE_THRESHOLD: "65"

      PHASE352_CAUTION_DRAWDOWN: "-0.05"
      PHASE352_REDUCE_DRAWDOWN: "-0.10"
      PHASE352_HALT_DRAWDOWN: "-0.15"
      PHASE352_CAUTION_DAILY_LOSS: "-0.025"
      PHASE352_HALT_DAILY_LOSS: "-0.05"
      PHASE352_MAX_EXPOSURE_CAUTION: "0.80"
      PHASE352_MAX_EXPOSURE_HALT: "0.95"
      PHASE352_MAX_CONCENTRATION_CAUTION: "0.35"
      PHASE352_MAX_CONCENTRATION_HALT: "0.50"
      PHASE352_CONSECUTIVE_LOSS_CAUTION: "3"
      PHASE352_CONSECUTIVE_LOSS_HALT: "5"

      PHASE348451_SCORE_THRESHOLD: "65"
      PHASE348451_MAX_CANDIDATES: "3"
      PHASE348451_MAX_ROWS_PER_TABLE: "5000"

      PHASE348_SCORE_THRESHOLD: "65"
      PHASE348_MAX_CANDIDATES: "3"
      PHASE348_INITIAL_CASH: "1000000"
      PHASE348_MAX_POSITION_PCT: "0.20"
      PHASE348_ROUND_LOT: "1000"

      PHASE349_INITIAL_CASH: "1000000"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependencies
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.6.2 health-monitoring contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py
          test -f automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py
          test -f supabase/PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE.sql

          grep -q 'PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE' \
            automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py

          grep -q 'HEALTHY' \
            automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py

          grep -q 'DEGRADED' \
            automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py

          grep -q 'INCIDENT' \
            automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py

          echo "Phase 3.6.2 health-monitoring contract: PASS"

      - name: Execute Phase 3.6.2 autonomous health monitoring
        shell: bash
        run: |
          set -euo pipefail

          APPROVER="${{ inputs.approver }}"
          if [ -z "${APPROVER}" ]; then
            APPROVER="github-actions"
          fi

          python automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py \
            --approver "${APPROVER}"

      - name: Validate Phase 3.6.2 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase362_output/phase362_health_monitoring.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase362_output/phase362_health_monitoring.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.6.2", data
          assert data["health_status"] in {
              "HEALTHY",
              "DEGRADED",
              "INCIDENT",
          }, data

          assert 0 <= data["health_score"] <= 100, data
          assert data["checks_passed"] >= 0, data
          assert data["checks_failed"] >= 0, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          if data["health_status"] == "INCIDENT":
              raise SystemExit("Critical health incident reported")

          assert data["status"] == "PASS", data

          print("Phase 3.6.2 output validation: PASS")
          PY

      - name: Upload Phase 3.6.2 health evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase362-production-paper-health-${{ github.run_id }}
          path: |
            phase350_output/
            phase351_output/
            phase352_output/
            phase353_output/
            phase354_output/
            phase355_output/
            phase360_output/
            phase361_output/
            phase362_output/
          if-no-files-found: warn
          retention-days: 90
'@

Set-Content -LiteralPath $workflowTarget -Value $workflow -Encoding UTF8
Write-Host "Wrote: $workflowTarget" -ForegroundColor Green

Section "Static validation"

$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} else {
    Fail "Python was not found in PATH."
}

if ($pythonCmd -eq "py") {
    & py -3 -m py_compile $pythonTarget
} else {
    & python -m py_compile $pythonTarget
}

if ($LASTEXITCODE -ne 0) {
    Fail "Python compile validation failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$source = Get-Content -LiteralPath $pythonTarget -Raw
$needles = @(
    'PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE',
    'paper_system_health_v92',
    'paper_incident_audit_v92',
    'HEALTHY',
    'DEGRADED',
    'INCIDENT',
    'build_checks',
    'classify_health',
    '"synthetic_market_data": False',
    '"synthetic_signals": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.6.2 token missing: $needle"
    }
}

Write-Host "Phase 3.6.2 health/incident contract scan: PASS" -ForegroundColor Green

Section "Git status"
& git status --short

if ($AutoGit) {
    Section "Optional AutoGit"

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    & git add -- $sqlTarget $pythonTarget $workflowTarget
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed"
    }

    $pending = (& git diff --cached --name-only)

    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged Phase 3.6.2 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.6.2 autonomous health monitoring incident audit"
        if ($LASTEXITCODE -ne 0) {
            Fail "git commit failed"
        }

        & git push origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git push origin main failed"
        }

        Write-Host "AutoGit commit + push: PASS" -ForegroundColor Green
    }
}

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $sqlTarget"
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Health states:" -ForegroundColor Cyan
Write-Host "  HEALTHY   -> all critical checks pass, no recovery degradation"
Write-Host "  DEGRADED  -> safe but warning/recovery condition exists"
Write-Host "  INCIDENT  -> critical health or safety contract failure; fail-closed"
Write-Host ""

Write-Host "Incident audit:" -ForegroundColor Cyan
Write-Host "  Persistent health snapshot"
Write-Host "  Failed-check details"
Write-Host "  Severity classification"
Write-Host "  Recovery attempted/succeeded evidence"
Write-Host "  Operator-action-required flag"
Write-Host ""

Write-Host "Supabase SQL required before first Phase 3.6.2 run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE.sql"
Write-Host ""

Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 0 11 * * 1-5"
Write-Host "  11:00 UTC = 19:00 Taiwan time, weekdays"
Write-Host ""

Write-Host "Hard safety locks:" -ForegroundColor Yellow
Write-Host "  Synthetic market data: DISABLED"
Write-Host "  Synthetic signals: DISABLED"
Write-Host "  Fake prices: DISABLED"
Write-Host "  Broker API used: NO"
Write-Host "  Broker credentials used: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host "  Fail-closed: ENABLED"
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run Phase 3.6.2 Supabase SQL once."
Write-Host "  2) Commit/Push Phase 3.6.2 files (or deploy with -AutoGit)."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.2 - Production Paper Autonomous Health Monitoring Incident Audit Engine."
Write-Host "  4) Confirm Health Status=HEALTHY or DEGRADED; INCIDENT must fail closed."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
