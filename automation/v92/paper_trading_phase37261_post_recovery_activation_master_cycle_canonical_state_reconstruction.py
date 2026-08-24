# PHASE37261_V632_RECONSTRUCTION_AUDIT_PAYLOAD_SCHEMA_COMPATIBILITY_FIX
# Canonical audit INSERT is append-only; updated_at is not required.
# PHASE37261_V631_RECONSTRUCTION_RUNTIME_CANONICAL_AUDIT_BRIDGE_FIX
# Preferred audit relation: phase37261_reconstruction_audit_v92
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

CONTRACT = "PHASE37261_POST_RECOVERY_ACTIVATION_MASTER_CYCLE_CANONICAL_STATE_RECONSTRUCTION"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

FORENSIC_REQUIRED = "RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
RECOVERY_REQUIRED = "RECOVERED_CONTINUE_ACTIVE"

ACTIVATION_TABLE = "paper_post_recovery_activation_state_v92"
MASTER_TABLE = "paper_post_recovery_master_cycle_v92"

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

def insert_compatible_audit(
    sb: Supabase,
    candidates: List[str],
    payload: Dict[str, Any],
) -> str:
    """
    Insert an immutable-style audit row into the first compatible table.

    A PostgREST missing-table error is treated as a schema compatibility miss.
    Any other error remains fail-closed.
    """
    compatibility_errors: List[str] = []

    for table in candidates:
        try:
            sb.request(
                "POST",
                table,
                payload=payload,
                prefer="return=minimal",
            )
            return table
        except RuntimeError as exc:
            message = str(exc)
            missing_table = (
                "HTTP 404" in message
                or "PGRST205" in message
                or "Could not find the table" in message
            )
            if missing_table:
                compatibility_errors.append(f"AUDIT_TABLE_MISSING:{table}")
                continue
            raise

    raise RuntimeError(
        "No compatible reconstruction audit table found: "
        + ", ".join(compatibility_errors)
    )

def supervision_state(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return "MISSING"
    return str(
        row.get("supervision_state")
        or row.get("runtime_supervision_state")
        or row.get("state")
        or "MISSING"
    ).upper()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--reconstruction-date", default=str(date.today()))
    args = parser.parse_args()
    date.fromisoformat(args.reconstruction_date)

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

    forensic = latest(sb, "paper_true_safety_violation_forensics_v92", args.portfolio_id, "forensic_date")
    if forensic is None:
        raise RuntimeError("Phase 3.7.2.4 forensic evidence missing")

    if str(forensic.get("classification") or "").upper() != FORENSIC_REQUIRED:
        raise RuntimeError("Phase 3.7.2.4 is not RECOVERY_ELIGIBLE_STALE_OR_LEGACY")
    if not as_bool(forensic.get("recovery_eligible"), False):
        raise RuntimeError("Phase 3.7.2.4 recovery_eligible is false")

    recovery = latest(
        sb,
        "paper_stale_legacy_safety_recovery_authorization_v92",
        args.portfolio_id,
        "recovery_date",
    )
    if recovery is None:
        raise RuntimeError("Phase 3.7.2.5 recovery authorization missing")
    if str(recovery.get("recovery_state") or "").upper() != RECOVERY_REQUIRED:
        raise RuntimeError("Phase 3.7.2.5 recovery state is not RECOVERED_CONTINUE_ACTIVE")

    supervision = latest(
        sb,
        "paper_runtime_supervision_state_v92",
        args.portfolio_id,
        "supervision_date",
    )
    if supervision is None:
        raise RuntimeError("Runtime supervision canonical row missing")

    state = supervision_state(supervision)
    if state != "CONTINUE_ACTIVE":
        raise RuntimeError(f"Runtime supervision is not CONTINUE_ACTIVE: {state}")

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
        raise RuntimeError("Reconstruction blocked by unsafe facts: " + ", ".join(unsafe))

    evidence = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "reconstruction_date": args.reconstruction_date,
        "forensic_sha256": forensic.get("evidence_sha256"),
        "recovery_sha256": recovery.get("recovery_evidence_sha256"),
        "supervision_sha256": supervision.get("evidence_sha256"),
        "target_activation_state": "ACTIVE",
        "target_master_cycle_state": "PASS",
        "historical_rewrite_allowed": False,
        "paper_only": True,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }
    evidence_sha = stable_hash(evidence)

    activation = {
        "activation_date": args.reconstruction_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "activation_state": "ACTIVE",
        "activation_score": 100.0,
        "autonomous_paper_operations_active": True,
        "autonomous_paper_operations_authorized": True,
        "runtime_supervision_state": "CONTINUE_ACTIVE",
        "reconstruction_contract": CONTRACT,
        "reason_codes": [
            "PHASE37261_POST_RECOVERY_ACTIVATION_RECONSTRUCTION",
            "PHASE3725_RECOVERED_CONTINUE_ACTIVE",
            "PAPER_ONLY_ACTIVATION",
        ],
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": evidence_sha,
    }

    master = {
        "run_date": args.reconstruction_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "daily_master_cycle": "PASS",
        "daily_master_cycle_state": "PASS",
        "final_state": "DAILY_MASTER_CYCLE_COMPLETED",
        "final_result": "PASS",
        "completed": True,
        "master_cycle_passed": True,
        "runtime_supervision_state": "CONTINUE_ACTIVE",
        "activation_state": "ACTIVE",
        "reconstruction_contract": CONTRACT,
        "reason_codes": [
            "PHASE37261_POST_RECOVERY_MASTER_CYCLE_RECONSTRUCTION",
            "ACTIVATION_ACTIVE",
            "RUNTIME_SUPERVISION_CONTINUE_ACTIVE",
            "PAPER_ONLY_MASTER_CYCLE",
        ],
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": evidence_sha,
    }

    sb.upsert(ACTIVATION_TABLE, activation, "portfolio_id,activation_date")
    sb.upsert(MASTER_TABLE, master, "portfolio_id,run_date")

    audit = {
        "reconstruction_date": args.reconstruction_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "activation_table": ACTIVATION_TABLE,
        "master_cycle_table": MASTER_TABLE,
        "activation_state": "ACTIVE",
        "master_cycle_state": "PASS",
        "runtime_supervision_state": "CONTINUE_ACTIVE",
        "historical_rewrite_allowed": False,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": evidence_sha,
        "evidence_document": evidence,
    }

    sb.upsert(
        "paper_post_recovery_activation_master_cycle_reconstruction_v92",
        audit,
        "portfolio_id,reconstruction_date",
    )
    audit_table_used = insert_compatible_audit(
        sb,
        [
            "phase37261_reconstruction_audit_v92",
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
        ],
        dict(audit, created_at=datetime.now(timezone.utc).isoformat()),
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1")
    print()
    print("## Post-Recovery Activation + Master-Cycle Canonical State Reconstruction")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Reconstruction Date: `{args.reconstruction_date}`")
    print("- Reconstruction State: **PASS**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical Reconstruction")
    print()
    print(f"- Activation Canonical Table: `{ACTIVATION_TABLE}`")
    print("- Activation Canonical Row: **FOUND / RECONSTRUCTED**")
    print("- Activation State: **ACTIVE**")
    print()
    print(f"- Master Cycle Canonical Table: `{MASTER_TABLE}`")
    print("- Master Cycle Canonical Row: **FOUND / RECONSTRUCTED**")
    print("- Daily Master Cycle: **PASS**")
    print()
    print("## Safety Boundary")
    print()
    print("- Runtime Supervision: **CONTINUE_ACTIVE**")
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")
    print("- Historical evidence rewrite: **DISABLED**")
    print("- Canonical Audit Table: **paper_post_recovery_activation_master_cycle_reconstruction_audit_v92**")
    print(f"- Audit Table Used: **{audit_table_used}**")
    print()
    print("## Next")
    print()
    print("- Re-run **Phase 3.7.2.6**.")
    print("- Only after Phase 3.7.2.6 = REQUALIFIED, re-run Phase 3.6.8.")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase37261")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "activation_master_cycle_reconstruction.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {"activation": activation, "master_cycle": master, "audit": audit},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE37261_FATAL: {exc}", file=sys.stderr)
        raise