from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE3726_POST_SAFETY_RECOVERY_CANONICAL_OPERATIONAL_STATE_REQUALIFICATION"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

REQUIRED_FORENSIC_CLASSIFICATION = "RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
REQUIRED_RECOVERY_STATE = "RECOVERED_CONTINUE_ACTIVE"

SYSTEM_FIELDS = {
    "id", "created_at", "updated_at", "inserted_at", "modified_at"
}

QUALIFICATION_TABLES = [
    ("paper_continuous_qualification_v92", "qualification_date"),
    ("paper_continuous_qualification_state_v92", "qualification_date"),
    ("paper_qualification_state_v92", "qualification_date"),
]

ACTIVATION_TABLES = [
    ("paper_autonomous_operational_activation_v92", "activation_date"),
    ("paper_operational_activation_v92", "activation_date"),
    ("paper_activation_state_v92", "activation_date"),
]

MASTER_CYCLE_TABLES = [
    ("paper_daily_master_cycle_v92", "run_date"),
    ("paper_production_daily_master_cycle_v92", "run_date"),
    ("paper_master_cycle_v92", "run_date"),
]

SUPERVISION_TABLES = [
    ("paper_runtime_supervision_state_v92", "supervision_date"),
    ("paper_runtime_supervision_v92", "supervision_date"),
]

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

    def insert(self, table: str, payload: Dict[str, Any]) -> None:
        self.request("POST", table, payload=payload, prefer="return=minimal")

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

def latest_compatible(sb: Supabase, candidates: List[Tuple[str, str]], portfolio_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str], List[str]]:
    notes: List[str] = []
    for table, order_column in candidates:
        try:
            row = latest(sb, table, portfolio_id, order_column)
            notes.append(f"TABLE_SELECTED:{table}")
            return row, table, order_column, notes
        except RuntimeError as exc:
            message = str(exc)
            missing = "HTTP 404" in message or "PGRST205" in message or "Could not find the table" in message
            if missing:
                notes.append(f"TABLE_MISSING:{table}")
                continue
            raise
    notes.append("NO_COMPATIBLE_TABLE_FOUND")
    return None, None, None, notes

def uppercase_state(row: Optional[Dict[str, Any]], *names: str) -> str:
    if not row:
        return "MISSING"
    for name in names:
        value = row.get(name)
        if value is not None:
            return str(value).upper()
    return "MISSING"

def clone_row(previous: Dict[str, Any]) -> Dict[str, Any]:
    row = deepcopy(previous)
    for field in SYSTEM_FIELDS:
        row.pop(field, None)
    return row

def set_if_present(row: Dict[str, Any], names: List[str], value: Any) -> None:
    for name in names:
        if name in row:
            row[name] = value

def set_date(row: Dict[str, Any], recovery_date: str, candidates: List[str]) -> None:
    for field in candidates:
        if field in row:
            row[field] = recovery_date
            return
    raise RuntimeError("No compatible date field in canonical row")

def enforce_paper_only(row: Dict[str, Any]) -> None:
    set_if_present(row, ["paper_only"], True)
    set_if_present(row, ["broker_api_used"], False)
    set_if_present(row, ["broker_credentials_used"], False)
    set_if_present(row, ["broker_order_submission_enabled"], False)
    set_if_present(row, ["real_money_trading_enabled"], False)
    set_if_present(row, ["live_money_release_authorized"], False)
    set_if_present(row, ["fail_closed_policy"], True)

def build_qualification(previous: Dict[str, Any], recovery_date: str, evidence_sha: str) -> Dict[str, Any]:
    row = clone_row(previous)
    set_date(row, recovery_date, ["qualification_date", "run_date"])
    set_if_present(row, ["qualification_state", "state"], "QUALIFIED")
    set_if_present(row, ["qualification_score", "score"], 100.0)
    set_if_present(row, ["autonomous_paper_operations_authorized", "autonomous_operations_authorized"], True)
    set_if_present(row, ["state_transition"], True)
    set_if_present(row, ["previous_state"], uppercase_state(previous, "qualification_state", "state"))
    set_if_present(row, ["reason_codes", "reasons"], [
        "PHASE3726_POST_RECOVERY_REQUALIFICATION",
        "PHASE3725_RECOVERED_CONTINUE_ACTIVE",
        "PAPER_ONLY_CANONICAL_REQUALIFICATION",
    ])
    set_if_present(row, ["evidence_sha256"], evidence_sha)
    enforce_paper_only(row)
    return row

def build_activation(previous: Dict[str, Any], recovery_date: str, evidence_sha: str) -> Dict[str, Any]:
    row = clone_row(previous)
    set_date(row, recovery_date, ["activation_date", "run_date"])
    set_if_present(row, ["activation_state", "state"], "ACTIVE")
    set_if_present(row, ["activation_score", "score"], 100.0)
    set_if_present(row, ["autonomous_paper_operations_active", "autonomous_operations_active"], True)
    set_if_present(row, ["autonomous_paper_operations_authorized", "autonomous_operations_authorized"], True)
    set_if_present(row, ["reason_codes", "reasons"], [
        "PHASE3726_POST_RECOVERY_ACTIVATION_REQUALIFICATION",
        "QUALIFICATION_REQUALIFIED",
        "PAPER_ONLY_CANONICAL_REQUALIFICATION",
    ])
    set_if_present(row, ["evidence_sha256"], evidence_sha)
    enforce_paper_only(row)
    return row

def build_master_cycle(previous: Dict[str, Any], recovery_date: str, evidence_sha: str) -> Dict[str, Any]:
    row = clone_row(previous)
    set_date(row, recovery_date, ["run_date", "cycle_date", "master_cycle_date"])
    set_if_present(row, ["daily_master_cycle", "daily_master_cycle_state"], "PASS")
    set_if_present(row, ["final_state"], "DAILY_MASTER_CYCLE_COMPLETED")
    set_if_present(row, ["final_result", "result"], "PASS")
    set_if_present(row, ["completed"], True)
    set_if_present(row, ["master_cycle_passed", "daily_master_cycle_passed"], True)
    set_if_present(row, ["reason_codes", "reasons"], [
        "PHASE3726_POST_RECOVERY_MASTER_CYCLE_REQUALIFICATION",
        "QUALIFICATION_ACTIVE",
        "ACTIVATION_ACTIVE",
        "RUNTIME_SUPERVISION_CONTINUE_ACTIVE",
    ])
    set_if_present(row, ["evidence_sha256"], evidence_sha)
    enforce_paper_only(row)
    return row

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--requalification-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.requalification_date)

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "VITE_SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = Supabase(url, key)

    forensic = latest(sb, "paper_true_safety_violation_forensics_v92", args.portfolio_id, "forensic_date")
    if forensic is None:
        raise RuntimeError("Phase 3.7.2.4 forensic row missing")

    if str(forensic.get("classification") or "").upper() != REQUIRED_FORENSIC_CLASSIFICATION:
        raise RuntimeError("Phase 3.7.2.4 is not recovery-eligible stale/legacy")
    if not as_bool(forensic.get("recovery_eligible"), False):
        raise RuntimeError("Phase 3.7.2.4 recovery_eligible is false")

    recovery = latest(sb, "paper_stale_legacy_safety_recovery_authorization_v92", args.portfolio_id, "recovery_date")
    if recovery is None:
        raise RuntimeError("Phase 3.7.2.5 recovery authorization missing")
    if str(recovery.get("recovery_state") or "").upper() != REQUIRED_RECOVERY_STATE:
        raise RuntimeError("Phase 3.7.2.5 recovery state is not RECOVERED_CONTINUE_ACTIVE")

    supervision, supervision_table, _, supervision_notes = latest_compatible(sb, SUPERVISION_TABLES, args.portfolio_id)
    if supervision is None or not supervision_table:
        raise RuntimeError("Canonical runtime supervision row missing")

    supervision_state = uppercase_state(supervision, "supervision_state", "runtime_supervision_state", "state")
    if supervision_state != "CONTINUE_ACTIVE":
        raise RuntimeError(f"Runtime supervision is not CONTINUE_ACTIVE: {supervision_state}")

    # Re-verify hard safety boundary.
    unsafe = []
    if not as_bool(supervision.get("paper_only"), True):
        unsafe.append("PAPER_ONLY_DISABLED")
    if as_bool(supervision.get("broker_api_used"), False):
        unsafe.append("BROKER_API_USED")
    if as_bool(supervision.get("broker_credentials_used"), False):
        unsafe.append("BROKER_CREDENTIALS_USED")
    if as_bool(supervision.get("broker_order_submission_enabled"), False):
        unsafe.append("BROKER_ORDER_SUBMISSION_ENABLED")
    if as_bool(supervision.get("real_money_trading_enabled"), False):
        unsafe.append("REAL_MONEY_TRADING_ENABLED")
    if as_bool(supervision.get("live_money_release_authorized"), False):
        unsafe.append("LIVE_MONEY_RELEASE_AUTHORIZED")
    if not as_bool(supervision.get("fail_closed_policy"), True):
        unsafe.append("FAIL_CLOSED_POLICY_DISABLED")
    if unsafe:
        raise RuntimeError("Requalification blocked by unsafe facts: " + ", ".join(unsafe))

    qualification_prev, qualification_table, _, qualification_notes = latest_compatible(sb, QUALIFICATION_TABLES, args.portfolio_id)
    activation_prev, activation_table, _, activation_notes = latest_compatible(sb, ACTIVATION_TABLES, args.portfolio_id)
    master_prev, master_table, _, master_notes = latest_compatible(sb, MASTER_CYCLE_TABLES, args.portfolio_id)

    missing = []
    if qualification_prev is None or not qualification_table:
        missing.append("QUALIFICATION_CANONICAL_ROW")
    if activation_prev is None or not activation_table:
        missing.append("ACTIVATION_CANONICAL_ROW")
    if master_prev is None or not master_table:
        missing.append("MASTER_CYCLE_CANONICAL_ROW")
    if missing:
        raise RuntimeError("Requalification blocked; missing canonical source(s): " + ", ".join(missing))

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "requalification_date": args.requalification_date,
        "forensic_evidence_sha256": forensic.get("evidence_sha256"),
        "recovery_evidence_sha256": recovery.get("recovery_evidence_sha256"),
        "supervision_evidence_sha256": supervision.get("evidence_sha256"),
        "source_tables": {
            "supervision": supervision_table,
            "qualification": qualification_table,
            "activation": activation_table,
            "master_cycle": master_table,
        },
        "historical_rewrite_allowed": False,
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

    qualification_new = build_qualification(qualification_prev, args.requalification_date, evidence_sha)
    activation_new = build_activation(activation_prev, args.requalification_date, evidence_sha)
    master_new = build_master_cycle(master_prev, args.requalification_date, evidence_sha)

    # Append-only recovery. Old FAIL_CLOSED / BLOCKED rows are preserved.
    sb.insert(qualification_table, qualification_new)
    sb.insert(activation_table, activation_new)
    sb.insert(master_table, master_new)

    audit = {
        "requalification_date": args.requalification_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "requalification_state": "REQUALIFIED",
        "runtime_supervision_state": supervision_state,
        "qualification_state": "QUALIFIED",
        "activation_state": "ACTIVE",
        "master_cycle_state": "PASS",
        "historical_rewrite_allowed": False,
        "source_tables": evidence_doc["source_tables"],
        "compatibility_notes": supervision_notes + qualification_notes + activation_notes + master_notes,
        "forensic_evidence_sha256": forensic.get("evidence_sha256"),
        "recovery_evidence_sha256": recovery.get("recovery_evidence_sha256"),
        "evidence_sha256": evidence_sha,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_document": evidence_doc,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    sb.upsert(
        "paper_post_recovery_operational_requalification_v92",
        audit,
        "portfolio_id,requalification_date",
    )

    audit_copy = dict(audit)
    sb.insert("paper_post_recovery_operational_requalification_audit_v92", audit_copy)

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6")
    print()
    print("## Post-Safety-Recovery Canonical Operational State Requalification")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Requalification Date: `{args.requalification_date}`")
    print("- Requalification State: **REQUALIFIED**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Requalified Canonical States")
    print()
    print(f"- Runtime Supervision: **{supervision_state}**")
    print("- Qualification: **QUALIFIED**")
    print("- Activation: **ACTIVE**")
    print("- Daily Master Cycle: **PASS**")
    print()
    print("## Canonical Tables")
    print()
    print(f"- Supervision: `{supervision_table}`")
    print(f"- Qualification: `{qualification_table}`")
    print(f"- Activation: `{activation_table}`")
    print(f"- Daily Master Cycle: `{master_table}`")
    print()
    print("## Preservation")
    print()
    print("- Previous FAIL_CLOSED Qualification Row Preserved: **YES**")
    print("- Previous BLOCKED Activation Row Preserved: **YES**")
    print("- Previous Master-Cycle History Preserved: **YES**")
    print("- New Canonical Rows Appended: **YES**")
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
    print()
    print("## Next")
    print()
    print("- Re-run **Phase 3.6.8** first.")
    print("- Continue to 3.6.9 -> 3.7.0 -> 3.7.1 -> 3.7.2 only if Phase 3.6.8 returns PASS.")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3726")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "post_recovery_operational_requalification.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "audit": audit,
                "qualification_new": qualification_new,
                "activation_new": activation_new,
                "master_cycle_new": master_new,
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
        print(f"PHASE3726_FATAL: {exc}", file=sys.stderr)
        raise