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

CONTRACT = "PHASE372_PRODUCTION_PAPER_OBSERVATION_DAILY_AUTOMATION_ACCEPTANCE_PROMOTION_CONTROLLER"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

STATE_OBSERVATION_CONTINUES = "OBSERVATION_CONTINUES"
STATE_ACCEPTANCE_ELIGIBLE = "PAPER_ACCEPTANCE_ELIGIBLE"
STATE_LIMITED_COVERAGE = "PAPER_ACCEPTANCE_LIMITED_COVERAGE"
STATE_HELD = "PROMOTION_HELD"
STATE_FAIL_CLOSED = "FAIL_CLOSED"

SAFE_READINESS = {
    "NOT_READY",
    "READY",
    "READY_WITH_LIMITED_COVERAGE",
}

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

def latest(
    sb: Supabase,
    table: str,
    portfolio_id: str,
    order_column: str,
) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def evaluate(
    readiness: Dict[str, Any],
    observation: Dict[str, Any],
    lifecycle: Dict[str, Any],
) -> Dict[str, Any]:
    readiness_state = str(readiness.get("readiness_state") or "MISSING").upper()
    observation_state = str(observation.get("observation_state") or "MISSING").upper()
    lifecycle_state = str(lifecycle.get("lifecycle_state") or "MISSING").upper()

    observation_days = as_int(readiness.get("observation_days"), 0)
    remaining_days = as_int(readiness.get("remaining_days"), 0)
    pass_rate = as_float(readiness.get("lifecycle_pass_rate"), 0.0)
    safety_revocations = as_int(readiness.get("safety_revocation_days"), 0)
    chain_breaks = as_int(readiness.get("evidence_chain_break_count"), 0)
    max_drawdown = as_float(readiness.get("max_drawdown"), 0.0)
    signal_days = as_int(readiness.get("signal_days"), 0)
    fill_days = as_int(readiness.get("fill_days"), 0)

    observation_validated = as_bool(readiness.get("observation_validated"), False)
    acceptance_candidate = as_bool(readiness.get("acceptance_candidate"), False)
    lifecycle_passed = as_bool(lifecycle.get("lifecycle_passed"), False)

    reasons: List[str] = []
    hard_failures: List[str] = []

    if readiness_state not in SAFE_READINESS:
        hard_failures.append("READINESS_UNSAFE_OR_UNKNOWN")
    if observation_state == "FAIL_CLOSED":
        hard_failures.append("OBSERVATION_FAIL_CLOSED")
    if lifecycle_state == "FAIL_CLOSED" or not lifecycle_passed:
        hard_failures.append("LATEST_LIFECYCLE_NOT_PASS")
    if safety_revocations > 0:
        hard_failures.append("SAFETY_REVOCATION_PRESENT")
    if chain_breaks > 0:
        hard_failures.append("EVIDENCE_CHAIN_BREAK_PRESENT")
    if max_drawdown < -0.15:
        hard_failures.append("MAX_DRAWDOWN_EXCEEDED")

    if hard_failures:
        promotion_state = STATE_FAIL_CLOSED
        promotion_authorized = False
        reasons.extend(hard_failures)

    elif readiness_state == "READY":
        if (
            observation_days >= 20
            and remaining_days == 0
            and pass_rate >= 0.95
            and observation_validated
            and acceptance_candidate
        ):
            promotion_state = STATE_ACCEPTANCE_ELIGIBLE
            promotion_authorized = True
            reasons.append("PAPER_ACCEPTANCE_ELIGIBILITY_PROMOTED")
        else:
            promotion_state = STATE_HELD
            promotion_authorized = False
            reasons.append("READY_STATE_CANONICAL_CONTRACT_INCONSISTENT")

    elif readiness_state == "READY_WITH_LIMITED_COVERAGE":
        if observation_days >= 20 and observation_validated:
            promotion_state = STATE_LIMITED_COVERAGE
            promotion_authorized = False
            reasons.append("VALIDATED_BUT_TRADE_COVERAGE_LIMITED")
        else:
            promotion_state = STATE_HELD
            promotion_authorized = False
            reasons.append("LIMITED_COVERAGE_STATE_NOT_MATURE")

    else:
        promotion_state = STATE_OBSERVATION_CONTINUES
        promotion_authorized = False
        reasons.append("OBSERVATION_WINDOW_CONTINUES")

    return {
        "promotion_state": promotion_state,
        "promotion_authorized": promotion_authorized,
        "readiness_state": readiness_state,
        "observation_state": observation_state,
        "lifecycle_state": lifecycle_state,
        "observation_days": observation_days,
        "remaining_days": remaining_days,
        "pass_rate": pass_rate,
        "safety_revocations": safety_revocations,
        "chain_breaks": chain_breaks,
        "max_drawdown": max_drawdown,
        "signal_days": signal_days,
        "fill_days": fill_days,
        "observation_validated": observation_validated,
        "acceptance_candidate": acceptance_candidate,
        "reasons": reasons,
        "hard_failures": hard_failures,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--promotion-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.promotion_date)

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

    readiness = latest(
        sb,
        "paper_observation_acceptance_readiness_v92",
        args.portfolio_id,
        "monitor_date",
    )
    if readiness is None:
        raise RuntimeError("Phase 3.7.1 readiness state missing")

    observation = latest(
        sb,
        "paper_operations_observation_validation_v92",
        args.portfolio_id,
        "observation_date",
    )
    if observation is None:
        raise RuntimeError("Phase 3.7.0 observation state missing")

    lifecycle = latest(
        sb,
        "paper_daily_lifecycle_evidence_v92",
        args.portfolio_id,
        "evidence_date",
    )
    if lifecycle is None:
        raise RuntimeError("Phase 3.6.9 lifecycle evidence missing")

    result = evaluate(readiness, observation, lifecycle)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "promotion_date": args.promotion_date,
        "result": result,
        "source_readiness_evidence_sha256": readiness.get("evidence_sha256"),
        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_lifecycle_evidence_sha256": lifecycle.get("evidence_sha256"),
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
        "promotion_date": args.promotion_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "promotion_state": result["promotion_state"],
        "paper_acceptance_eligibility_promoted": result["promotion_authorized"],

        "readiness_state": result["readiness_state"],
        "observation_state": result["observation_state"],
        "lifecycle_state": result["lifecycle_state"],

        "observation_days": result["observation_days"],
        "remaining_days": result["remaining_days"],
        "lifecycle_pass_rate": result["pass_rate"],
        "safety_revocation_days": result["safety_revocations"],
        "evidence_chain_break_count": result["chain_breaks"],
        "max_drawdown": result["max_drawdown"],
        "signal_days": result["signal_days"],
        "fill_days": result["fill_days"],

        "observation_validated": result["observation_validated"],
        "acceptance_candidate": result["acceptance_candidate"],

        "reason_codes": result["reasons"],
        "hard_failures": result["hard_failures"],

        "source_readiness_evidence_sha256": readiness.get("evidence_sha256"),
        "source_observation_evidence_sha256": observation.get("evidence_sha256"),
        "source_lifecycle_evidence_sha256": lifecycle.get("evidence_sha256"),

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
        "paper_acceptance_promotion_control_v92",
        payload,
        "portfolio_id,promotion_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_acceptance_promotion_control_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2")
    print()
    print("## Production Paper Observation Daily Automation + Acceptance Promotion Controller")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Promotion Date: `{args.promotion_date}`")
    print(f"- Promotion State: **{result['promotion_state']}**")
    print(f"- Paper Acceptance Eligibility Promoted: **{'YES' if result['promotion_authorized'] else 'NO'}**")
    print()
    print("## Canonical Inputs")
    print()
    print(f"- Acceptance Readiness: **{result['readiness_state']}**")
    print(f"- Observation State: **{result['observation_state']}**")
    print(f"- Lifecycle State: **{result['lifecycle_state']}**")
    print(f"- Observation Day: **{result['observation_days']} / 20**")
    print(f"- Remaining Days: **{result['remaining_days']}**")
    print(f"- Lifecycle PASS Rate: **{result['pass_rate'] * 100:.2f}%**")
    print(f"- Observation Validated: **{'YES' if result['observation_validated'] else 'NO'}**")
    print(f"- Acceptance Candidate: **{'YES' if result['acceptance_candidate'] else 'NO'}**")
    print()
    print("## Safety / Coverage")
    print()
    print(f"- Safety Revocations: **{result['safety_revocations']}**")
    print(f"- Evidence Chain Breaks: **{result['chain_breaks']}**")
    print(f"- Maximum Drawdown: **{result['max_drawdown'] * 100:.4f}%**")
    print(f"- Signal Days: **{result['signal_days']}**")
    print(f"- Fill Days: **{result['fill_days']}**")
    print()
    print("## Promotion Reasons")
    print()
    for item in result["reasons"]:
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
    print("- Real-money promotion authority: **NOT PRESENT IN THIS PHASE**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase372")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "acceptance_promotion_control.json"),
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

    # OBSERVATION_CONTINUES is the expected successful state during Day 1..19.
    # FAIL_CLOSED is persisted as a governance outcome; runtime faults still fail.
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE372_FATAL: {exc}", file=sys.stderr)
        raise