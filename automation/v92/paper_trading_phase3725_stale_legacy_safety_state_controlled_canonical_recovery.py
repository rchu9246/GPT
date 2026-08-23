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
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE3725_STALE_LEGACY_SAFETY_STATE_CONTROLLED_CANONICAL_RECOVERY"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

REQUIRED_FORENSIC_CLASSIFICATION = "RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
RECOVERY_STATE = "RECOVERED_CONTINUE_ACTIVE"

SYSTEM_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "inserted_at",
    "modified_at",
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

    def insert(self, table: str, payload: Dict[str, Any]) -> None:
        self.request("POST", table, payload=payload, prefer="return=minimal")

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

def clone_for_new_supervision_row(
    previous: Dict[str, Any],
    recovery_date: str,
    evidence_sha: str,
) -> Dict[str, Any]:

    new_row = deepcopy(previous)

    for field in SYSTEM_FIELDS:
        new_row.pop(field, None)

    # Establish a NEW canonical state row. Never overwrite the previous REVOKED row.
    if "supervision_date" in new_row:
        new_row["supervision_date"] = recovery_date
    elif "run_date" in new_row:
        new_row["run_date"] = recovery_date
    else:
        raise RuntimeError("Supervision schema has no supervision_date/run_date column")

    # State compatibility.
    if "supervision_state" in new_row:
        new_row["supervision_state"] = "CONTINUE_ACTIVE"
    if "runtime_supervision_state" in new_row:
        new_row["runtime_supervision_state"] = "CONTINUE_ACTIVE"
    if "state" in new_row and str(new_row.get("state", "")).upper() in {
        "REVOKED", "FAIL_CLOSED", "STOP", "BLOCKED"
    }:
        new_row["state"] = "CONTINUE_ACTIVE"

    # Clear only stale/legacy revocation flags in the NEW row.
    for field in (
        "safety_revocation_triggered",
        "revoked",
        "is_revoked",
        "recovery_blocked",
    ):
        if field in new_row:
            new_row[field] = False

    # Preserve and enforce paper-only safety boundary.
    if "paper_only" in new_row:
        new_row["paper_only"] = True
    if "broker_api_used" in new_row:
        new_row["broker_api_used"] = False
    if "broker_credentials_used" in new_row:
        new_row["broker_credentials_used"] = False
    if "broker_order_submission_enabled" in new_row:
        new_row["broker_order_submission_enabled"] = False
    if "real_money_trading_enabled" in new_row:
        new_row["real_money_trading_enabled"] = False
    if "live_money_release_authorized" in new_row:
        new_row["live_money_release_authorized"] = False
    if "fail_closed_policy" in new_row:
        new_row["fail_closed_policy"] = True

    # Replace reason fields, when available, with an explicit controlled recovery marker.
    recovery_reasons = [
        "PHASE3725_CONTROLLED_CANONICAL_RECOVERY",
        "SOURCE_PHASE3724_RECOVERY_ELIGIBLE_STALE_OR_LEGACY",
        "HISTORICAL_REVOKED_ROW_PRESERVED",
        "PAPER_ONLY_RECOVERY",
    ]
    for field in (
        "reason_codes",
        "reasons",
        "revocation_reasons",
        "safety_reasons",
        "failure_reasons",
        "hard_failures",
    ):
        if field in new_row:
            new_row[field] = recovery_reasons

    if "evidence_sha256" in new_row:
        new_row["evidence_sha256"] = evidence_sha

    return new_row

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--recovery-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.recovery_date)

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

    forensic = latest(
        sb,
        "paper_true_safety_violation_forensics_v92",
        args.portfolio_id,
        "forensic_date",
    )
    if forensic is None:
        raise RuntimeError("Phase 3.7.2.4 forensic evidence missing")

    classification = str(forensic.get("classification") or "").upper()
    recovery_eligible = as_bool(forensic.get("recovery_eligible"), False)

    if classification != REQUIRED_FORENSIC_CLASSIFICATION:
        raise RuntimeError(
            f"Recovery blocked: forensic classification={classification!r}"
        )
    if not recovery_eligible:
        raise RuntimeError("Recovery blocked: recovery_eligible is false")

    # Re-verify immutable safety boundary from the forensic record.
    unsafe = []
    if not as_bool(forensic.get("paper_only"), True):
        unsafe.append("PAPER_ONLY_DISABLED")
    if as_bool(forensic.get("broker_api_used"), False):
        unsafe.append("BROKER_API_USED")
    if as_bool(forensic.get("broker_credentials_used"), False):
        unsafe.append("BROKER_CREDENTIALS_USED")
    if as_bool(forensic.get("broker_order_submission_enabled"), False):
        unsafe.append("BROKER_ORDER_SUBMISSION_ENABLED")
    if as_bool(forensic.get("real_money_trading_enabled"), False):
        unsafe.append("REAL_MONEY_TRADING_ENABLED")
    if as_bool(forensic.get("live_money_release_authorized"), False):
        unsafe.append("LIVE_MONEY_RELEASE_AUTHORIZED")
    if not as_bool(forensic.get("fail_closed_policy"), True):
        unsafe.append("FAIL_CLOSED_POLICY_DISABLED")

    current_violations = forensic.get("current_violations")
    if isinstance(current_violations, list) and current_violations:
        unsafe.extend(str(x) for x in current_violations)

    if unsafe:
        raise RuntimeError(
            "Recovery blocked by current unsafe facts: " + ", ".join(sorted(set(unsafe)))
        )

    supervision_table = (
        forensic.get("supervision_table")
        or "paper_runtime_supervision_state_v92"
    )

    previous = latest(
        sb,
        supervision_table,
        args.portfolio_id,
        "supervision_date",
    )
    if previous is None:
        raise RuntimeError("Current canonical supervision row missing")

    previous_state = str(
        previous.get("supervision_state")
        or previous.get("runtime_supervision_state")
        or previous.get("state")
        or "MISSING"
    ).upper()

    if previous_state not in {"REVOKED", "FAIL_CLOSED", "STOP", "BLOCKED"}:
        raise RuntimeError(
            f"Recovery not required: latest supervision state={previous_state}"
        )

    recovery_evidence = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "recovery_date": args.recovery_date,
        "forensic_evidence_sha256": forensic.get("evidence_sha256"),
        "forensic_classification": classification,
        "previous_supervision_evidence_sha256": previous.get("evidence_sha256"),
        "previous_supervision_state": previous_state,
        "target_supervision_state": "CONTINUE_ACTIVE",
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
    recovery_evidence_sha = stable_hash(recovery_evidence)

    new_supervision_row = clone_for_new_supervision_row(
        previous,
        args.recovery_date,
        recovery_evidence_sha,
    )

    authorization = {
        "recovery_date": args.recovery_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "forensic_classification": classification,
        "recovery_eligible": True,
        "recovery_state": RECOVERY_STATE,
        "previous_supervision_state": previous_state,
        "target_supervision_state": "CONTINUE_ACTIVE",
        "historical_rewrite_allowed": False,
        "forensic_evidence_sha256": forensic.get("evidence_sha256"),
        "previous_supervision_evidence_sha256": previous.get("evidence_sha256"),
        "recovery_evidence_sha256": recovery_evidence_sha,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write authorization evidence first.
    sb.upsert(
        "paper_stale_legacy_safety_recovery_authorization_v92",
        authorization,
        "portfolio_id,recovery_date",
    )

    # Append a NEW current-state row. Historical REVOKED row is untouched.
    sb.insert(supervision_table, new_supervision_row)

    audit = dict(authorization)
    audit["recovery_evidence"] = recovery_evidence
    audit["new_supervision_row_sha256"] = stable_hash(new_supervision_row)

    sb.insert(
        "paper_stale_legacy_safety_recovery_audit_v92",
        audit,
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.5")
    print()
    print("## Stale / Legacy Safety State Controlled Canonical Recovery")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Recovery Date: `{args.recovery_date}`")
    print(f"- Forensic Classification: **{classification}**")
    print("- Recovery Eligible: **YES**")
    print(f"- Recovery State: **{RECOVERY_STATE}**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical Recovery")
    print()
    print(f"- Runtime Supervision Table: **{supervision_table}**")
    print(f"- Previous Supervision State: **{previous_state}**")
    print("- New Supervision State: **CONTINUE_ACTIVE**")
    print("- Historical REVOKED Row Preserved: **YES**")
    print("- New Canonical Row Appended: **YES**")
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
    print("## Required Next Chain")
    print()
    print("- Re-run in this order:")
    print("  `Phase 3.6.8 -> Phase 3.6.9 -> Phase 3.7.0 -> Phase 3.7.1 -> Phase 3.7.2`")
    print("- Do not skip directly to Phase 3.7.2.")
    print("- Do not backfill observation days.")
    print(f"- Recovery Evidence SHA256: `{recovery_evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3725")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "controlled_canonical_recovery.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "authorization": authorization,
                "recovery_evidence": recovery_evidence,
                "new_supervision_row": new_supervision_row,
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
        print(f"PHASE3725_FATAL: {exc}", file=sys.stderr)
        raise