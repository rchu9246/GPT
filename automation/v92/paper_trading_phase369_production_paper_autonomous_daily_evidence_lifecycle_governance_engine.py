from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE369_PRODUCTION_PAPER_AUTONOMOUS_DAILY_EVIDENCE_LIFECYCLE_GOVERNANCE_ENGINE"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

LIFECYCLE_PASS = "PASS"
LIFECYCLE_PASS_OBSERVATION = "PASS_WITH_OBSERVATION"
LIFECYCLE_BLOCKED = "BLOCKED"
LIFECYCLE_FAIL_CLOSED = "FAIL_CLOSED"

VALID_CONTROLLER_STATES = {"COMPLETED", "COMPLETED_WITH_OBSERVATION"}

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

def exact_date(sb: Supabase, table: str, portfolio_id: str, date_column: str, business_date: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + "&" + date_column + "=eq." + urllib.parse.quote(business_date, safe="") + "&limit=2"
    )
    rows = sb.get(table, query)
    if len(rows) > 1:
        raise RuntimeError("AMBIGUOUS_SAME_DATE_EVIDENCE")
    return rows[0] if rows else None

def latest_before(
    sb: Supabase,
    table: str,
    portfolio_id: str,
    date_column: str,
    current_date: str,
) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + "&" + date_column + "=lt." + urllib.parse.quote(current_date, safe="")
        + f"&order={date_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def compact_master(master: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not master:
        return {}
    return {
        "cycle_date": master.get("cycle_date"),
        "cycle_status": master.get("cycle_status"),
        "final_state": master.get("final_state"),
        "eligible_signals": as_int(master.get("eligible_signals"), 0),
        "sized_candidates": as_int(master.get("sized_candidates"), 0),
        "order_intents_created": as_int(master.get("order_intents_created"), 0),
        "simulated_fills_created": as_int(master.get("simulated_fills_created"), 0),
        "fills_settled": as_int(master.get("fills_settled"), 0),
        "cash": as_float(master.get("cash"), 0.0),
        "market_value": as_float(master.get("market_value"), 0.0),
        "nav": as_float(master.get("nav"), 0.0),
        "realized_pnl": as_float(master.get("realized_pnl"), 0.0),
        "unrealized_pnl": as_float(master.get("unrealized_pnl"), 0.0),
        "open_positions": as_int(master.get("open_positions"), 0),
        "evidence_sha256": master.get("evidence_sha256"),
    }

def evaluate(controller: Dict[str, Any]) -> Dict[str, Any]:
    controller_state = str(controller.get("controller_state") or "MISSING").upper()
    controller_passed = as_bool(controller.get("controller_passed"), False)
    authorized = as_bool(controller.get("autonomous_daily_operations_authorized"), False)
    cycle_executed = as_bool(controller.get("daily_paper_cycle_executed"), False)
    safety_revocation = as_bool(controller.get("safety_revocation_triggered"), False)

    activation_state = str(controller.get("activation_state") or "MISSING").upper()
    qualification_state = str(controller.get("qualification_state") or "MISSING").upper()
    supervision_state = str(controller.get("runtime_supervision_state") or "MISSING").upper()
    master_cycle_state = str(controller.get("master_cycle_state") or "MISSING").upper()

    reasons: List[str] = []

    if controller_state not in VALID_CONTROLLER_STATES:
        reasons.append("CONTROLLER_STATE_NOT_COMPLETED")
    if not controller_passed:
        reasons.append("CONTROLLER_NOT_PASSED")
    if not authorized:
        reasons.append("AUTONOMOUS_DAILY_OPERATIONS_NOT_AUTHORIZED")
    if not cycle_executed:
        reasons.append("DAILY_PAPER_CYCLE_NOT_EXECUTED")
    if safety_revocation:
        reasons.append("SAFETY_REVOCATION_TRIGGERED")

    if activation_state not in {"ACTIVE", "ACTIVE_WITH_OBSERVATION"}:
        reasons.append("ACTIVATION_NOT_ACTIVE")
    if qualification_state not in {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}:
        reasons.append("QUALIFICATION_NOT_VALID")
    if supervision_state not in {"CONTINUE_ACTIVE", "CONTINUE_WITH_OBSERVATION"}:
        reasons.append("RUNTIME_SUPERVISION_NOT_CONTINUABLE")

    if reasons:
        state = LIFECYCLE_FAIL_CLOSED
        passed = False
    elif (
        controller_state == "COMPLETED_WITH_OBSERVATION"
        or activation_state == "ACTIVE_WITH_OBSERVATION"
        or qualification_state == "QUALIFIED_WITH_OBSERVATION"
        or supervision_state == "CONTINUE_WITH_OBSERVATION"
    ):
        state = LIFECYCLE_PASS_OBSERVATION
        passed = True
    else:
        state = LIFECYCLE_PASS
        passed = True

    if not reasons:
        reasons.append("CANONICAL_DAILY_CONTROLLER_EVIDENCE_VALID")

    return {
        "lifecycle_state": state,
        "lifecycle_passed": passed,
        "reason_codes": reasons,
        "controller_state": controller_state,
        "activation_state": activation_state,
        "qualification_state": qualification_state,
        "runtime_supervision_state": supervision_state,
        "runtime_supervision_score": as_float(controller.get("runtime_supervision_score"), 0.0),
        "master_cycle_state": master_cycle_state,
        "autonomous_daily_operations_authorized": authorized,
        "daily_paper_cycle_executed": cycle_executed,
        "safety_revocation_triggered": safety_revocation,
    }

def main(artifact: Dict[str, Any]) -> int:
    # Only phase369_controller_completion supplies an exact, digest-verified artifact.
    if not isinstance(artifact, dict) or not artifact.get("artifact_sha256"):
        raise RuntimeError("VERIFIED_CONTROLLER_COMPLETION_REQUIRED")
    business_date = artifact["business_date"]
    date.fromisoformat(business_date)
    portfolio_id = artifact["portfolio_id"]
    strategy_version = artifact["strategy_version"]

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

    controller = exact_date(
        sb,
        "paper_daily_autonomous_controller_v92",
        portfolio_id,
        "controller_date",
        business_date,
    )
    if controller is None:
        raise RuntimeError("Canonical Phase 3.6.8 controller evidence missing")

    for key in ("producer_run_id", "producer_run_attempt", "canonical_authority_hash", "controller_input_sha256", "source_evidence_sha256"):
        if str(controller.get(key) or "") != str(artifact.get(key) or ""):
            raise RuntimeError("CONTROLLER_ARTIFACT_DATABASE_AUTHORITY_MISMATCH")
    if (controller.get("evidence_sha256") != artifact["controller_evidence_sha256"]
            or controller.get("controller_state") != artifact["controller_state"]
            or controller.get("strategy_version") != strategy_version):
        raise RuntimeError("CONTROLLER_ARTIFACT_DATABASE_HASH_MISMATCH")

    master = exact_date(
        sb,
        "paper_master_cycles_v92",
        portfolio_id,
        "cycle_date",
        business_date,
    )
    if (str(controller.get("source_master_evidence_sha256") or "")
            != str((master or {}).get("evidence_sha256") or "")):
        raise RuntimeError("SAME_DATE_MASTER_SOURCE_HASH_MISMATCH")
    if controller.get("controller_passed") and master is None:
        raise RuntimeError("SAME_DATE_MASTER_CYCLE_MISSING")

    previous = latest_before(
        sb,
        "paper_daily_lifecycle_evidence_v92",
        portfolio_id,
        "evidence_date",
        business_date,
    )

    evaluation = evaluate(controller)
    previous_sha = str((previous or {}).get("evidence_sha256") or "GENESIS")
    lifecycle_sequence = as_int((previous or {}).get("lifecycle_sequence"), 0) + 1

    master_compact = compact_master(master)

    evidence_document = {
        "contract": CONTRACT,
        "portfolio_id": portfolio_id,
        "strategy_version": strategy_version,
        "evidence_date": business_date,
        "lifecycle_sequence": lifecycle_sequence,
        "previous_evidence_sha256": previous_sha,
        "controller": {
            "controller_state": evaluation["controller_state"],
            "activation_state": evaluation["activation_state"],
            "qualification_state": evaluation["qualification_state"],
            "runtime_supervision_state": evaluation["runtime_supervision_state"],
            "runtime_supervision_score": evaluation["runtime_supervision_score"],
            "master_cycle_state": evaluation["master_cycle_state"],
            "autonomous_daily_operations_authorized": evaluation["autonomous_daily_operations_authorized"],
            "daily_paper_cycle_executed": evaluation["daily_paper_cycle_executed"],
            "safety_revocation_triggered": evaluation["safety_revocation_triggered"],
        },
        "master": master_compact,
        "lifecycle_state": evaluation["lifecycle_state"],
        "lifecycle_passed": evaluation["lifecycle_passed"],
        "reason_codes": evaluation["reason_codes"],
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

    evidence_sha = stable_hash(evidence_document)

    payload = {
        "evidence_date": business_date,
        "portfolio_id": portfolio_id,
        "strategy_version": strategy_version,
        "contract": CONTRACT,
        "producer_run_id": artifact["producer_run_id"],
        "producer_run_attempt": int(artifact["producer_run_attempt"]),
        "canonical_authority_hash": artifact["canonical_authority_hash"],
        "controller_run_id": artifact["controller_run_id"],
        "controller_run_attempt": int(artifact["controller_run_attempt"]),

        "lifecycle_sequence": lifecycle_sequence,
        "lifecycle_state": evaluation["lifecycle_state"],
        "lifecycle_passed": evaluation["lifecycle_passed"],

        "controller_state": evaluation["controller_state"],
        "activation_state": evaluation["activation_state"],
        "qualification_state": evaluation["qualification_state"],
        "runtime_supervision_state": evaluation["runtime_supervision_state"],
        "runtime_supervision_score": evaluation["runtime_supervision_score"],
        "master_cycle_state": evaluation["master_cycle_state"],

        "autonomous_daily_operations_authorized": evaluation["autonomous_daily_operations_authorized"],
        "daily_paper_cycle_executed": evaluation["daily_paper_cycle_executed"],
        "safety_revocation_triggered": evaluation["safety_revocation_triggered"],

        "eligible_signals": master_compact.get("eligible_signals", 0),
        "sized_candidates": master_compact.get("sized_candidates", 0),
        "order_intents_created": master_compact.get("order_intents_created", 0),
        "simulated_fills_created": master_compact.get("simulated_fills_created", 0),
        "fills_settled": master_compact.get("fills_settled", 0),
        "cash": master_compact.get("cash", 0.0),
        "market_value": master_compact.get("market_value", 0.0),
        "nav": master_compact.get("nav", 0.0),
        "realized_pnl": master_compact.get("realized_pnl", 0.0),
        "unrealized_pnl": master_compact.get("unrealized_pnl", 0.0),
        "open_positions": master_compact.get("open_positions", 0),

        "previous_evidence_sha256": previous_sha,
        "source_controller_evidence_sha256": controller.get("evidence_sha256"),
        "source_master_evidence_sha256": master_compact.get("evidence_sha256"),
        "reason_codes": evaluation["reason_codes"],

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

    existing = exact_date(sb, "paper_daily_lifecycle_evidence_v92", portfolio_id, "evidence_date", business_date)
    if existing is not None:
        for key in ("producer_run_id", "producer_run_attempt", "canonical_authority_hash"):
            if str(existing.get(key) or "") != str(payload[key]):
                raise RuntimeError("SAME_DAY_LIFECYCLE_AUTHORITY_CONFLICT_OR_LEGACY_PROVENANCE")
        if (not existing.get("evidence_sha256") or not existing.get("lifecycle_state")
                or existing.get("source_controller_evidence_sha256") != payload["source_controller_evidence_sha256"]
                or existing.get("evidence_sha256") != evidence_sha):
            raise RuntimeError("SAME_AUTHORITY_LIFECYCLE_CONTENT_CONFLICT")
        audit_row = exact_date(sb, "paper_daily_lifecycle_evidence_audit_v92", portfolio_id,
                               "evidence_date", business_date)
        if (audit_row is None or audit_row.get("evidence_sha256") != evidence_sha
                or any(str(audit_row.get(k) or "") != str(payload[k]) for k in
                       ("producer_run_id", "producer_run_attempt", "canonical_authority_hash"))):
            raise RuntimeError("INCOMPLETE_LIFECYCLE_AUDIT_EVIDENCE")
        # An exact controller retry may have a distinct controller workflow run ID.
        # Content/authority is immutable; do not append another audit row.
        return 0
    sb.request("POST", "paper_daily_lifecycle_evidence_v92", payload=payload, prefer="return=minimal")

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_document
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_daily_lifecycle_evidence_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.9")
    print()
    print("## Production Paper Autonomous Daily Evidence + Lifecycle Governance Engine")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{portfolio_id}`")
    print(f"- Evidence Date: `{business_date}`")
    print(f"- Lifecycle Sequence: **{lifecycle_sequence}**")
    print(f"- Lifecycle State: **{evaluation['lifecycle_state']}**")
    print(f"- Lifecycle Passed: **{'YES' if evaluation['lifecycle_passed'] else 'NO'}**")
    print(f"- Controller State: **{evaluation['controller_state']}**")
    print(f"- Qualification State: **{evaluation['qualification_state']}**")
    print(f"- Activation State: **{evaluation['activation_state']}**")
    print(f"- Runtime Supervision: **{evaluation['runtime_supervision_state']}**")
    print(f"- Daily Master Cycle: **{evaluation['master_cycle_state']}**")
    print(f"- Autonomous Daily Operations Authorized: **{'YES' if evaluation['autonomous_daily_operations_authorized'] else 'NO'}**")
    print(f"- Daily Paper Cycle Executed: **{'YES' if evaluation['daily_paper_cycle_executed'] else 'NO'}**")
    print(f"- Safety Revocation Triggered: **{'YES' if evaluation['safety_revocation_triggered'] else 'NO'}**")
    print()
    print("## Daily Operating Evidence")
    print()
    print(f"- Eligible Signals: **{master_compact.get('eligible_signals', 0)}**")
    print(f"- Sized Candidates: **{master_compact.get('sized_candidates', 0)}**")
    print(f"- Order Intents: **{master_compact.get('order_intents_created', 0)}**")
    print(f"- Simulated Fills: **{master_compact.get('simulated_fills_created', 0)}**")
    print(f"- Fills Settled: **{master_compact.get('fills_settled', 0)}**")
    print(f"- NAV: **{master_compact.get('nav', 0.0):.2f}**")
    print(f"- Open Positions: **{master_compact.get('open_positions', 0)}**")
    print()
    print("## Lifecycle Reasons")
    print()
    for reason in evaluation["reason_codes"]:
        print(f"- `{reason}`")
    print()
    print("## Evidence Chain")
    print()
    print(f"- Previous Evidence SHA256: `{previous_sha}`")
    print(f"- Current Evidence SHA256: `{evidence_sha}`")
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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase369")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "daily_lifecycle_evidence.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "payload": payload,
                "evidence_document": evidence_document,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    # Governance FAIL_CLOSED is a valid safety outcome, not a software failure.
    return 0

if __name__ == "__main__":
    raise SystemExit("VERIFIED_CONTROLLER_COMPLETION_REQUIRED")
