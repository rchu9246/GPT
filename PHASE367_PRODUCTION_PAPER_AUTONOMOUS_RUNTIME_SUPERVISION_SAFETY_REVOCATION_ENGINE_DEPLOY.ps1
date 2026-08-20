#requires -Version 5.1
<#
PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.7 — Production Paper Autonomous Runtime Supervision + Safety Revocation Engine

Purpose
-------
Continuously supervise an already ACTIVE Production Paper autonomous runtime.
If any critical operational/safety condition degrades, automatically revoke
autonomous paper activity and persist an auditable supervision/revocation state.

This phase NEVER enables broker/live-money capabilities.

Created/overwritten
-------------------
  automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py
  supabase/PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase367-production-paper-autonomous-runtime-supervision-safety-revocation-engine.yml
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Text" -ForegroundColor Red
    exit 1
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

Section "GPT Quant V9.2 — Phase 3.6.7 Runtime Supervision + Safety Revocation"

$repo = $null
try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = $null
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this package from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase366_production_paper_autonomous_operational_activation_control_engine.py",
    "automation/v92/paper_trading_phase3653_continuous_qualification_state_transition_recovery_fix.py",
    "automation/v92/paper_trading_phase360_production_paper_daily_master_orchestrator.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required dependency missing: $item"
    }
}

$sqlTarget = Join-Path $repo "supabase\PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE.sql"
$pyTarget  = Join-Path $repo "automation\v92\paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase367-production-paper-autonomous-runtime-supervision-safety-revocation-engine.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase367-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Writing Phase 3.6.7 runtime supervision engine"

$py = @'
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
FAIL_CLOSED_POLICY = True

SUPERVISION_CONTINUE = "CONTINUE_ACTIVE"
SUPERVISION_OBSERVE = "CONTINUE_WITH_OBSERVATION"
SUPERVISION_SUSPENDED = "SUSPENDED"
SUPERVISION_REVOKED = "REVOKED"
SUPERVISION_FAIL_CLOSED = "FAIL_CLOSED"

ACTIVE_STATES = {"ACTIVE", "ACTIVE_WITH_OBSERVATION"}
QUALIFIED_STATES = {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}

def env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""

def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None

def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

class Supabase:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def request(
        self,
        method: str,
        table: str,
        query: str = "",
        payload: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> Any:
        endpoint = f"{self.url}/rest/v1/{table}"
        if query:
            endpoint += "?" + query
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer

        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, headers=headers, data=data, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc

    def get(self, table: str, query: str) -> List[Dict[str, Any]]:
        value = self.request("GET", table, query=query)
        return value if isinstance(value, list) else []

    def upsert(self, table: str, payload: Dict[str, Any], on_conflict: str) -> None:
        query = "on_conflict=" + urllib.parse.quote(on_conflict, safe=",")
        self.request(
            "POST",
            table,
            query=query,
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )

def latest(sb: Supabase, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def supervise(
    activation: Dict[str, Any],
    qualification: Dict[str, Any],
    readiness: Dict[str, Any],
    health: Dict[str, Any],
    sla: Dict[str, Any],
    master: Dict[str, Any],
    incident: Optional[Dict[str, Any]],
    today: date,
) -> Dict[str, Any]:
    checks: Dict[str, Dict[str, Any]] = {}

    def add(name: str, passed: bool, value: Any, expected: Any, severity: str = "CRITICAL") -> None:
        checks[name] = {
            "passed": bool(passed),
            "value": value,
            "expected": expected,
            "severity": severity,
        }

    activation_state = str(activation.get("activation_state", "MISSING")).upper()
    activation_active = as_bool(activation.get("autonomous_paper_operations_active"), False)

    qualification_state = str(qualification.get("qualification_state", "MISSING")).upper()
    qualification_auth = as_bool(qualification.get("autonomous_paper_operations_authorized"), False)
    qualification_score = as_float(qualification.get("qualification_score"), 0.0)

    readiness_state = str(readiness.get("readiness_status", "MISSING")).upper()
    readiness_gate = as_bool(readiness.get("promotion_gate_open"), False)
    readiness_score = as_float(readiness.get("readiness_score"), 0.0)

    health_state = str(health.get("health_status", "MISSING")).upper()
    health_score = as_float(health.get("health_score"), 0.0)

    sla_state = str(sla.get("sla_status", "MISSING")).upper()
    sla_score = as_float(sla.get("sla_score"), 0.0)

    master_state = str(
        master.get("cycle_status")
        or master.get("master_status")
        or master.get("status")
        or "MISSING"
    ).upper()

    latest_dates = {
        "activation": parse_date(activation.get("activation_date")),
        "qualification": parse_date(qualification.get("qualification_date")),
        "readiness": parse_date(readiness.get("readiness_date")),
        "health": parse_date(health.get("health_date")),
        "sla": parse_date(sla.get("observation_date")),
        "master": parse_date(master.get("cycle_date")),
    }

    max_stale_days = int(os.getenv("PHASE367_MAX_CANONICAL_STALE_DAYS", "2"))

    incident_open = False
    incident_severity = "NONE"
    if incident:
        i_state = str(
            incident.get("incident_state")
            or incident.get("incident_status")
            or incident.get("status")
            or "UNKNOWN"
        ).upper()
        incident_severity = str(incident.get("severity") or "UNKNOWN").upper()
        incident_open = i_state not in {"CLOSED", "RESOLVED", "CLEAR", "NONE", "OBSERVED"}

    add("activation_state", activation_state in ACTIVE_STATES, activation_state, "ACTIVE or ACTIVE_WITH_OBSERVATION")
    add("activation_active", activation_active, activation_active, True)

    add("qualification_state", qualification_state in QUALIFIED_STATES, qualification_state, "QUALIFIED or QUALIFIED_WITH_OBSERVATION")
    add("qualification_authorization", qualification_auth, qualification_auth, True)
    add("qualification_score", qualification_score >= 75.0, qualification_score, ">= 75", "WARNING")

    add("readiness_state", readiness_state in {"READY", "READY_WITH_OBSERVATION"}, readiness_state, "READY or READY_WITH_OBSERVATION")
    add("readiness_gate", readiness_gate, readiness_gate, True)
    add("readiness_score", readiness_score >= 90.0, readiness_score, ">= 90", "WARNING")

    add("health_state", health_state in {"HEALTHY", "DEGRADED"}, health_state, "HEALTHY or DEGRADED")
    add("health_score", health_score >= 90.0, health_score, ">= 90", "WARNING")

    add("sla_state", sla_state in {"SLA_PASS", "SLA_WARN"}, sla_state, "SLA_PASS or SLA_WARN")
    add("sla_score", sla_score >= 75.0, sla_score, ">= 75", "WARNING")

    add("master_cycle", master_state in {"PASS", "SUCCESS", "COMPLETED", "HEALTHY"}, master_state, "PASS/SUCCESS/COMPLETED/HEALTHY")

    add(
        "blocking_incident_absent",
        not (incident_open and incident_severity in {"CRITICAL", "HIGH", "SEV0", "SEV1"}),
        {"open": incident_open, "severity": incident_severity},
        "no open high/critical incident",
    )

    for source, d in latest_dates.items():
        if d is None:
            add(f"freshness_{source}", False, None, f"<= {max_stale_days} stale day(s)")
        else:
            stale = (today - d).days
            add(f"freshness_{source}", stale <= max_stale_days, stale, f"<= {max_stale_days} stale day(s)")

    safety_rows = {
        "activation": activation,
        "qualification": qualification,
        "readiness": readiness,
        "health": health,
        "sla": sla,
        "master": master,
    }

    false_keys = (
        "synthetic_market_data",
        "synthetic_signals",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    )

    for source, row in safety_rows.items():
        for key in false_keys:
            if key in row:
                add(f"safety_{source}_{key}", row.get(key) is False, row.get(key), False)
        if "fail_closed_policy" in row:
            add(f"safety_{source}_fail_closed", row.get("fail_closed_policy") is True, row.get("fail_closed_policy"), True)

    critical_failures = [
        name for name, item in checks.items()
        if not item["passed"] and item["severity"] == "CRITICAL"
    ]
    warning_failures = [
        name for name, item in checks.items()
        if not item["passed"] and item["severity"] == "WARNING"
    ]

    total = len(checks)
    passed_count = sum(1 for item in checks.values() if item["passed"])
    supervision_score = round((passed_count / total) * 100.0, 4) if total else 0.0

    safety_failures = [x for x in critical_failures if x.startswith("safety_")]
    qualification_failures = [x for x in critical_failures if x.startswith("qualification_")]
    activation_failures = [x for x in critical_failures if x.startswith("activation_")]
    freshness_failures = [x for x in critical_failures if x.startswith("freshness_")]

    if safety_failures:
        state = SUPERVISION_FAIL_CLOSED
        continue_active = False
        revoked = True
    elif qualification_failures or activation_failures:
        state = SUPERVISION_REVOKED
        continue_active = False
        revoked = True
    elif critical_failures or freshness_failures:
        state = SUPERVISION_SUSPENDED
        continue_active = False
        revoked = True
    elif warning_failures or activation_state == "ACTIVE_WITH_OBSERVATION" or qualification_state == "QUALIFIED_WITH_OBSERVATION" or readiness_state == "READY_WITH_OBSERVATION" or health_state == "DEGRADED" or sla_state == "SLA_WARN":
        state = SUPERVISION_OBSERVE
        continue_active = True
        revoked = False
    else:
        state = SUPERVISION_CONTINUE
        continue_active = True
        revoked = False

    return {
        "checks": checks,
        "critical_failures": critical_failures,
        "warning_failures": warning_failures,
        "supervision_state": state,
        "supervision_score": supervision_score,
        "continue_active": continue_active,
        "revoked": revoked,
        "activation_state": activation_state,
        "qualification_state": qualification_state,
        "qualification_score": qualification_score,
        "readiness_state": readiness_state,
        "readiness_score": readiness_score,
        "health_state": health_state,
        "health_score": health_score,
        "sla_state": sla_state,
        "sla_score": sla_score,
        "master_state": master_state,
        "incident_open": incident_open,
        "incident_severity": incident_severity,
        "latest_dates": {k: (v.isoformat() if v else None) for k, v in latest_dates.items()},
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--supervision-date", default=str(date.today()))
    args = parser.parse_args()

    supervision_date = date.fromisoformat(args.supervision_date)

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = Supabase(url, key)

    activation = latest(sb, "paper_autonomous_activation_state_v92", args.portfolio_id, "activation_date")
    qualification = latest(sb, "paper_continuous_qualification_v92", args.portfolio_id, "qualification_date")
    readiness = latest(sb, "paper_operational_readiness_v92", args.portfolio_id, "readiness_date")
    health = latest(sb, "paper_system_health_v92", args.portfolio_id, "health_date")
    sla = latest(sb, "paper_observability_daily_v92", args.portfolio_id, "observation_date")
    master = latest(sb, "paper_master_cycles_v92", args.portfolio_id, "cycle_date")
    incident = latest(sb, "paper_incident_audit_v92", args.portfolio_id, "incident_date")

    missing = []
    if activation is None: missing.append("activation")
    if qualification is None: missing.append("qualification")
    if readiness is None: missing.append("readiness")
    if health is None: missing.append("health")
    if sla is None: missing.append("sla")
    if master is None: missing.append("master")

    if missing:
        raise RuntimeError("Missing canonical supervision evidence: " + ", ".join(missing))

    decision = supervise(
        activation,
        qualification,
        readiness,
        health,
        sla,
        master,
        incident,
        supervision_date,
    )

    reasons: List[str] = []
    reasons.extend("CRITICAL_" + x.upper() for x in decision["critical_failures"])
    reasons.extend("OBSERVE_" + x.upper() for x in decision["warning_failures"])

    if not reasons:
        reasons.append("ALL_RUNTIME_SUPERVISION_GATES_PASS")

    evidence = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "supervision_date": args.supervision_date,
        "decision": decision,
        "reasons": reasons,
        "safety": {
            "paper_only": True,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
        },
    }
    evidence_sha = stable_hash(evidence)

    state_payload = {
        "supervision_date": args.supervision_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "supervision_state": decision["supervision_state"],
        "supervision_score": decision["supervision_score"],
        "autonomous_paper_operations_continued": decision["continue_active"],
        "safety_revocation_triggered": decision["revoked"],

        "activation_state": decision["activation_state"],
        "qualification_state": decision["qualification_state"],
        "qualification_score": decision["qualification_score"],
        "readiness_state": decision["readiness_state"],
        "readiness_score": decision["readiness_score"],
        "health_state": decision["health_state"],
        "health_score": decision["health_score"],
        "sla_state": decision["sla_state"],
        "sla_score": decision["sla_score"],
        "master_cycle_state": decision["master_state"],
        "open_incident": decision["incident_open"],
        "incident_severity": decision["incident_severity"],

        "critical_failures": decision["critical_failures"],
        "warning_failures": decision["warning_failures"],
        "reason_codes": reasons,
        "canonical_dates": decision["latest_dates"],

        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,

        "evidence_sha256": evidence_sha,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    sb.upsert(
        "paper_runtime_supervision_state_v92",
        state_payload,
        "portfolio_id,supervision_date",
    )

    if decision["revoked"]:
        revoke_payload = dict(activation)
        revoke_payload["activation_state"] = (
            "FAIL_CLOSED"
            if decision["supervision_state"] == SUPERVISION_FAIL_CLOSED
            else "BLOCKED"
        )
        revoke_payload["autonomous_paper_operations_active"] = False
        revoke_payload["critical_failures"] = decision["critical_failures"]
        revoke_payload["warning_failures"] = decision["warning_failures"]
        revoke_payload["reason_codes"] = reasons
        revoke_payload["evidence_sha256"] = evidence_sha
        revoke_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

        # keep only fields accepted by the activation table
        allowed = {
            "activation_date",
            "portfolio_id",
            "strategy_version",
            "contract",
            "activation_state",
            "activation_score",
            "autonomous_paper_operations_active",
            "qualification_state",
            "qualification_score",
            "readiness_state",
            "readiness_score",
            "health_state",
            "health_score",
            "sla_state",
            "sla_score",
            "master_cycle_state",
            "open_incident",
            "incident_severity",
            "critical_failures",
            "warning_failures",
            "reason_codes",
            "paper_only",
            "broker_api_used",
            "broker_credentials_used",
            "broker_order_submission_enabled",
            "real_money_trading_enabled",
            "live_money_release_authorized",
            "fail_closed_policy",
            "evidence_sha256",
            "updated_at",
        }
        revoke_payload = {k: v for k, v in revoke_payload.items() if k in allowed}

        sb.upsert(
            "paper_autonomous_activation_state_v92",
            revoke_payload,
            "portfolio_id,activation_date",
        )

    audit_payload = {
        "supervision_date": args.supervision_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "supervision_state": decision["supervision_state"],
        "supervision_score": decision["supervision_score"],
        "autonomous_paper_operations_continued": decision["continue_active"],
        "safety_revocation_triggered": decision["revoked"],
        "activation_state": decision["activation_state"],
        "qualification_state": decision["qualification_state"],
        "reason_codes": reasons,
        "evidence_sha256": evidence_sha,
        "paper_only": True,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    sb.request(
        "POST",
        "paper_runtime_supervision_audit_v92",
        payload=audit_payload,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.7")
    print()
    print("## Production Paper Autonomous Runtime Supervision + Safety Revocation Engine")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Supervision Date: `{args.supervision_date}`")
    print(f"- Activation State: **{decision['activation_state']}**")
    print(f"- Qualification State: **{decision['qualification_state']}**")
    print(f"- Supervision State: **{decision['supervision_state']}**")
    print(f"- Supervision Score: **{decision['supervision_score']:.4f}**")
    print(f"- Autonomous Paper Operations Continued: **{'YES' if decision['continue_active'] else 'NO'}**")
    print(f"- Safety Revocation Triggered: **{'YES' if decision['revoked'] else 'NO'}**")
    print()
    print("## Canonical Runtime Inputs")
    print()
    print(f"- Operational Readiness: `{decision['readiness_state']}` / {decision['readiness_score']:.4f}")
    print(f"- Health: `{decision['health_state']}` / {decision['health_score']:.4f}")
    print(f"- SLA: `{decision['sla_state']}` / {decision['sla_score']:.4f}")
    print(f"- Master Cycle: `{decision['master_state']}`")
    print(f"- Open Incident: **{'YES' if decision['incident_open'] else 'NO'}**")
    print(f"- Incident Severity: `{decision['incident_severity']}`")
    print()
    print("## Supervision Reasons")
    print()
    for reason in reasons:
        print(f"- `{reason}`")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase367")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "runtime_supervision_evidence.json"), "w", encoding="utf-8") as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE367_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.6.7 Supabase supervision schema"

$sql = @'
begin;

create table if not exists public.paper_runtime_supervision_state_v92 (
    id bigint generated by default as identity primary key,
    supervision_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE',

    supervision_state text not null,
    supervision_score numeric not null default 0,
    autonomous_paper_operations_continued boolean not null default false,
    safety_revocation_triggered boolean not null default false,

    activation_state text not null default 'UNKNOWN',
    qualification_state text not null default 'UNKNOWN',
    qualification_score numeric not null default 0,
    readiness_state text not null default 'UNKNOWN',
    readiness_score numeric not null default 0,
    health_state text not null default 'UNKNOWN',
    health_score numeric not null default 0,
    sla_state text not null default 'UNKNOWN',
    sla_score numeric not null default 0,
    master_cycle_state text not null default 'UNKNOWN',

    open_incident boolean not null default false,
    incident_severity text not null default 'NONE',

    critical_failures jsonb not null default '[]'::jsonb,
    warning_failures jsonb not null default '[]'::jsonb,
    reason_codes jsonb not null default '[]'::jsonb,
    canonical_dates jsonb not null default '{}'::jsonb,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint ck_phase367_supervision_state
        check (supervision_state in (
            'CONTINUE_ACTIVE',
            'CONTINUE_WITH_OBSERVATION',
            'SUSPENDED',
            'REVOKED',
            'FAIL_CLOSED'
        )),
    constraint ck_phase367_paper_only
        check (paper_only = true),
    constraint ck_phase367_no_broker_api
        check (broker_api_used = false),
    constraint ck_phase367_no_broker_credentials
        check (broker_credentials_used = false),
    constraint ck_phase367_no_broker_submission
        check (broker_order_submission_enabled = false),
    constraint ck_phase367_no_real_money
        check (real_money_trading_enabled = false),
    constraint ck_phase367_no_live_release
        check (live_money_release_authorized = false),
    constraint ck_phase367_fail_closed
        check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_runtime_supervision_state_v92_portfolio_date
    on public.paper_runtime_supervision_state_v92 (portfolio_id, supervision_date);

create index if not exists ix_paper_runtime_supervision_state_v92_state
    on public.paper_runtime_supervision_state_v92 (supervision_state, supervision_date desc);

create table if not exists public.paper_runtime_supervision_audit_v92 (
    id bigint generated by default as identity primary key,
    supervision_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',

    supervision_state text not null,
    supervision_score numeric not null default 0,
    autonomous_paper_operations_continued boolean not null default false,
    safety_revocation_triggered boolean not null default false,

    activation_state text not null default 'UNKNOWN',
    qualification_state text not null default 'UNKNOWN',

    reason_codes jsonb not null default '[]'::jsonb,
    evidence_sha256 text not null,

    paper_only boolean not null default true,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    created_at timestamptz not null default now(),

    constraint ck_phase367_audit_paper_only
        check (paper_only = true),
    constraint ck_phase367_audit_no_broker
        check (broker_order_submission_enabled = false),
    constraint ck_phase367_audit_no_real_money
        check (real_money_trading_enabled = false),
    constraint ck_phase367_audit_no_live_release
        check (live_money_release_authorized = false),
    constraint ck_phase367_audit_fail_closed
        check (fail_closed_policy = true)
);

create index if not exists ix_paper_runtime_supervision_audit_v92_portfolio_created
    on public.paper_runtime_supervision_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_runtime_supervision_state_v92 enable row level security;
alter table public.paper_runtime_supervision_audit_v92 enable row level security;

comment on table public.paper_runtime_supervision_state_v92 is
'GPT Quant V9.2 Phase 3.6.7 active Production Paper runtime supervision state with automatic safety revocation.';

comment on table public.paper_runtime_supervision_audit_v92 is
'GPT Quant V9.2 Phase 3.6.7 immutable-style runtime supervision and revocation audit.';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.7 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.6.7 - Production Paper Autonomous Runtime Supervision Safety Revocation Engine

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

  schedule:
    # 12:30 UTC = 20:30 Asia/Taipei
    - cron: "30 12 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase367-production-paper-runtime-supervision
  cancel-in-progress: false

jobs:
  production-paper-runtime-supervision:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE367_MAX_CANONICAL_STALE_DAYS: "2"

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Compile Phase 3.6.7
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py

      - name: Validate Phase 3.6.7 safety contract
        shell: bash
        run: |
          set -euo pipefail

          grep -q 'PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE' \
            automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py

          grep -q 'SUPERVISION_FAIL_CLOSED' \
            automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py

          grep -q '"live_money_release_authorized": False' \
            automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py

          echo "Phase 3.6.7 safety contract: PASS"

      - name: Execute Phase 3.6.7 runtime supervision
        shell: bash
        run: |
          mkdir -p artifacts/phase367

          python automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase367/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase367/summary.md ]; then
            cat artifacts/phase367/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase367-runtime-supervision-evidence
          path: artifacts/phase367/
          if-no-files-found: warn
          retention-days: 30
'@

Write-Utf8NoBom $ymlTarget $yml
Write-Host "Wrote: $ymlTarget" -ForegroundColor Green

Section "Static validation"

$pythonExe = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} else {
    Fail "Python not found in PATH."
}

if ($pythonExe -eq "py") {
    & py -3 -m py_compile $pyTarget
} else {
    & python -m py_compile $pyTarget
}

if ($LASTEXITCODE -ne 0) {
    Fail "Phase 3.6.7 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $sqlTarget -Raw) + "`n" +
            (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE",
    "paper_runtime_supervision_state_v92",
    "paper_runtime_supervision_audit_v92",
    "CONTINUE_ACTIVE",
    "CONTINUE_WITH_OBSERVATION",
    "SUSPENDED",
    "REVOKED",
    "FAIL_CLOSED",
    "paper_autonomous_activation_state_v92",
    "paper_continuous_qualification_v92",
    "paper_system_health_v92",
    "paper_observability_daily_v92"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.6.7 required contract token missing: $token"
    }
}

foreach ($forbidden in @(
    '"broker_api_used": True',
    '"broker_credentials_used": True',
    '"broker_order_submission_enabled": True',
    '"real_money_trading_enabled": True',
    '"live_money_release_authorized": True'
)) {
    if ($combined.Contains($forbidden)) {
        Fail "Forbidden live capability detected: $forbidden"
    }
}

Write-Host "Runtime supervision contract scan: PASS" -ForegroundColor Green
Write-Host "Automatic safety revocation contract scan: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary scan: PASS" -ForegroundColor Green

Section "Git status"
& git status --short

Section "DEPLOY COMPLETE"

Write-Host "Generated:" -ForegroundColor Green
Write-Host "  automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py"
Write-Host "  supabase/PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase367-production-paper-autonomous-runtime-supervision-safety-revocation-engine.yml"
Write-Host ""
Write-Host "Supervision states:" -ForegroundColor Cyan
Write-Host "  CONTINUE_ACTIVE"
Write-Host "  CONTINUE_WITH_OBSERVATION"
Write-Host "  SUSPENDED"
Write-Host "  REVOKED"
Write-Host "  FAIL_CLOSED"
Write-Host ""
Write-Host "Expected healthy result:" -ForegroundColor Cyan
Write-Host "  Activation State: ACTIVE"
Write-Host "  Qualification State: QUALIFIED"
Write-Host "  Supervision State: CONTINUE_ACTIVE"
Write-Host "  Supervision Score: 100"
Write-Host "  Autonomous Paper Operations Continued: YES"
Write-Host "  Safety Revocation Triggered: NO"
Write-Host ""
Write-Host "Safety:" -ForegroundColor Yellow
Write-Host "  PAPER ONLY"
Write-Host "  Broker API: NO"
Write-Host "  Broker credentials: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release: NO"
Write-Host "  Fail-closed: ENABLED"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run supabase/PHASE367_PRODUCTION_PAPER_AUTONOMOUS_RUNTIME_SUPERVISION_SAFETY_REVOCATION_ENGINE.sql once."
Write-Host "  2) Commit and Push generated files."
Write-Host "  3) Run GitHub Action: GPT Quant Phase 3.6.7 - Production Paper Autonomous Runtime Supervision Safety Revocation Engine."
Write-Host "  4) Confirm Supervision State=CONTINUE_ACTIVE or CONTINUE_WITH_OBSERVATION."
Write-Host "  5) After PASS, proceed to Phase 3.6.8 Daily Autonomous Operations Controller."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
