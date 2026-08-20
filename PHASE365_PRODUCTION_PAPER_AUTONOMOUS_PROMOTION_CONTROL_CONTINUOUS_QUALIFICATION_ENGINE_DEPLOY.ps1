#requires -Version 5.1
<#
PHASE365_PRODUCTION_PAPER_AUTONOMOUS_PROMOTION_CONTROL_CONTINUOUS_QUALIFICATION_ENGINE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.5 - Production Paper Autonomous Promotion Control + Continuous Qualification Engine

Single overwrite deployment package.

Creates:
  automation/v92/paper_trading_phase365_autonomous_promotion_control_continuous_qualification_engine.py
  supabase/PHASE365_PRODUCTION_PAPER_AUTONOMOUS_PROMOTION_CONTROL_CONTINUOUS_QUALIFICATION_ENGINE.sql
  .github/workflows/gpt-quant-v92-paper-trading-phase365-autonomous-promotion-control-continuous-qualification-engine.yml

Safety:
  PAPER ONLY
  NO BROKER
  NO BROKER CREDENTIALS
  NO BROKER ORDER SUBMISSION
  NO REAL MONEY
  NO LIVE-MONEY RELEASE
  FAIL-CLOSED
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

$Repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $Repo ".git"))) {
    throw "Run this deploy file from the GPT repository root (folder containing .git). Current: $Repo"
}

Write-Section "GPT Quant V9.2 - Phase 3.6.5"
Write-Host "Production Paper Autonomous Promotion Control + Continuous Qualification Engine"
Write-Host "Repository: $Repo"

$PyPath  = Join-Path $Repo "automation\v92\paper_trading_phase365_autonomous_promotion_control_continuous_qualification_engine.py"
$SqlPath = Join-Path $Repo "supabase\PHASE365_PRODUCTION_PAPER_AUTONOMOUS_PROMOTION_CONTROL_CONTINUOUS_QUALIFICATION_ENGINE.sql"
$YmlPath = Join-Path $Repo ".github\workflows\gpt-quant-v92-paper-trading-phase365-autonomous-promotion-control-continuous-qualification-engine.yml"

$Python = @'
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE365_PRODUCTION_PAPER_AUTONOMOUS_PROMOTION_CONTROL_CONTINUOUS_QUALIFICATION_ENGINE"
STRATEGY_DEFAULT = "V9.1"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
FAIL_CLOSED_POLICY = True

QUALIFIED_STATES = {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}
BLOCKED_STATES = {"NOT_QUALIFIED", "REVOKED", "FAIL_CLOSED"}

@dataclass
class Supabase:
    url: str
    key: str

    def request(
        self,
        method: str,
        table: str,
        query: str = "",
        payload: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> Any:
        endpoint = self.url.rstrip("/") + "/rest/v1/" + table
        if query:
            endpoint += "?" + query
        headers = {
            "apikey": self.key,
            "Authorization": "Bearer " + self.key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8")
                return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase HTTP {e.code} on {table}: {body}") from e

    def select(self, table: str, query: str) -> List[Dict[str, Any]]:
        data = self.request("GET", table, query=query)
        return data if isinstance(data, list) else []

    def upsert(self, table: str, payload: Dict[str, Any], on_conflict: str) -> None:
        query = "on_conflict=" + urllib.parse.quote(on_conflict, safe=",")
        self.request(
            "POST",
            table,
            query=query,
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )

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

def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def first_value(row: Dict[str, Any], names: Tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default

def select_latest(
    sb: Supabase,
    table: str,
    portfolio_id: str,
    order_candidates: Tuple[str, ...],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    last_error: Optional[Exception] = None
    filters = [
        "portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe=""),
        "",
    ]
    for filt in filters:
        for col in order_candidates:
            q = "select=*"
            if filt:
                q += "&" + filt
            q += f"&order={col}.desc&limit=1"
            try:
                rows = sb.select(table, q)
                if rows:
                    return rows[0], None
            except Exception as exc:
                last_error = exc
    return None, str(last_error) if last_error else None

def normalized_readiness(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {
            "state": "MISSING",
            "score": 0.0,
            "promotion_gate_open": False,
            "source_date": None,
        }
    return {
        "state": str(first_value(row, ("readiness_status", "readiness_state", "status"), "UNKNOWN")).upper(),
        "score": as_float(first_value(row, ("readiness_score", "score"), 0.0)),
        "promotion_gate_open": as_bool(first_value(row, ("promotion_gate_open", "gate_open", "authorized"), False)),
        "source_date": first_value(row, ("readiness_date", "cycle_date", "as_of_date", "created_at"), None),
    }

def normalized_health(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {"state": "MISSING", "score": 0.0}
    return {
        "state": str(first_value(row, ("health_status", "health_state", "status"), "UNKNOWN")).upper(),
        "score": as_float(first_value(row, ("health_score", "score"), 0.0)),
    }

def normalized_sla(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {"state": "MISSING", "score": 0.0}
    return {
        "state": str(first_value(row, ("sla_status", "sla_state", "status"), "UNKNOWN")).upper(),
        "score": as_float(first_value(row, ("sla_score", "score"), 0.0)),
    }

def normalized_master(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {"state": "MISSING"}
    return {
        "state": str(first_value(row, ("cycle_status", "master_status", "status"), "UNKNOWN")).upper()
    }

def normalized_incident(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {"state": "NONE", "severity": "NONE", "open": False}
    state = str(first_value(row, ("incident_status", "status", "state"), "UNKNOWN")).upper()
    severity = str(first_value(row, ("severity", "incident_severity"), "UNKNOWN")).upper()
    closed = state in {"CLOSED", "RESOLVED", "CLEAR", "NONE"}
    return {"state": state, "severity": severity, "open": not closed}

def sha256_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def qualification_decision(
    readiness: Dict[str, Any],
    health: Dict[str, Any],
    sla: Dict[str, Any],
    master: Dict[str, Any],
    incident: Dict[str, Any],
    previous_state: str,
) -> Tuple[str, bool, float, List[str]]:
    reasons: List[str] = []
    score_parts: List[float] = []

    r_state = readiness["state"]
    if r_state not in {"READY", "READY_WITH_OBSERVATION"}:
        reasons.append(f"READINESS_{r_state}")
    if not readiness["promotion_gate_open"]:
        reasons.append("READINESS_PROMOTION_GATE_CLOSED")
    score_parts.append(max(0.0, min(100.0, readiness["score"])))

    h_state = health["state"]
    if h_state in {"FAIL", "FAILED", "CRITICAL", "UNHEALTHY", "FAIL_CLOSED", "MISSING"}:
        reasons.append(f"HEALTH_{h_state}")
    score_parts.append(max(0.0, min(100.0, health["score"])))

    s_state = sla["state"]
    if s_state in {"FAIL", "FAILED", "BREACH", "CRITICAL", "FAIL_CLOSED", "MISSING"}:
        reasons.append(f"SLA_{s_state}")
    score_parts.append(max(0.0, min(100.0, sla["score"])))

    m_state = master["state"]
    if m_state not in {"PASS", "SUCCESS", "COMPLETED", "HEALTHY"}:
        reasons.append(f"MASTER_{m_state}")

    if incident["open"] and incident["severity"] in {"CRITICAL", "HIGH", "SEV0", "SEV1"}:
        reasons.append(f"OPEN_{incident['severity']}_INCIDENT")

    missing_hard = any(x.endswith("_MISSING") or x == "MASTER_MISSING" for x in reasons)
    critical = any(
        x.startswith("READINESS_FAIL_CLOSED")
        or x.startswith("HEALTH_FAIL_CLOSED")
        or x.startswith("SLA_FAIL_CLOSED")
        or x.startswith("OPEN_CRITICAL")
        or x.startswith("OPEN_SEV0")
        for x in reasons
    )

    qualification_score = round(sum(score_parts) / len(score_parts), 4) if score_parts else 0.0

    if critical or missing_hard:
        return "FAIL_CLOSED", False, qualification_score, reasons

    if reasons:
        if previous_state in QUALIFIED_STATES:
            return "REVOKED", False, qualification_score, reasons
        return "NOT_QUALIFIED", False, qualification_score, reasons

    observation = (
        r_state == "READY_WITH_OBSERVATION"
        or h_state in {"WARN", "WARNING", "OBSERVATION", "DEGRADED"}
        or s_state in {"WARN", "WARNING", "OBSERVATION", "DEGRADED"}
        or incident["open"]
    )
    if observation:
        return "QUALIFIED_WITH_OBSERVATION", True, qualification_score, ["VALID_WITH_OBSERVATION"]
    return "QUALIFIED", True, qualification_score, ["ALL_CONTINUOUS_QUALIFICATION_GATES_PASS"]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    ap.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    ap.add_argument("--qualification-date", default=str(date.today()))
    args = ap.parse_args()

    sb_url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    sb_key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )
    if not sb_url or not sb_key:
        raise RuntimeError("Missing SUPABASE_URL and Supabase key environment variables.")

    sb = Supabase(sb_url, sb_key)

    readiness_row, readiness_err = select_latest(
        sb, "paper_operational_readiness_v92", args.portfolio_id,
        ("readiness_date", "cycle_date", "created_at", "updated_at")
    )
    health_row, health_err = select_latest(
        sb, "paper_health_monitoring_v92", args.portfolio_id,
        ("health_date", "cycle_date", "created_at", "updated_at")
    )
    sla_row, sla_err = select_latest(
        sb, "paper_observability_sla_v92", args.portfolio_id,
        ("sla_date", "cycle_date", "created_at", "updated_at")
    )
    master_row, master_err = select_latest(
        sb, "paper_master_cycles_v92", args.portfolio_id,
        ("cycle_date", "created_at", "updated_at")
    )
    incident_row, incident_err = select_latest(
        sb, "paper_incident_audit_v92", args.portfolio_id,
        ("incident_date", "cycle_date", "created_at", "updated_at")
    )

    prev_rows = sb.select(
        "paper_continuous_qualification_v92",
        "select=qualification_state&portfolio_id=eq."
        + urllib.parse.quote(args.portfolio_id, safe="")
        + "&order=qualification_date.desc&limit=1",
    )
    previous_state = str(prev_rows[0].get("qualification_state", "NONE")).upper() if prev_rows else "NONE"

    readiness = normalized_readiness(readiness_row)
    health = normalized_health(health_row)
    sla = normalized_sla(sla_row)
    master = normalized_master(master_row)
    incident = normalized_incident(incident_row)

    source_errors = {
        "readiness": readiness_err,
        "health": health_err,
        "sla": sla_err,
        "master": master_err,
        "incident": incident_err,
    }

    state, authorized, score, reasons = qualification_decision(
        readiness, health, sla, master, incident, previous_state
    )

    if any(source_errors.values()):
        state = "FAIL_CLOSED"
        authorized = False
        reasons = ["CANONICAL_SOURCE_READ_ERROR"] + reasons

    evidence = {
        "contract": CONTRACT,
        "strategy_version": args.strategy_version,
        "portfolio_id": args.portfolio_id,
        "qualification_date": args.qualification_date,
        "readiness": readiness,
        "health": health,
        "sla": sla,
        "master": master,
        "incident": incident,
        "previous_state": previous_state,
        "qualification_state": state,
        "autonomous_paper_operations_authorized": authorized,
        "qualification_score": score,
        "reasons": reasons,
        "source_errors": source_errors,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_api_used": BROKER_API_USED,
            "broker_credentials_used": BROKER_CREDENTIALS_USED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "live_money_release_authorized": LIVE_MONEY_RELEASE_AUTHORIZED,
            "fail_closed_policy": FAIL_CLOSED_POLICY,
        },
    }
    evidence_sha = sha256_json(evidence)

    payload = {
        "qualification_date": args.qualification_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "previous_qualification_state": previous_state,
        "qualification_state": state,
        "qualification_score": score,
        "autonomous_paper_operations_authorized": authorized,
        "readiness_state": readiness["state"],
        "readiness_score": readiness["score"],
        "health_state": health["state"],
        "health_score": health["score"],
        "sla_state": sla["state"],
        "sla_score": sla["score"],
        "master_cycle_state": master["state"],
        "open_incident": incident["open"],
        "incident_severity": incident["severity"],
        "reason_codes": reasons,
        "evidence_sha256": evidence_sha,
        "paper_only": PAPER_ONLY,
        "broker_api_used": BROKER_API_USED,
        "broker_credentials_used": BROKER_CREDENTIALS_USED,
        "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
        "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
        "live_money_release_authorized": LIVE_MONEY_RELEASE_AUTHORIZED,
        "fail_closed_policy": FAIL_CLOSED_POLICY,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    sb.upsert(
        "paper_continuous_qualification_v92",
        payload,
        "portfolio_id,qualification_date",
    )

    transition = previous_state != state
    if transition:
        audit = {
            "qualification_date": args.qualification_date,
            "portfolio_id": args.portfolio_id,
            "strategy_version": args.strategy_version,
            "from_state": previous_state,
            "to_state": state,
            "autonomous_paper_operations_authorized": authorized,
            "reason_codes": reasons,
            "evidence_sha256": evidence_sha,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        sb.request("POST", "paper_promotion_control_audit_v92", payload=audit, prefer="return=minimal")

    print(f"# GPT Quant V9.2 Paper Trading - Phase 3.6.5")
    print()
    print("## Production Paper Autonomous Promotion Control + Continuous Qualification Engine")
    print()
    print(f"- Strategy: `{args.strategy_version}`")
    print(f"- Trading Mode: `SHADOW_ONLY_NO_BROKER`")
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Qualification Date: `{args.qualification_date}`")
    print(f"- Qualification State: **{state}**")
    print(f"- Qualification Score: **{score:.4f}**")
    print(f"- Previous State: `{previous_state}`")
    print(f"- State Transition: **{'YES' if transition else 'NO'}**")
    print(f"- Autonomous Paper Operations Authorized: **{'YES' if authorized else 'NO'}**")
    print()
    print("## Canonical Qualification Inputs")
    print()
    print(f"- Operational Readiness: `{readiness['state']}` / {readiness['score']:.4f}")
    print(f"- Phase 3.6.4 Promotion Gate Open: **{'YES' if readiness['promotion_gate_open'] else 'NO'}**")
    print(f"- Health: `{health['state']}` / {health['score']:.4f}")
    print(f"- SLA: `{sla['state']}` / {sla['score']:.4f}")
    print(f"- Master Cycle: `{master['state']}`")
    print(f"- Open Incident: **{'YES' if incident['open'] else 'NO'}**")
    print(f"- Incident Severity: `{incident['severity']}`")
    print()
    print("## Qualification Reasons")
    print()
    for reason in reasons:
        print(f"- `{reason}`")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Synthetic market data: **DISABLED**")
    print("- Synthetic signals: **DISABLED**")
    print("- Fake prices: **DISABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    # NOT_QUALIFIED/REVOKED are valid governance outcomes, not workflow failures.
    # FAIL_CLOSED is also persisted and reported; return success so audit evidence is retained.
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE365_FATAL: {exc}", file=sys.stderr)
        raise
'@

$Sql = @'
begin;

create table if not exists public.paper_continuous_qualification_v92 (
    id bigint generated by default as identity primary key,
    qualification_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    contract text not null default 'PHASE365_PRODUCTION_PAPER_AUTONOMOUS_PROMOTION_CONTROL_CONTINUOUS_QUALIFICATION_ENGINE',

    previous_qualification_state text not null default 'NONE',
    qualification_state text not null,
    qualification_score numeric not null default 0,
    autonomous_paper_operations_authorized boolean not null default false,

    readiness_state text not null default 'UNKNOWN',
    readiness_score numeric not null default 0,
    health_state text not null default 'UNKNOWN',
    health_score numeric not null default 0,
    sla_state text not null default 'UNKNOWN',
    sla_score numeric not null default 0,
    master_cycle_state text not null default 'UNKNOWN',

    open_incident boolean not null default false,
    incident_severity text not null default 'NONE',
    reason_codes jsonb not null default '[]'::jsonb,

    evidence_sha256 text not null,

    paper_only boolean not null default true,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint ck_phase365_qualification_state
        check (qualification_state in (
            'QUALIFIED',
            'QUALIFIED_WITH_OBSERVATION',
            'NOT_QUALIFIED',
            'REVOKED',
            'FAIL_CLOSED'
        )),
    constraint ck_phase365_paper_only check (paper_only = true),
    constraint ck_phase365_no_broker_api check (broker_api_used = false),
    constraint ck_phase365_no_broker_credentials check (broker_credentials_used = false),
    constraint ck_phase365_no_broker_submission check (broker_order_submission_enabled = false),
    constraint ck_phase365_no_real_money check (real_money_trading_enabled = false),
    constraint ck_phase365_no_live_release check (live_money_release_authorized = false),
    constraint ck_phase365_fail_closed check (fail_closed_policy = true)
);

create unique index if not exists uq_paper_continuous_qualification_v92_portfolio_date
    on public.paper_continuous_qualification_v92 (portfolio_id, qualification_date);

create index if not exists ix_paper_continuous_qualification_v92_state
    on public.paper_continuous_qualification_v92 (qualification_state, qualification_date desc);

create table if not exists public.paper_promotion_control_audit_v92 (
    id bigint generated by default as identity primary key,
    qualification_date date not null,
    portfolio_id text not null,
    strategy_version text not null default 'V9.1',
    from_state text not null,
    to_state text not null,
    autonomous_paper_operations_authorized boolean not null default false,
    reason_codes jsonb not null default '[]'::jsonb,
    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create index if not exists ix_paper_promotion_control_audit_v92_portfolio_created
    on public.paper_promotion_control_audit_v92 (portfolio_id, created_at desc);

alter table public.paper_continuous_qualification_v92 enable row level security;
alter table public.paper_promotion_control_audit_v92 enable row level security;

comment on table public.paper_continuous_qualification_v92 is
'GPT Quant V9.2 Phase 3.6.5 persistent continuous qualification state. Paper-only; broker and real-money capabilities hard-disabled.';

comment on table public.paper_promotion_control_audit_v92 is
'GPT Quant V9.2 Phase 3.6.5 immutable-style promotion/revocation transition audit for autonomous paper operations.';

commit;
'@

$Yaml = @'
name: GPT Quant Phase 3.6.5 - Production Paper Autonomous Promotion Control Continuous Qualification Engine

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
    # 12:00 UTC = 20:00 Asia/Taipei
    - cron: "0 12 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase365-production-paper-continuous-qualification
  cancel-in-progress: false

jobs:
  autonomous-promotion-control-continuous-qualification:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Compile Phase 3.6.5
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase365_autonomous_promotion_control_continuous_qualification_engine.py

      - name: Run Phase 3.6.5
        shell: bash
        run: |
          mkdir -p artifacts/phase365
          python automation/v92/paper_trading_phase365_autonomous_promotion_control_continuous_qualification_engine.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase365/summary.md

      - name: Publish job summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase365/summary.md ]; then
            cat artifacts/phase365/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload Phase 3.6.5 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase365-continuous-qualification-evidence
          path: artifacts/phase365/
          if-no-files-found: warn
          retention-days: 30
'@

Write-Utf8NoBom $PyPath $Python
Write-Utf8NoBom $SqlPath $Sql
Write-Utf8NoBom $YmlPath $Yaml

Write-Section "Validation"

$PythonExe = $null
foreach ($candidate in @("python", "py")) {
    try {
        if ($candidate -eq "py") {
            & py -3 --version *> $null
            if ($LASTEXITCODE -eq 0) { $PythonExe = "py"; break }
        } else {
            & python --version *> $null
            if ($LASTEXITCODE -eq 0) { $PythonExe = "python"; break }
        }
    } catch {}
}

if (-not $PythonExe) {
    throw "Python not found. Install Python or make python/py available in PATH."
}

if ($PythonExe -eq "py") {
    & py -3 -m py_compile $PyPath
} else {
    & python -m py_compile $PyPath
}
if ($LASTEXITCODE -ne 0) {
    throw "Python compile failed."
}
Write-Host "Python compile: PASS" -ForegroundColor Green

$scanFiles = @($PyPath, $SqlPath, $YmlPath)
$required = @(
    "PHASE365_PRODUCTION_PAPER_AUTONOMOUS_PROMOTION_CONTROL_CONTINUOUS_QUALIFICATION_ENGINE",
    "paper_continuous_qualification_v92",
    "paper_promotion_control_audit_v92",
    "QUALIFIED_WITH_OBSERVATION",
    "NOT_QUALIFIED",
    "REVOKED",
    "FAIL_CLOSED"
)

$combined = ($scanFiles | ForEach-Object { Get-Content -Raw $_ }) -join "`n"
foreach ($token in $required) {
    if ($combined -notmatch [regex]::Escape($token)) {
        throw "Phase 3.6.5 contract scan failed. Missing token: $token"
    }
}

$forbiddenPatterns = @(
    'broker_order_submission_enabled\s*=\s*True',
    'real_money_trading_enabled\s*=\s*True',
    'live_money_release_authorized\s*=\s*True'
)
foreach ($pattern in $forbiddenPatterns) {
    if ($combined -match $pattern) {
        throw "Safety scan failed: forbidden capability enabled ($pattern)"
    }
}

Write-Host "Phase 3.6.5 continuous-qualification contract scan: PASS" -ForegroundColor Green
Write-Host "Safety boundary scan: PASS" -ForegroundColor Green

Write-Section "DEPLOY COMPLETE"
Write-Host "Generated files:"
Write-Host "  automation/v92/paper_trading_phase365_autonomous_promotion_control_continuous_qualification_engine.py"
Write-Host "  supabase/PHASE365_PRODUCTION_PAPER_AUTONOMOUS_PROMOTION_CONTROL_CONTINUOUS_QUALIFICATION_ENGINE.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase365-autonomous-promotion-control-continuous-qualification-engine.yml"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Run the generated SQL once in Supabase SQL Editor."
Write-Host "  2. Commit and push generated files to main."
Write-Host "  3. Run the Phase 3.6.5 GitHub Action."
Write-Host ""
Write-Host "Safety remains PAPER ONLY / NO BROKER / NO REAL MONEY / FAIL-CLOSED." -ForegroundColor Yellow
