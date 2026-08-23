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

CONTRACT = "PHASE3722_OBSERVATION_FAIL_CLOSED_ROOT_CAUSE_DIAGNOSTIC_RECOVERY"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

RECOVERY_NOT_NEEDED = "NOT_NEEDED"
RECOVERY_SAFE_RERUN = "SAFE_CANONICAL_RERUN"
RECOVERY_BLOCKED = "BLOCKED_BY_TRUE_SAFETY_FAILURE"
RECOVERY_NEEDS_REVIEW = "NEEDS_REVIEW"

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

    def request(self, method: str, table: str, query: str = "", payload: Optional[Any] = None, prefer: Optional[str] = None) -> Any:
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
        self.request("POST", table, query=query, payload=payload, prefer="resolution=merge-duplicates,return=minimal")

def latest(sb: Supabase, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def row_date(row: Optional[Dict[str, Any]], *names: str) -> Optional[str]:
    if not row:
        return None
    for name in names:
        value = row.get(name)
        if value:
            return str(value)[:10]
    return None

def text(row: Optional[Dict[str, Any]], *names: str, default: str = "MISSING") -> str:
    if not row:
        return default
    for name in names:
        value = row.get(name)
        if value is not None:
            return str(value).upper()
    return default

def truth(row: Optional[Dict[str, Any]], *names: str, default: bool = False) -> bool:
    if not row:
        return default
    for name in names:
        if name in row:
            return as_bool(row.get(name), default)
    return default

def diagnose(supervision, controller, lifecycle, observation, readiness, promotion):
    reasons: List[str] = []
    true_safety_failures: List[str] = []
    stale_or_propagation_issues: List[str] = []

    supervision_state = text(supervision, "supervision_state", "runtime_supervision_state", "state")
    controller_state = text(controller, "controller_state")
    lifecycle_state = text(lifecycle, "lifecycle_state")
    observation_state = text(observation, "observation_state")
    readiness_state = text(readiness, "readiness_state")
    promotion_state = text(promotion, "promotion_state")

    supervision_revoked = (
        truth(supervision, "safety_revocation_triggered", default=False)
        or supervision_state in {"REVOKED", "FAIL_CLOSED", "STOP", "BLOCKED"}
    )
    controller_revoked = truth(controller, "safety_revocation_triggered", default=False)
    lifecycle_revoked = truth(lifecycle, "safety_revocation_triggered", default=False)

    observation_revocation_days = as_int((observation or {}).get("safety_revocation_days"), 0)
    readiness_revocation_days = as_int((readiness or {}).get("safety_revocation_days"), 0)

    if supervision_revoked:
        true_safety_failures.append("RUNTIME_SUPERVISION_REVOKED")
    if controller_revoked:
        true_safety_failures.append("DAILY_CONTROLLER_REVOKED")
    if lifecycle_revoked:
        true_safety_failures.append("LATEST_LIFECYCLE_REVOKED")

    dates = {
        "supervision": row_date(supervision, "supervision_date", "run_date", "created_at"),
        "controller": row_date(controller, "controller_date", "run_date", "created_at"),
        "lifecycle": row_date(lifecycle, "evidence_date", "run_date", "created_at"),
        "observation": row_date(observation, "observation_date", "created_at"),
        "readiness": row_date(readiness, "monitor_date", "created_at"),
        "promotion": row_date(promotion, "promotion_date", "created_at"),
    }

    known_dates = [d for d in dates.values() if d]
    newest_date = max(known_dates) if known_dates else None
    if newest_date:
        for name, d in dates.items():
            if d and d != newest_date:
                stale_or_propagation_issues.append(f"{name.upper()}_DATE_MISMATCH:{d}!={newest_date}")

    if (
        lifecycle_state == "FAIL_CLOSED"
        and not lifecycle_revoked
        and controller_state in {"COMPLETED", "COMPLETED_WITH_OBSERVATION"}
        and not controller_revoked
        and supervision_state in {"CONTINUE_ACTIVE", "CONTINUE_WITH_OBSERVATION", "ACTIVE", "HEALTHY"}
        and not supervision_revoked
    ):
        stale_or_propagation_issues.append("LIFECYCLE_FAIL_CLOSED_WITH_HEALTHY_UPSTREAM")

    if observation_state == "FAIL_CLOSED" and lifecycle_state in {"PASS", "PASS_WITH_OBSERVATION"} and not lifecycle_revoked:
        stale_or_propagation_issues.append("OBSERVATION_FAIL_CLOSED_WITH_PASSING_LIFECYCLE")

    if readiness_state == "FAIL_CLOSED" and observation_state not in {"FAIL_CLOSED", "MISSING"} and observation_revocation_days == 0:
        stale_or_propagation_issues.append("READINESS_FAIL_CLOSED_WITH_HEALTHY_OBSERVATION")

    if promotion_state == "FAIL_CLOSED" and readiness_state not in {"FAIL_CLOSED", "MISSING"}:
        stale_or_propagation_issues.append("PROMOTION_FAIL_CLOSED_WITH_HEALTHY_READINESS")

    if observation_revocation_days > 0:
        reasons.append(f"OBSERVATION_REPORTED_REVOCATION_DAYS:{observation_revocation_days}")
    if readiness_revocation_days > 0:
        reasons.append(f"READINESS_REPORTED_REVOCATION_DAYS:{readiness_revocation_days}")

    if true_safety_failures:
        recovery_state = RECOVERY_BLOCKED
        safe_to_rerun = False
        reasons.extend(true_safety_failures)
    elif stale_or_propagation_issues:
        recovery_state = RECOVERY_SAFE_RERUN
        safe_to_rerun = True
        reasons.extend(stale_or_propagation_issues)
    elif all(state not in {"FAIL_CLOSED", "MISSING"} for state in (lifecycle_state, observation_state, readiness_state, promotion_state)):
        recovery_state = RECOVERY_NOT_NEEDED
        safe_to_rerun = False
        reasons.append("CURRENT_CHAIN_NOT_FAIL_CLOSED")
    else:
        recovery_state = RECOVERY_NEEDS_REVIEW
        safe_to_rerun = False
        reasons.append("FAIL_CLOSED_ROOT_CAUSE_NOT_PROVEN_SAFE")

    if (observation_revocation_days > 0 or readiness_revocation_days > 0) and not true_safety_failures:
        reasons.append("HISTORICAL_REVOCATION_COUNT_REQUIRES_SOURCE_AUDIT")

    return {
        "recovery_state": recovery_state,
        "safe_to_rerun_canonical_chain": safe_to_rerun,
        "historical_rewrite_allowed": False,
        "true_safety_failures": true_safety_failures,
        "stale_or_propagation_issues": stale_or_propagation_issues,
        "reasons": reasons,
        "states": {
            "supervision": supervision_state,
            "controller": controller_state,
            "lifecycle": lifecycle_state,
            "observation": observation_state,
            "readiness": readiness_state,
            "promotion": promotion_state,
        },
        "dates": dates,
        "observation_revocation_days": observation_revocation_days,
        "readiness_revocation_days": readiness_revocation_days,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--diagnostic-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.diagnostic_date)

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "VITE_SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = Supabase(url, key)

    supervision = latest(sb, "paper_runtime_supervision_v92", args.portfolio_id, "supervision_date")
    controller = latest(sb, "paper_daily_autonomous_controller_v92", args.portfolio_id, "controller_date")
    lifecycle = latest(sb, "paper_daily_lifecycle_evidence_v92", args.portfolio_id, "evidence_date")
    observation = latest(sb, "paper_operations_observation_validation_v92", args.portfolio_id, "observation_date")
    readiness = latest(sb, "paper_observation_acceptance_readiness_v92", args.portfolio_id, "monitor_date")
    promotion = latest(sb, "paper_acceptance_promotion_control_v92", args.portfolio_id, "promotion_date")

    result = diagnose(supervision, controller, lifecycle, observation, readiness, promotion)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "diagnostic_date": args.diagnostic_date,
        "result": result,
        "safety": {
            "paper_only": True,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "historical_rewrite_allowed": False,
        },
    }
    evidence_sha = stable_hash(evidence_doc)

    payload = {
        "diagnostic_date": args.diagnostic_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "recovery_state": result["recovery_state"],
        "safe_to_rerun_canonical_chain": result["safe_to_rerun_canonical_chain"],
        "historical_rewrite_allowed": False,

        "runtime_supervision_state": result["states"]["supervision"],
        "controller_state": result["states"]["controller"],
        "lifecycle_state": result["states"]["lifecycle"],
        "observation_state": result["states"]["observation"],
        "readiness_state": result["states"]["readiness"],
        "promotion_state": result["states"]["promotion"],

        "runtime_supervision_date": result["dates"]["supervision"],
        "controller_date": result["dates"]["controller"],
        "lifecycle_date": result["dates"]["lifecycle"],
        "observation_date": result["dates"]["observation"],
        "readiness_date": result["dates"]["readiness"],
        "promotion_date": result["dates"]["promotion"],

        "observation_revocation_days": result["observation_revocation_days"],
        "readiness_revocation_days": result["readiness_revocation_days"],

        "true_safety_failures": result["true_safety_failures"],
        "stale_or_propagation_issues": result["stale_or_propagation_issues"],
        "reason_codes": result["reasons"],

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

    sb.upsert("paper_observation_fail_closed_diagnostic_v92", payload, "portfolio_id,diagnostic_date")

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request("POST", "paper_observation_fail_closed_diagnostic_audit_v92", payload=audit, prefer="return=minimal")

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.2")
    print()
    print("## Observation FAIL_CLOSED Root Cause Diagnostic + Safe Recovery")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Diagnostic Date: `{args.diagnostic_date}`")
    print(f"- Recovery State: **{result['recovery_state']}**")
    print(f"- Safe To Re-run Canonical Chain: **{'YES' if result['safe_to_rerun_canonical_chain'] else 'NO'}**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical State Snapshot")
    print()
    for name in ("supervision", "controller", "lifecycle", "observation", "readiness", "promotion"):
        print(f"- {name.title()}: **{result['states'][name]}** (date `{result['dates'][name] or 'MISSING'}`)")
    print()
    print("## Revocation Diagnostics")
    print()
    print(f"- Observation Revocation Days: **{result['observation_revocation_days']}**")
    print(f"- Readiness Revocation Days: **{result['readiness_revocation_days']}**")
    print(f"- True Safety Failures: **{len(result['true_safety_failures'])}**")
    print(f"- Stale/Propagation Issues: **{len(result['stale_or_propagation_issues'])}**")
    print()
    print("## Diagnostic Reasons")
    print()
    for item in result["reasons"]:
        print(f"- `{item}`")
    print()
    print("## Recovery Instruction")
    print()
    if result["recovery_state"] == RECOVERY_SAFE_RERUN:
        print("- **SAFE RECOVERY PATH:** re-run canonical chain in order:")
        print("  `Phase 3.6.9 -> Phase 3.7.0 -> Phase 3.7.1 -> Phase 3.7.2`")
        print("- Do **not** delete or rewrite prior lifecycle evidence.")
    elif result["recovery_state"] == RECOVERY_BLOCKED:
        print("- **RECOVERY BLOCKED:** a real safety failure/revocation is present.")
        print("- Inspect Phase 3.6.7 / 3.6.8 before any downstream re-run.")
    elif result["recovery_state"] == RECOVERY_NOT_NEEDED:
        print("- Current canonical chain is not FAIL_CLOSED; no recovery required.")
    else:
        print("- Root cause is not proven safe. Keep FAIL_CLOSED and review source evidence.")
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
    print("- Historical evidence rewrite: **DISABLED**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3722")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "fail_closed_diagnostic.json"), "w", encoding="utf-8") as handle:
        json.dump({"payload": payload, "evidence_document": evidence_doc}, handle, ensure_ascii=False, indent=2)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3722_FATAL: {exc}", file=sys.stderr)
        raise