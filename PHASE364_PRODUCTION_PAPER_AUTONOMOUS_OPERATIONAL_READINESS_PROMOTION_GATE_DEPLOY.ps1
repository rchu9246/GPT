#requires -Version 5.1
<#
PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.4 — Production Paper Autonomous Operational Readiness + Promotion Gate

Purpose
-------
Aggregate Phase 3.6.0 through 3.6.3 into one explicit operational-readiness gate.

Readiness states
----------------
  READY
  READY_WITH_OBSERVATION
  NOT_READY
  FAIL_CLOSED

Important
---------
This is a PAPER-ONLY readiness gate.
It does NOT authorize broker trading, live-money trading, or live-money release.

Created/overwritten
-------------------
  supabase/PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE.sql
  automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py
  .github/workflows/gpt-quant-v92-paper-trading-phase364-production-paper-autonomous-operational-readiness-promotion-gate.yml
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

Section "GPT Quant V9.2 — Phase 3.6.4 Operational Readiness + Promotion Gate"

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
    "automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py",
    "automation/v92/paper_trading_phase361_production_paper_autonomous_daily_operations_failure_recovery.py",
    "automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py",
    "automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py",
    "supabase/PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required Phase 3.6.x dependency missing: $item"
    }
}

$sqlTarget = "supabase/PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE.sql"
$pythonTarget = "automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase364-production-paper-autonomous-operational-readiness-promotion-gate.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase364-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.6.4 Supabase readiness-gate schema"

$sql = @'
begin;

create table if not exists public.paper_operational_readiness_v92 (
    readiness_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    readiness_date date not null,

    readiness_status text not null,
    readiness_score numeric not null,
    promotion_gate_open boolean not null default false,
    observation_required boolean not null default false,
    operator_action_required boolean not null default false,

    master_status text,
    master_final_state text,
    autonomous_operation_status text,
    recovery_state text,
    health_status text,
    health_score numeric,
    sla_status text,
    sla_score numeric,

    success_rate_7d numeric,
    recovery_rate_7d numeric,
    incident_count_7d integer,
    successful_streak_days integer,

    eligible_signals integer,
    sized_candidates integer,
    order_intents_created integer,
    simulated_fills_created integer,
    fills_settled integer,

    cash numeric,
    market_value numeric,
    nav numeric,
    open_positions integer,

    gate_checks jsonb not null default '{}'::jsonb,
    blocking_reasons jsonb not null default '[]'::jsonb,

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

create unique index if not exists uq_paper_operational_readiness_v92_portfolio_date
    on public.paper_operational_readiness_v92 (portfolio_id, readiness_date);

create table if not exists public.paper_promotion_gate_audit_v92 (
    gate_audit_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    audit_date date not null,

    readiness_id text not null,
    readiness_status text not null,
    promotion_gate_open boolean not null default false,
    observation_required boolean not null default false,
    operator_action_required boolean not null default false,

    approved_for_autonomous_paper_operations boolean not null default false,
    approved_for_broker_trading boolean not null default false,
    approved_for_real_money_trading boolean not null default false,
    approved_for_live_money_release boolean not null default false,

    blocking_reasons jsonb not null default '[]'::jsonb,
    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_promotion_gate_audit_v92_portfolio_date
    on public.paper_promotion_gate_audit_v92 (portfolio_id, audit_date);

alter table public.paper_operational_readiness_v92 enable row level security;
alter table public.paper_promotion_gate_audit_v92 enable row level security;

comment on table public.paper_operational_readiness_v92 is
'GPT Quant V9.2 operational-readiness gate for autonomous paper trading only.';

comment on table public.paper_promotion_gate_audit_v92 is
'GPT Quant V9.2 promotion-gate audit. Broker and real-money approvals are hard-disabled.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.4 Python readiness-gate engine"

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
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.6.4 GitHub Actions readiness-gate workflow"

$workflow = @'
name: GPT Quant Phase 3.6.4 - Production Paper Autonomous Operational Readiness Promotion Gate

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
    - cron: "30 11 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase364-production-paper-operational-readiness
  cancel-in-progress: false

jobs:
  operational-readiness-promotion-gate:
    runs-on: ubuntu-latest
    timeout-minutes: 150

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      FINMIND_TOKEN: ${{ secrets.FINMIND_TOKEN }}

      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}

      PHASE364_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE363_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE362_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE361_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE360_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE364_APPROVER: ${{ inputs.approver || 'github-actions' }}

      PHASE364_MIN_SUCCESS_RATE_7D: "95"
      PHASE364_MIN_SLA_SCORE: "75"
      PHASE364_MIN_HEALTH_SCORE: "90"
      PHASE364_MIN_SUCCESSFUL_STREAK_DAYS: "1"
      PHASE364_MAX_INCIDENTS_7D: "0"

      PHASE363_MAX_CYCLE_SECONDS: "120"
      PHASE363_MIN_SUCCESS_RATE_7D: "95"
      PHASE363_MAX_RECOVERY_RATE_7D: "25"
      PHASE363_MAX_INCIDENTS_7D: "0"

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

      - name: Validate Phase 3.6.4 readiness-gate contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py
          test -f automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py
          test -f supabase/PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE.sql

          grep -q 'PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE' \
            automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py

          grep -q 'READY_WITH_OBSERVATION' \
            automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py

          grep -q 'FAIL_CLOSED' \
            automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py

          grep -q '"approved_for_broker_trading": False' \
            automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py

          grep -q '"approved_for_real_money_trading": False' \
            automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py

          echo "Phase 3.6.4 readiness-gate contract: PASS"

      - name: Execute Phase 3.6.4 operational readiness gate
        shell: bash
        run: |
          set -euo pipefail

          APPROVER="${{ inputs.approver }}"
          if [ -z "${APPROVER}" ]; then
            APPROVER="github-actions"
          fi

          python automation/v92/paper_trading_phase364_production_paper_autonomous_operational_readiness_promotion_gate.py \
            --approver "${APPROVER}"

      - name: Validate Phase 3.6.4 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase364_output/phase364_operational_readiness.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase364_output/phase364_operational_readiness.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.6.4", data
          assert data["readiness_status"] in {
              "READY",
              "READY_WITH_OBSERVATION",
              "NOT_READY",
              "FAIL_CLOSED",
          }, data

          assert 0 <= data["readiness_score"] <= 100, data

          assert data["approved_for_broker_trading"] is False, data
          assert data["approved_for_real_money_trading"] is False, data
          assert data["approved_for_live_money_release"] is False, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          if data["readiness_status"] in {"NOT_READY", "FAIL_CLOSED"}:
              raise SystemExit("Operational readiness gate is closed")

          assert data["status"] == "PASS", data
          assert data["promotion_gate_open"] is True, data
          assert data["approved_for_autonomous_paper_operations"] is True, data

          print("Phase 3.6.4 output validation: PASS")
          PY

      - name: Upload Phase 3.6.4 readiness evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase364-production-paper-readiness-${{ github.run_id }}
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
            phase363_output/
            phase364_output/
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
    'PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE',
    'paper_operational_readiness_v92',
    'paper_promotion_gate_audit_v92',
    'READY_WITH_OBSERVATION',
    'NOT_READY',
    'FAIL_CLOSED',
    'classify_readiness',
    '"approved_for_broker_trading": False',
    '"approved_for_real_money_trading": False',
    '"approved_for_live_money_release": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.6.4 token missing: $needle"
    }
}

Write-Host "Phase 3.6.4 operational-readiness contract scan: PASS" -ForegroundColor Green

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
        Write-Host "No staged Phase 3.6.4 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.6.4 operational readiness promotion gate"
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

Write-Host "Readiness states:" -ForegroundColor Cyan
Write-Host "  READY"
Write-Host "  READY_WITH_OBSERVATION"
Write-Host "  NOT_READY"
Write-Host "  FAIL_CLOSED"
Write-Host ""

Write-Host "Promotion scope:" -ForegroundColor Cyan
Write-Host "  Autonomous paper operations may be approved when gate is open."
Write-Host "  Broker trading approval is ALWAYS FALSE."
Write-Host "  Real-money trading approval is ALWAYS FALSE."
Write-Host "  Live-money release approval is ALWAYS FALSE."
Write-Host ""

Write-Host "Default readiness thresholds:" -ForegroundColor Cyan
Write-Host "  Min 7-day success rate: 95%"
Write-Host "  Min health score: 90%"
Write-Host "  Min SLA score: 75%"
Write-Host "  Min successful streak: 1 day"
Write-Host "  Max 7-day incidents: 0"
Write-Host ""

Write-Host "Supabase SQL required before first Phase 3.6.4 run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE364_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_READINESS_PROMOTION_GATE.sql"
Write-Host ""

Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 30 11 * * 1-5"
Write-Host "  11:30 UTC = 19:30 Taiwan time, weekdays"
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
Write-Host "  1) Run Phase 3.6.4 Supabase SQL once."
Write-Host "  2) Commit/Push Phase 3.6.4 files (or deploy with -AutoGit)."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.4 - Production Paper Autonomous Operational Readiness Promotion Gate."
Write-Host "  4) Confirm Readiness Status=READY or READY_WITH_OBSERVATION."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
