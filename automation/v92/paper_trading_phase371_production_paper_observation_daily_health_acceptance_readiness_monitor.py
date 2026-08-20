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

CONTRACT = "PHASE371_PRODUCTION_PAPER_OBSERVATION_DAILY_HEALTH_ACCEPTANCE_READINESS_MONITOR"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

READINESS_NOT_READY = "NOT_READY"
READINESS_READY_WITH_LIMITED_COVERAGE = "READY_WITH_LIMITED_COVERAGE"
READINESS_READY = "READY"
READINESS_BLOCKED = "BLOCKED"
READINESS_FAIL_CLOSED = "FAIL_CLOSED"

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
            with urllib.request.urlopen(req, timeout=45) as response:
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

def evaluate(observation: Dict[str, Any], controller: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    observation_state = str(observation.get("observation_state") or "MISSING").upper()
    observation_days = as_int(observation.get("observation_days"), 0)
    remaining_days = as_int(observation.get("remaining_minimum_days"), 0)
    pass_rate = as_float(observation.get("pass_rate"), 0.0)
    safety_revocations = as_int(observation.get("safety_revocation_days"), 0)
    chain_breaks = as_int(observation.get("evidence_chain_break_count"), 0)
    max_drawdown = as_float(observation.get("max_drawdown"), 0.0)
    signal_days = as_int(observation.get("signal_days"), 0)
    fill_days = as_int(observation.get("fill_days"), 0)
    validated = as_bool(observation.get("validated"), False)
    acceptance_candidate = as_bool(observation.get("acceptance_candidate"), False)

    controller_state = str((controller or {}).get("controller_state") or "MISSING").upper()
    controller_passed = as_bool((controller or {}).get("controller_passed"), False)

    hard_failures: List[str] = []
    notes: List[str] = []

    if observation_state == "FAIL_CLOSED":
        hard_failures.append("OBSERVATION_FAIL_CLOSED")
    if safety_revocations > 0:
        hard_failures.append("SAFETY_REVOCATION_PRESENT")
    if chain_breaks > 0:
        hard_failures.append("EVIDENCE_CHAIN_BREAK_PRESENT")
    if max_drawdown < -0.15:
        hard_failures.append("MAX_DRAWDOWN_EXCEEDED")
    if controller and (controller_state not in {"COMPLETED", "COMPLETED_WITH_OBSERVATION"} or not controller_passed):
        hard_failures.append("LATEST_CONTROLLER_NOT_PASS")

    if observation_days < 20:
        notes.append("MINIMUM_OBSERVATION_WINDOW_NOT_COMPLETE")
    if pass_rate < 0.95:
        notes.append("LIFECYCLE_PASS_RATE_BELOW_TARGET")
    if signal_days == 0:
        notes.append("NO_SIGNAL_COVERAGE_YET")
    if fill_days == 0:
        notes.append("NO_FILL_COVERAGE_YET")

    if hard_failures:
        readiness = READINESS_FAIL_CLOSED
    elif validated and acceptance_candidate and fill_days > 0:
        readiness = READINESS_READY
    elif validated and not hard_failures:
        readiness = READINESS_READY_WITH_LIMITED_COVERAGE
    else:
        readiness = READINESS_NOT_READY

    return {
        "readiness_state": readiness,
        "observation_state": observation_state,
        "observation_days": observation_days,
        "remaining_days": remaining_days,
        "pass_rate": pass_rate,
        "safety_revocations": safety_revocations,
        "chain_breaks": chain_breaks,
        "max_drawdown": max_drawdown,
        "signal_days": signal_days,
        "fill_days": fill_days,
        "validated": validated,
        "acceptance_candidate": acceptance_candidate,
        "controller_state": controller_state,
        "hard_failures": hard_failures,
        "notes": notes,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--monitor-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.monitor_date)

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

    observation = latest(
        sb,
        "paper_operations_observation_validation_v92",
        args.portfolio_id,
        "observation_date",
    )
    if observation is None:
        raise RuntimeError("Phase 3.7.0 observation state missing")

    controller = latest(
        sb,
        "paper_daily_autonomous_controller_v92",
        args.portfolio_id,
        "controller_date",
    )

    result = evaluate(observation, controller)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "monitor_date": args.monitor_date,
        "result": result,
        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_controller_evidence_sha256": (controller or {}).get("evidence_sha256"),
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
    evidence_sha = stable_hash(evidence_doc)

    payload = {
        "monitor_date": args.monitor_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "readiness_state": result["readiness_state"],
        "observation_state": result["observation_state"],
        "observation_days": result["observation_days"],
        "remaining_days": result["remaining_days"],
        "lifecycle_pass_rate": result["pass_rate"],
        "safety_revocation_days": result["safety_revocations"],
        "evidence_chain_break_count": result["chain_breaks"],
        "max_drawdown": result["max_drawdown"],
        "signal_days": result["signal_days"],
        "fill_days": result["fill_days"],
        "observation_validated": result["validated"],
        "acceptance_candidate": result["acceptance_candidate"],
        "latest_controller_state": result["controller_state"],

        "hard_failures": result["hard_failures"],
        "notes": result["notes"],

        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_controller_evidence_sha256": (controller or {}).get("evidence_sha256"),

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
        "paper_observation_acceptance_readiness_v92",
        payload,
        "portfolio_id,monitor_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_observation_acceptance_readiness_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.1")
    print()
    print("## Production Paper Observation Daily Health + Acceptance Readiness Monitor")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Monitor Date: `{args.monitor_date}`")
    print(f"- Acceptance Readiness: **{result['readiness_state']}**")
    print()
    print("## Observation Progress")
    print()
    print(f"- Observation Day: **{result['observation_days']} / 20**")
    print(f"- Remaining Days: **{result['remaining_days']}**")
    print(f"- Observation State: **{result['observation_state']}**")
    print(f"- Lifecycle PASS Rate: **{result['pass_rate'] * 100:.2f}%**")
    print(f"- Observation Validated: **{'YES' if result['validated'] else 'NO'}**")
    print(f"- Acceptance Candidate: **{'YES' if result['acceptance_candidate'] else 'NO'}**")
    print()
    print("## Daily Health")
    print()
    print(f"- Latest Controller State: **{result['controller_state']}**")
    print(f"- Safety Revocations: **{result['safety_revocations']}**")
    print(f"- Evidence Chain Breaks: **{result['chain_breaks']}**")
    print(f"- Maximum Drawdown: **{result['max_drawdown'] * 100:.4f}%**")
    print()
    print("## Coverage")
    print()
    print(f"- Signal Days: **{result['signal_days']}**")
    print(f"- Fill Days: **{result['fill_days']}**")

    if result["hard_failures"]:
        print()
        print("## Hard Failures")
        print()
        for item in result["hard_failures"]:
            print(f"- `{item}`")

    if result["notes"]:
        print()
        print("## Readiness Notes")
        print()
        for item in result["notes"]:
            print(f"- `{item}`")

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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase371")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "daily_acceptance_readiness.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "payload": payload,
                "evidence_document": evidence_doc,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE371_FATAL: {exc}", file=sys.stderr)
        raise