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

CONTRACT = "PHASE3653_CONTINUOUS_QUALIFICATION_STATE_TRANSITION_RECOVERY_FIX"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
FAIL_CLOSED_POLICY = True

RECOVERABLE_PREVIOUS_STATES = {"FAIL_CLOSED", "REVOKED", "NOT_QUALIFIED"}

def env_first(*names: str) -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
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

def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

class SB:
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
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8")
                return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc

    def get(self, table: str, query: str) -> List[Dict[str, Any]]:
        value = self.request("GET", table, query=query)
        return value if isinstance(value, list) else []

    def upsert(self, table: str, payload: Dict[str, Any], on_conflict: str) -> None:
        q = "on_conflict=" + urllib.parse.quote(on_conflict, safe=",")
        self.request(
            "POST",
            table,
            query=q,
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )

def latest(sb: SB, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    q = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, q)
    return rows[0] if rows else None

def current_qualification(sb: SB, portfolio_id: str) -> Optional[Dict[str, Any]]:
    q = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + "&order=qualification_date.desc&limit=1"
    )
    rows = sb.get("paper_continuous_qualification_v92", q)
    return rows[0] if rows else None

def gate_revalidation(
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

    readiness_state = str(readiness.get("readiness_status", "MISSING")).upper()
    readiness_score = as_float(readiness.get("readiness_score"), 0.0)
    gate_open = as_bool(readiness.get("promotion_gate_open"), False)

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

    incident_open = False
    incident_severity = "NONE"
    if incident:
        incident_state = str(
            incident.get("incident_state")
            or incident.get("incident_status")
            or incident.get("status")
            or "UNKNOWN"
        ).upper()
        incident_severity = str(incident.get("severity") or "UNKNOWN").upper()
        incident_open = incident_state not in {"CLOSED", "RESOLVED", "CLEAR", "NONE", "OBSERVED"}

    add("operational_readiness_state", readiness_state in {"READY", "READY_WITH_OBSERVATION"},
        readiness_state, "READY or READY_WITH_OBSERVATION")
    add("operational_readiness_score", readiness_score >= 90.0,
        readiness_score, ">= 90", "WARNING")
    add("promotion_gate_open", gate_open, gate_open, True)

    add("health_state", health_state in {"HEALTHY", "DEGRADED"},
        health_state, "HEALTHY or DEGRADED")
    add("health_score", health_score >= 90.0,
        health_score, ">= 90", "WARNING")

    add("sla_state", sla_state in {"SLA_PASS", "SLA_WARN"},
        sla_state, "SLA_PASS or SLA_WARN")
    add("sla_score", sla_score >= 75.0,
        sla_score, ">= 75", "WARNING")

    add("master_cycle", master_state in {"PASS", "SUCCESS", "COMPLETED", "HEALTHY"},
        master_state, "PASS/SUCCESS/COMPLETED/HEALTHY")

    add("critical_incident_absent",
        not (incident_open and incident_severity in {"CRITICAL", "HIGH", "SEV0", "SEV1"}),
        {"open": incident_open, "severity": incident_severity},
        "no open high/critical incident")

    safety_rows = {
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
            add(f"safety_{source}_fail_closed", row.get("fail_closed_policy") is True,
                row.get("fail_closed_policy"), True)

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
    score = round((passed_count / total) * 100.0, 4) if total else 0.0

    if critical_failures:
        target_state = "FAIL_CLOSED"
        authorized = False
    elif warning_failures:
        target_state = "QUALIFIED_WITH_OBSERVATION"
        authorized = True
    else:
        target_state = "QUALIFIED"
        authorized = True

    return {
        "checks": checks,
        "critical_failures": critical_failures,
        "warning_failures": warning_failures,
        "revalidated_score": score,
        "target_state": target_state,
        "authorized": authorized,
        "readiness_state": readiness_state,
        "readiness_score": readiness_score,
        "health_state": health_state,
        "health_score": health_score,
        "sla_state": sla_state,
        "sla_score": sla_score,
        "master_state": master_state,
        "incident_open": incident_open,
        "incident_severity": incident_severity,
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    ap.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    ap.add_argument("--qualification-date", default=str(date.today()))
    args = ap.parse_args()

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = SB(url, key)

    readiness = latest(sb, "paper_operational_readiness_v92", args.portfolio_id, "readiness_date")
    health = latest(sb, "paper_system_health_v92", args.portfolio_id, "health_date")
    sla = latest(sb, "paper_observability_daily_v92", args.portfolio_id, "observation_date")
    master = latest(sb, "paper_master_cycles_v92", args.portfolio_id, "cycle_date")
    incident = latest(sb, "paper_incident_audit_v92", args.portfolio_id, "incident_date")

    if readiness is None:
        raise RuntimeError("Canonical readiness evidence missing")
    if health is None:
        raise RuntimeError("Canonical health evidence missing")
    if sla is None:
        raise RuntimeError("Canonical SLA evidence missing")
    if master is None:
        raise RuntimeError("Canonical master-cycle evidence missing")

    previous = current_qualification(sb, args.portfolio_id)
    previous_state = str((previous or {}).get("qualification_state", "NONE")).upper()

    decision = gate_revalidation(readiness, health, sla, master, incident)
    target_state = decision["target_state"]
    authorized = bool(decision["authorized"])

    recovery_allowed = (
        previous_state in RECOVERABLE_PREVIOUS_STATES
        and target_state in {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}
        and not decision["critical_failures"]
    )

    if previous_state in RECOVERABLE_PREVIOUS_STATES and target_state in {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}:
        if not recovery_allowed:
            target_state = "FAIL_CLOSED"
            authorized = False

    transition = previous_state != target_state
    reasons: List[str] = []

    if decision["critical_failures"]:
        reasons.extend("CRITICAL_" + x.upper() for x in decision["critical_failures"])
    if decision["warning_failures"]:
        reasons.extend("OBSERVE_" + x.upper() for x in decision["warning_failures"])

    if recovery_allowed:
        reasons.insert(0, "CANONICAL_REVALIDATION_RECOVERY_ALLOWED")
    elif not reasons:
        reasons.append("CANONICAL_REVALIDATION_STABLE")

    evidence = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "qualification_date": args.qualification_date,
        "previous_state": previous_state,
        "target_state": target_state,
        "state_transition": transition,
        "recovery_allowed": recovery_allowed,
        "autonomous_paper_operations_authorized": authorized,
        "decision": decision,
        "reasons": reasons,
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
    evidence_sha = stable_hash(evidence)

    payload = {
        "qualification_date": args.qualification_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "previous_qualification_state": previous_state,
        "qualification_state": target_state,
        "qualification_score": decision["revalidated_score"],
        "autonomous_paper_operations_authorized": authorized,
        "readiness_state": decision["readiness_state"],
        "readiness_score": decision["readiness_score"],
        "health_state": decision["health_state"],
        "health_score": decision["health_score"],
        "sla_state": decision["sla_state"],
        "sla_score": decision["sla_score"],
        "master_cycle_state": decision["master_state"],
        "open_incident": decision["incident_open"],
        "incident_severity": decision["incident_severity"],
        "reason_codes": reasons,
        "evidence_sha256": evidence_sha,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    sb.upsert(
        "paper_continuous_qualification_v92",
        payload,
        "portfolio_id,qualification_date",
    )

    if transition:
        sb.request(
            "POST",
            "paper_promotion_control_audit_v92",
            payload={
                "qualification_date": args.qualification_date,
                "portfolio_id": args.portfolio_id,
                "strategy_version": args.strategy_version,
                "from_state": previous_state,
                "to_state": target_state,
                "autonomous_paper_operations_authorized": authorized,
                "reason_codes": reasons,
                "evidence_sha256": evidence_sha,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=minimal",
        )

    recovery_row = {
        "recovery_date": args.qualification_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "previous_state": previous_state,
        "target_state": target_state,
        "recovery_allowed": recovery_allowed,
        "state_transition": transition,
        "autonomous_paper_operations_authorized": authorized,
        "revalidated_score": decision["revalidated_score"],
        "critical_failures": decision["critical_failures"],
        "warning_failures": decision["warning_failures"],
        "reason_codes": reasons,
        "evidence_sha256": evidence_sha,
        "paper_only": True,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    sb.upsert(
        "paper_qualification_recovery_audit_v92",
        recovery_row,
        "portfolio_id,recovery_date",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.5.3")
    print()
    print("## Continuous Qualification State Transition Recovery Fix")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Previous State: **{previous_state}**")
    print(f"- Revalidated Score: **{decision['revalidated_score']:.4f}**")
    print(f"- Recovery Allowed: **{'YES' if recovery_allowed else 'NO'}**")
    print(f"- Target Qualification State: **{target_state}**")
    print(f"- State Transition: **{'YES' if transition else 'NO'}**")
    print(f"- Autonomous Paper Operations Authorized: **{'YES' if authorized else 'NO'}**")
    print()
    print("## Canonical Revalidation")
    print()
    print(f"- Operational Readiness: `{decision['readiness_state']}` / {decision['readiness_score']:.4f}")
    print(f"- Health: `{decision['health_state']}` / {decision['health_score']:.4f}")
    print(f"- SLA: `{decision['sla_state']}` / {decision['sla_score']:.4f}")
    print(f"- Master Cycle: `{decision['master_state']}`")
    print(f"- Open Incident: **{'YES' if decision['incident_open'] else 'NO'}**")
    print(f"- Incident Severity: `{decision['incident_severity']}`")
    print()
    print("## Recovery Reasons")
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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3653")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "recovery_evidence.json"), "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    # Governance result can remain fail-closed without treating the workflow as a software failure.
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3653_FATAL: {exc}", file=sys.stderr)
        raise