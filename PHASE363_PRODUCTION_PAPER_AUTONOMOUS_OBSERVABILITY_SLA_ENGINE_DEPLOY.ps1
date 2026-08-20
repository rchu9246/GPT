#requires -Version 5.1
<#
PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.3 — Production Paper Autonomous Observability + SLA Engine

Purpose
-------
Add persistent observability and SLA measurement on top of Phase 3.6.2.

Capabilities
------------
  - Measures end-to-end autonomous cycle duration
  - Measures stage durations from Phase 3.6.0 master evidence
  - Tracks daily success / degraded / incident state
  - Tracks recovery usage
  - Tracks incident count
  - Computes rolling success rate and recovery rate
  - Computes consecutive successful-operation streak
  - Evaluates SLA thresholds
  - Persists observability snapshots and SLA audit rows
  - Remains paper-only / no broker / no real-money
  - Fail-closed on critical safety contract violations

Created/overwritten
-------------------
  supabase/PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE.sql
  automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py
  .github/workflows/gpt-quant-v92-paper-trading-phase363-production-paper-autonomous-observability-sla-engine.yml
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

Section "GPT Quant V9.2 — Phase 3.6.3 Autonomous Observability + SLA Engine"

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
    "automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py",
    ".github/workflows/gpt-quant-v92-paper-trading-phase362-production-paper-autonomous-health-monitoring-incident-audit-engine.yml",
    "supabase/PHASE362_PRODUCTION_PAPER_AUTONOMOUS_HEALTH_MONITORING_INCIDENT_AUDIT_ENGINE.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required Phase 3.6.2 dependency missing: $item"
    }
}

$sqlTarget = "supabase/PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE.sql"
$pythonTarget = "automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase363-production-paper-autonomous-observability-sla-engine.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase363-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.6.3 Supabase observability/SLA schema"

$sql = @'
begin;

create table if not exists public.paper_observability_daily_v92 (
    observability_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    observation_date date not null,

    health_status text not null,
    autonomous_operation_status text,
    recovery_state text,
    master_final_state text,

    end_to_end_duration_seconds numeric,
    stage_duration_seconds jsonb not null default '{}'::jsonb,

    success_rate_7d numeric,
    recovery_rate_7d numeric,
    incident_count_7d integer,
    successful_streak_days integer,

    sla_status text not null,
    sla_score numeric not null,
    sla_details jsonb not null default '{}'::jsonb,

    cash numeric,
    market_value numeric,
    nav numeric,
    open_positions integer,

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

create unique index if not exists uq_paper_observability_daily_v92_portfolio_date
    on public.paper_observability_daily_v92 (portfolio_id, observation_date);

create table if not exists public.paper_sla_audit_v92 (
    sla_audit_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    audit_date date not null,

    sla_status text not null,
    overall_score numeric not null,

    max_cycle_seconds numeric not null,
    min_success_rate_7d numeric not null,
    max_recovery_rate_7d numeric not null,
    max_incidents_7d integer not null,

    measured_cycle_seconds numeric,
    measured_success_rate_7d numeric,
    measured_recovery_rate_7d numeric,
    measured_incidents_7d integer,

    breach_reasons jsonb not null default '[]'::jsonb,
    operator_action_required boolean not null default false,

    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_sla_audit_v92_portfolio_date
    on public.paper_sla_audit_v92 (portfolio_id, audit_date);

alter table public.paper_observability_daily_v92 enable row level security;
alter table public.paper_sla_audit_v92 enable row level security;

comment on table public.paper_observability_daily_v92 is
'GPT Quant V9.2 production-paper observability ledger with rolling health and duration metrics.';

comment on table public.paper_sla_audit_v92 is
'GPT Quant V9.2 production-paper SLA audit ledger. No broker or real-money authority.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.3 Python observability/SLA engine"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase363_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE363_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py"
HEALTH_JSON = ROOT / "phase362_output/phase362_health_monitoring.json"
MASTER_JSON = ROOT / "phase360_output/phase360_master_cycle.json"
OP_JSON = ROOT / "phase361_output/phase361_autonomous_operation.json"

OBS_TABLE = "paper_observability_daily_v92"
SLA_TABLE = "paper_sla_audit_v92"
HEALTH_TABLE = "paper_system_health_v92"
INCIDENT_TABLE = "paper_incident_audit_v92"
OPERATIONS_TABLE = "paper_autonomous_operations_v92"

RESULT_JSON = OUT / "phase363_observability_sla.json"
RESULT_MD = OUT / "phase363_observability_sla.md"

CONTRACT = "PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE"

SLA_PASS = "SLA_PASS"
SLA_WARN = "SLA_WARN"
SLA_BREACH = "SLA_BREACH"


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


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
        raise RuntimeError(f"Phase 3.6.2 failed with exit code {proc.returncode}")

    if not HEALTH_JSON.exists():
        raise RuntimeError("Phase 3.6.2 health evidence missing")

    health = read_json(HEALTH_JSON)
    if health.get("health_status") == "INCIDENT":
        raise RuntimeError("Phase 3.6.2 critical incident is active")

    return health


def stage_durations(master: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}

    for stage in master.get("stages") or []:
        start = parse_dt(stage.get("started_at"))
        end = parse_dt(stage.get("completed_at"))
        if start and end:
            result[stage["stage_id"]] = round((end - start).total_seconds(), 3)

    return result


def cycle_duration(master: dict[str, Any]) -> float | None:
    stages = master.get("stages") or []
    starts = [parse_dt(x.get("started_at")) for x in stages]
    ends = [parse_dt(x.get("completed_at")) for x in stages]
    starts = [x for x in starts if x]
    ends = [x for x in ends if x]

    if not starts or not ends:
        return None

    return round((max(ends) - min(starts)).total_seconds(), 3)


def rolling_metrics(observation_date: str) -> dict[str, Any]:
    dt = datetime.fromisoformat(observation_date).date()
    start = (dt - timedelta(days=6)).isoformat()

    operations = rest_get(
        OPERATIONS_TABLE,
        [
            ("select", "operation_date,operation_status,recovery_state"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("operation_date", f"gte.{start}"),
            ("operation_date", f"lte.{observation_date}"),
            ("order", "operation_date.asc"),
        ],
    )

    incidents = rest_get(
        INCIDENT_TABLE,
        [
            ("select", "incident_date,severity,incident_state"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("incident_date", f"gte.{start}"),
            ("incident_date", f"lte.{observation_date}"),
        ],
    )

    total = len(operations)
    passed = sum(1 for x in operations if x.get("operation_status") == "PASS")
    recovered = sum(1 for x in operations if x.get("recovery_state") == "RECOVERED_AFTER_RETRY")

    success_rate = round((passed / total) * 100.0, 2) if total else 0.0
    recovery_rate = round((recovered / total) * 100.0, 2) if total else 0.0

    streak = 0
    for item in reversed(operations):
        if item.get("operation_status") == "PASS":
            streak += 1
        else:
            break

    return {
        "success_rate_7d": success_rate,
        "recovery_rate_7d": recovery_rate,
        "incident_count_7d": len(incidents),
        "successful_streak_days": streak,
    }


def evaluate_sla(
    cycle_seconds: float | None,
    rolling: dict[str, Any],
) -> tuple[str, float, dict[str, Any], list[str]]:
    max_cycle_seconds = float(os.getenv("PHASE363_MAX_CYCLE_SECONDS", "120"))
    min_success_rate_7d = float(os.getenv("PHASE363_MIN_SUCCESS_RATE_7D", "95"))
    max_recovery_rate_7d = float(os.getenv("PHASE363_MAX_RECOVERY_RATE_7D", "25"))
    max_incidents_7d = int(os.getenv("PHASE363_MAX_INCIDENTS_7D", "0"))

    checks = {
        "cycle_duration": {
            "passed": cycle_seconds is not None and cycle_seconds <= max_cycle_seconds,
            "value": cycle_seconds,
            "limit": max_cycle_seconds,
        },
        "success_rate_7d": {
            "passed": rolling["success_rate_7d"] >= min_success_rate_7d,
            "value": rolling["success_rate_7d"],
            "limit": min_success_rate_7d,
        },
        "recovery_rate_7d": {
            "passed": rolling["recovery_rate_7d"] <= max_recovery_rate_7d,
            "value": rolling["recovery_rate_7d"],
            "limit": max_recovery_rate_7d,
        },
        "incident_count_7d": {
            "passed": rolling["incident_count_7d"] <= max_incidents_7d,
            "value": rolling["incident_count_7d"],
            "limit": max_incidents_7d,
        },
    }

    passed = sum(1 for x in checks.values() if x["passed"])
    score = round((passed / len(checks)) * 100.0, 2)

    breaches = [name for name, item in checks.items() if not item["passed"]]

    if not breaches:
        status = SLA_PASS
    elif score >= 75.0:
        status = SLA_WARN
    else:
        status = SLA_BREACH

    return status, score, checks, breaches


def persist(
    health: dict[str, Any],
    master: dict[str, Any],
    operation: dict[str, Any],
    stage_seconds: dict[str, float],
    total_seconds: float | None,
    rolling: dict[str, Any],
    sla_status: str,
    sla_score: float,
    sla_details: dict[str, Any],
    breaches: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    observation_date = str(health["health_date"])

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "observation_date": observation_date,
        "health_status": health["health_status"],
        "cycle_seconds": total_seconds,
        "rolling": rolling,
        "sla_status": sla_status,
        "sla_score": sla_score,
        "breaches": breaches,
    }

    obs = {
        "observability_id": "P363O-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "observation_date": observation_date,
        "health_status": health["health_status"],
        "autonomous_operation_status": operation.get("operation_status"),
        "recovery_state": operation.get("recovery_state"),
        "master_final_state": master.get("final_state"),
        "end_to_end_duration_seconds": total_seconds,
        "stage_duration_seconds": stage_seconds,
        "success_rate_7d": rolling["success_rate_7d"],
        "recovery_rate_7d": rolling["recovery_rate_7d"],
        "incident_count_7d": rolling["incident_count_7d"],
        "successful_streak_days": rolling["successful_streak_days"],
        "sla_status": sla_status,
        "sla_score": sla_score,
        "sla_details": sla_details,
        "cash": master.get("cash"),
        "market_value": master.get("market_value"),
        "nav": master.get("nav"),
        "open_positions": int(master.get("open_positions") or 0),
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

    rest_upsert(OBS_TABLE, [obs], "portfolio_id,observation_date")

    sla_seed = {
        "portfolio_id": PORTFOLIO_ID,
        "audit_date": observation_date,
        "sla_status": sla_status,
        "sla_score": sla_score,
        "breaches": breaches,
    }

    sla = {
        "sla_audit_id": "P363S-" + stable_hash(sla_seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "audit_date": observation_date,
        "sla_status": sla_status,
        "overall_score": sla_score,
        "max_cycle_seconds": float(os.getenv("PHASE363_MAX_CYCLE_SECONDS", "120")),
        "min_success_rate_7d": float(os.getenv("PHASE363_MIN_SUCCESS_RATE_7D", "95")),
        "max_recovery_rate_7d": float(os.getenv("PHASE363_MAX_RECOVERY_RATE_7D", "25")),
        "max_incidents_7d": int(os.getenv("PHASE363_MAX_INCIDENTS_7D", "0")),
        "measured_cycle_seconds": total_seconds,
        "measured_success_rate_7d": rolling["success_rate_7d"],
        "measured_recovery_rate_7d": rolling["recovery_rate_7d"],
        "measured_incidents_7d": rolling["incident_count_7d"],
        "breach_reasons": breaches,
        "operator_action_required": sla_status == SLA_BREACH,
        "evidence_sha256": stable_hash(sla_seed),
    }

    rest_upsert(SLA_TABLE, [sla], "portfolio_id,audit_date")

    return obs, sla


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.6.3",
        "",
        "## Production Paper Autonomous Observability + SLA Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Observation Date: `{result['observation_date']}`",
        f"- Health Status: **{result['health_status']}**",
        f"- SLA Status: **{result['sla_status']}**",
        f"- SLA Score: **{result['sla_score']:.2f}%**",
        "",
        "### Reliability",
        "",
        f"- End-to-End Duration: **{result['end_to_end_duration_seconds']} sec**",
        f"- 7-Day Success Rate: **{result['success_rate_7d']:.2f}%**",
        f"- 7-Day Recovery Rate: **{result['recovery_rate_7d']:.2f}%**",
        f"- 7-Day Incident Count: **{result['incident_count_7d']}**",
        f"- Successful Streak: **{result['successful_streak_days']} day(s)**",
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
        default=os.getenv("PHASE363_APPROVER", "github-actions"),
    )
    args = parser.parse_args()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    health = run_upstream(args.approver)

    if not MASTER_JSON.exists() or not OP_JSON.exists():
        raise RuntimeError("Required master/autonomous evidence missing")

    master = read_json(MASTER_JSON)
    operation = read_json(OP_JSON)

    for payload_name, payload in (("master", master), ("operation", operation)):
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
            if payload.get(key) is not False:
                raise RuntimeError(
                    f"{payload_name} safety violation: {key}={payload.get(key)!r}"
                )
        if payload.get("fail_closed_policy") is not True:
            raise RuntimeError(f"{payload_name} fail_closed_policy must remain enabled")

    observation_date = str(health["health_date"])
    stage_seconds = stage_durations(master)
    total_seconds = cycle_duration(master)
    rolling = rolling_metrics(observation_date)

    sla_status, sla_score, sla_details, breaches = evaluate_sla(
        total_seconds,
        rolling,
    )

    obs, sla = persist(
        health,
        master,
        operation,
        stage_seconds,
        total_seconds,
        rolling,
        sla_status,
        sla_score,
        sla_details,
        breaches,
    )

    result = {
        "version": "3.6.3",
        "status": "PASS" if sla_status in {SLA_PASS, SLA_WARN} else "FAIL",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "observability_id": obs["observability_id"],
        "observation_date": str(obs["observation_date"]),
        "health_status": obs["health_status"],
        "sla_status": obs["sla_status"],
        "sla_score": float(obs["sla_score"]),
        "end_to_end_duration_seconds": (
            float(obs["end_to_end_duration_seconds"])
            if obs.get("end_to_end_duration_seconds") is not None
            else None
        ),
        "stage_duration_seconds": obs["stage_duration_seconds"],
        "success_rate_7d": float(obs["success_rate_7d"]),
        "recovery_rate_7d": float(obs["recovery_rate_7d"]),
        "incident_count_7d": int(obs["incident_count_7d"]),
        "successful_streak_days": int(obs["successful_streak_days"]),
        "breach_reasons": breaches,
        "cash": float(obs.get("cash") or 0),
        "market_value": float(obs.get("market_value") or 0),
        "nav": float(obs.get("nav") or 0),
        "open_positions": int(obs.get("open_positions") or 0),
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": obs["evidence_sha256"],
    }

    write_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if sla_status == SLA_BREACH:
        print("PHASE363 FAIL-CLOSED: SLA breach requires operator review.")
        return 1

    print(
        "PHASE363 PASS: observability + SLA evaluation complete. "
        f"sla={sla_status}, score={sla_score:.2f}, "
        f"success_7d={rolling['success_rate_7d']:.2f}%."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.6.3 GitHub Actions observability/SLA workflow"

$workflow = @'
name: GPT Quant Phase 3.6.3 - Production Paper Autonomous Observability SLA Engine

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
    - cron: "15 11 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase363-production-paper-autonomous-observability
  cancel-in-progress: false

jobs:
  autonomous-observability-sla:
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

      PHASE363_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE362_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE361_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE360_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE363_APPROVER: ${{ inputs.approver || 'github-actions' }}

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

      - name: Validate Phase 3.6.3 observability/SLA contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py
          test -f automation/v92/paper_trading_phase362_production_paper_autonomous_health_monitoring_incident_audit_engine.py
          test -f supabase/PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE.sql

          grep -q 'PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE' \
            automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py

          grep -q 'SLA_PASS' \
            automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py

          grep -q 'SLA_WARN' \
            automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py

          grep -q 'SLA_BREACH' \
            automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py

          echo "Phase 3.6.3 observability/SLA contract: PASS"

      - name: Execute Phase 3.6.3 observability/SLA
        shell: bash
        run: |
          set -euo pipefail

          APPROVER="${{ inputs.approver }}"
          if [ -z "${APPROVER}" ]; then
            APPROVER="github-actions"
          fi

          python automation/v92/paper_trading_phase363_production_paper_autonomous_observability_sla_engine.py \
            --approver "${APPROVER}"

      - name: Validate Phase 3.6.3 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase363_output/phase363_observability_sla.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase363_output/phase363_observability_sla.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.6.3", data
          assert data["sla_status"] in {
              "SLA_PASS",
              "SLA_WARN",
              "SLA_BREACH",
          }, data

          assert 0 <= data["sla_score"] <= 100, data
          assert 0 <= data["success_rate_7d"] <= 100, data
          assert 0 <= data["recovery_rate_7d"] <= 100, data
          assert data["incident_count_7d"] >= 0, data
          assert data["successful_streak_days"] >= 0, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          if data["sla_status"] == "SLA_BREACH":
              raise SystemExit("SLA breach requires operator review")

          assert data["status"] == "PASS", data

          print("Phase 3.6.3 output validation: PASS")
          PY

      - name: Upload Phase 3.6.3 observability evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase363-production-paper-observability-${{ github.run_id }}
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
    'PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE',
    'paper_observability_daily_v92',
    'paper_sla_audit_v92',
    'SLA_PASS',
    'SLA_WARN',
    'SLA_BREACH',
    'rolling_metrics',
    'evaluate_sla',
    '"synthetic_market_data": False',
    '"synthetic_signals": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.6.3 token missing: $needle"
    }
}

Write-Host "Phase 3.6.3 observability/SLA contract scan: PASS" -ForegroundColor Green

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
        Write-Host "No staged Phase 3.6.3 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Deploy Phase 3.6.3 autonomous observability SLA engine"
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

Write-Host "Observability metrics:" -ForegroundColor Cyan
Write-Host "  End-to-end master cycle duration"
Write-Host "  Per-stage duration"
Write-Host "  7-day success rate"
Write-Host "  7-day recovery rate"
Write-Host "  7-day incident count"
Write-Host "  Consecutive successful-operation streak"
Write-Host ""

Write-Host "SLA states:" -ForegroundColor Cyan
Write-Host "  SLA_PASS"
Write-Host "  SLA_WARN"
Write-Host "  SLA_BREACH -> fail-closed / operator review"
Write-Host ""

Write-Host "Default SLA thresholds:" -ForegroundColor Cyan
Write-Host "  Max cycle duration: 120 sec"
Write-Host "  Min 7-day success rate: 95%"
Write-Host "  Max 7-day recovery rate: 25%"
Write-Host "  Max 7-day incidents: 0"
Write-Host ""

Write-Host "Supabase SQL required before first Phase 3.6.3 run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE363_PRODUCTION_PAPER_AUTONOMOUS_OBSERVABILITY_SLA_ENGINE.sql"
Write-Host ""

Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 15 11 * * 1-5"
Write-Host "  11:15 UTC = 19:15 Taiwan time, weekdays"
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
Write-Host "  1) Run Phase 3.6.3 Supabase SQL once."
Write-Host "  2) Commit/Push Phase 3.6.3 files (or deploy with -AutoGit)."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.3 - Production Paper Autonomous Observability SLA Engine."
Write-Host "  4) Confirm SLA Status=SLA_PASS or SLA_WARN."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
