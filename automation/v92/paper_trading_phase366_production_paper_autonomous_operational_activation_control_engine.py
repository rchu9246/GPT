from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE366_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONAL_ACTIVATION_CONTROL_ENGINE"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
FAIL_CLOSED_POLICY = True

ACTIVATION_ACTIVE = "ACTIVE"
ACTIVATION_ACTIVE_OBSERVATION = "ACTIVE_WITH_OBSERVATION"
ACTIVATION_INACTIVE = "INACTIVE"
ACTIVATION_BLOCKED = "BLOCKED"
ACTIVATION_FAIL_CLOSED = "FAIL_CLOSED"

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

def activation_decision(
    qualification: Dict[str, Any],
    readiness: Dict[str, Any],
    health: Dict[str, Any],
    sla: Dict[str, Any],
    master: Dict[str, Any],
    incident: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    checks: Dict[str, Dict[str, Any]] = {}

    def add(name: str, passed: bool, value: Any, expected: Any, severity: str = "CRITICAL") -> None:
        checks[name] = {
            "passed": bool(passed),
            "value": value,
            "expected": expected,
            "severity": severity,
        }

    q_state = str(qualification.get("qualification_state", "MISSING")).upper()
    q_auth = as_bool(qualification.get("autonomous_paper_operations_authorized"), False)
    q_score = as_float(qualification.get("qualification_score"), 0.0)

    r_state = str(readiness.get("readiness_status", "MISSING")).upper()
    r_gate = as_bool(readiness.get("promotion_gate_open"), False)
    r_score = as_float(readiness.get("readiness_score"), 0.0)

    h_state = str(health.get("health_status", "MISSING")).upper()
    h_score = as_float(health.get("health_score"), 0.0)

    s_state = str(sla.get("sla_status", "MISSING")).upper()
    s_score = as_float(sla.get("sla_score"), 0.0)

    m_state = str(
        master.get("cycle_status")
        or master.get("master_status")
        or master.get("status")
        or "MISSING"
    ).upper()

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

    add("qualification_state", q_state in QUALIFIED_STATES, q_state, "QUALIFIED or QUALIFIED_WITH_OBSERVATION")
    add("qualification_authorization", q_auth is True, q_auth, True)
    add("qualification_score", q_score >= 75.0, q_score, ">= 75", "WARNING")

    add("readiness_state", r_state in {"READY", "READY_WITH_OBSERVATION"}, r_state, "READY or READY_WITH_OBSERVATION")
    add("promotion_gate_open", r_gate is True, r_gate, True)
    add("readiness_score", r_score >= 90.0, r_score, ">= 90", "WARNING")

    add("health_state", h_state in {"HEALTHY", "DEGRADED"}, h_state, "HEALTHY or DEGRADED")
    add("health_score", h_score >= 90.0, h_score, ">= 90", "WARNING")

    add("sla_state", s_state in {"SLA_PASS", "SLA_WARN"}, s_state, "SLA_PASS or SLA_WARN")
    add("sla_score", s_score >= 75.0, s_score, ">= 75", "WARNING")

    add("master_cycle", m_state in {"PASS", "SUCCESS", "COMPLETED", "HEALTHY"}, m_state, "PASS/SUCCESS/COMPLETED/HEALTHY")

    add(
        "blocking_incident_absent",
        not (incident_open and incident_severity in {"CRITICAL", "HIGH", "SEV0", "SEV1"}),
        {"open": incident_open, "severity": incident_severity},
        "no open high/critical incident",
    )

    safety_rows = {
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
    activation_score = round((passed_count / total) * 100.0, 4) if total else 0.0

    if critical_failures:
        safety_failure = any(name.startswith("safety_") for name in critical_failures)
        activation_state = ACTIVATION_FAIL_CLOSED if safety_failure else ACTIVATION_BLOCKED
        active = False
    elif warning_failures or q_state == "QUALIFIED_WITH_OBSERVATION" or r_state == "READY_WITH_OBSERVATION" or h_state == "DEGRADED" or s_state == "SLA_WARN":
        activation_state = ACTIVATION_ACTIVE_OBSERVATION
        active = True
    else:
        activation_state = ACTIVATION_ACTIVE
        active = True

    return {
        "checks": checks,
        "critical_failures": critical_failures,
        "warning_failures": warning_failures,
        "activation_state": activation_state,
        "activation_score": activation_score,
        "active": active,
        "qualification_state": q_state,
        "qualification_score": q_score,
        "readiness_state": r_state,
        "readiness_score": r_score,
        "health_state": h_state,
        "health_score": h_score,
        "sla_state": s_state,
        "sla_score": s_score,
        "master_state": m_state,
        "incident_open": incident_open,
        "incident_severity": incident_severity,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--activation-date", default=str(date.today()))
    args = parser.parse_args()

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

    qualification = latest(sb, "paper_continuous_qualification_v92", args.portfolio_id, "qualification_date")
    readiness = latest(sb, "paper_operational_readiness_v92", args.portfolio_id, "readiness_date")
    health = latest(sb, "paper_system_health_v92", args.portfolio_id, "health_date")
    sla = latest(sb, "paper_observability_daily_v92", args.portfolio_id, "observation_date")
    master = latest(sb, "paper_master_cycles_v92", args.portfolio_id, "cycle_date")
    incident = latest(sb, "paper_incident_audit_v92", args.portfolio_id, "incident_date")

    missing = []
    if qualification is None: missing.append("continuous_qualification")
    if readiness is None: missing.append("operational_readiness")
    if health is None: missing.append("health")
    if sla is None: missing.append("sla")
    if master is None: missing.append("master_cycle")

    if missing:
        raise RuntimeError("Missing canonical activation evidence: " + ", ".join(missing))

    decision = activation_decision(
        qualification,
        readiness,
        health,
        sla,
        master,
        incident,
    )

    reasons: List[str] = []
    reasons.extend("CRITICAL_" + x.upper() for x in decision["critical_failures"])
    reasons.extend("OBSERVE_" + x.upper() for x in decision["warning_failures"])
    if not reasons:
        reasons.append("ALL_ACTIVATION_GATES_PASS")

    evidence = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "activation_date": args.activation_date,
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

    activation_payload = {
        "activation_date": args.activation_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "activation_state": decision["activation_state"],
        "activation_score": decision["activation_score"],
        "autonomous_paper_operations_active": decision["active"],

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
        "paper_autonomous_activation_state_v92",
        activation_payload,
        "portfolio_id,activation_date",
    )

    audit_payload = {
        "activation_date": args.activation_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "activation_state": decision["activation_state"],
        "activation_score": decision["activation_score"],
        "autonomous_paper_operations_active": decision["active"],
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
        "paper_autonomous_activation_audit_v92",
        payload=audit_payload,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.6")
    print()
    print("## Production Paper Autonomous Operational Activation Control Engine")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Activation Date: `{args.activation_date}`")
    print(f"- Qualification State: **{decision['qualification_state']}**")
    print(f"- Qualification Score: **{decision['qualification_score']:.4f}**")
    print(f"- Activation State: **{decision['activation_state']}**")
    print(f"- Activation Score: **{decision['activation_score']:.4f}**")
    print(f"- Autonomous Paper Operations Active: **{'YES' if decision['active'] else 'NO'}**")
    print()
    print("## Canonical Activation Inputs")
    print()
    print(f"- Operational Readiness: `{decision['readiness_state']}` / {decision['readiness_score']:.4f}")
    print(f"- Health: `{decision['health_state']}` / {decision['health_score']:.4f}")
    print(f"- SLA: `{decision['sla_state']}` / {decision['sla_score']:.4f}")
    print(f"- Master Cycle: `{decision['master_state']}`")
    print(f"- Open Incident: **{'YES' if decision['incident_open'] else 'NO'}**")
    print(f"- Incident Severity: `{decision['incident_severity']}`")
    print()
    print("## Activation Reasons")
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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase366")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "activation_evidence.json"), "w", encoding="utf-8") as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE366_FATAL: {exc}", file=sys.stderr)
        raise