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
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE3724_TRUE_SAFETY_VIOLATION_EVIDENCE_FORENSICS_AND_RECOVERY_ELIGIBILITY"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

RECOVERY_ELIGIBLE = "RECOVERY_ELIGIBLE_STALE_OR_LEGACY"
RECOVERY_BLOCKED_TRUE = "RECOVERY_BLOCKED_TRUE_CURRENT_VIOLATION"
RECOVERY_BLOCKED_EVIDENCE = "RECOVERY_BLOCKED_INSUFFICIENT_EVIDENCE"
NO_ACTIVE_VIOLATION = "NO_ACTIVE_VIOLATION"

TRUE_UNSAFE_TOKENS = {
    "BROKER_API_USED",
    "BROKER_CREDENTIALS_USED",
    "BROKER_ORDER_SUBMISSION_ENABLED",
    "REAL_MONEY_TRADING_ENABLED",
    "LIVE_MONEY_RELEASE_AUTHORIZED",
    "PAPER_ONLY_DISABLED",
    "FAIL_CLOSED_POLICY_DISABLED",
    "EVIDENCE_CHAIN_BREAK",
    "UNAUTHORIZED_ORDER",
    "DRAWDOWN_LIMIT_EXCEEDED",
    "SAFETY_VIOLATION",
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

def latest_compatible(
    sb: Supabase,
    candidates: List[Tuple[str, str]],
    portfolio_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], List[str]]:
    notes: List[str] = []
    for table, order_column in candidates:
        try:
            row = latest(sb, table, portfolio_id, order_column)
            notes.append(f"TABLE_SELECTED:{table}")
            return row, table, notes
        except RuntimeError as exc:
            msg = str(exc)
            if "HTTP 404" in msg or "PGRST205" in msg or "Could not find the table" in msg:
                notes.append(f"TABLE_MISSING:{table}")
                continue
            raise
    notes.append("NO_COMPATIBLE_TABLE_FOUND")
    return None, None, notes

def row_date(row: Optional[Dict[str, Any]], *names: str) -> Optional[str]:
    if not row:
        return None
    for name in names:
        value = row.get(name)
        if value:
            return str(value)[:10]
    return None

def state(row: Optional[Dict[str, Any]], *names: str, default: str = "MISSING") -> str:
    if not row:
        return default
    for name in names:
        if name in row and row.get(name) is not None:
            return str(row.get(name)).upper()
    return default

def reason_list(row: Optional[Dict[str, Any]]) -> List[str]:
    if not row:
        return []
    result: List[str] = []
    for field in (
        "reason_codes",
        "reasons",
        "revocation_reasons",
        "safety_reasons",
        "failure_reasons",
        "hard_failures",
        "notes",
    ):
        value = row.get(field)
        if value is None:
            continue
        if isinstance(value, list):
            result.extend(str(x) for x in value)
        elif isinstance(value, dict):
            result.extend(f"{k}:{v}" for k, v in value.items())
        else:
            result.append(str(value))
    return result

def bool_fact(row: Optional[Dict[str, Any]], names: List[str], default: bool) -> bool:
    if not row:
        return default
    for name in names:
        if name in row:
            return as_bool(row.get(name), default)
    return default

def sha(row: Optional[Dict[str, Any]]) -> Optional[str]:
    if not row:
        return None
    return row.get("evidence_sha256") or row.get("evidence_hash") or row.get("sha256")

def forensic_classify(
    supervision: Optional[Dict[str, Any]],
    controller: Optional[Dict[str, Any]],
    lifecycle: Optional[Dict[str, Any]],
    diagnostic: Optional[Dict[str, Any]],
    reconciliation: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    reasons: List[str] = []
    current_violations: List[str] = []
    stale_or_legacy_indicators: List[str] = []
    evidence_gaps: List[str] = []

    supervision_state = state(supervision, "supervision_state", "runtime_supervision_state", "state")
    controller_state = state(controller, "controller_state")
    lifecycle_state = state(lifecycle, "lifecycle_state")
    reconciliation_class = state(reconciliation, "classification")

    paper_only = bool_fact(supervision, ["paper_only"], True)
    broker_api_used = bool_fact(supervision, ["broker_api_used"], False)
    broker_credentials_used = bool_fact(supervision, ["broker_credentials_used"], False)
    broker_submission_enabled = bool_fact(
        supervision,
        ["broker_order_submission_enabled", "broker_order_submission"],
        False,
    )
    real_money_enabled = bool_fact(
        supervision,
        ["real_money_trading_enabled", "real_money_trading"],
        False,
    )
    live_release = bool_fact(supervision, ["live_money_release_authorized"], False)
    fail_closed_policy = bool_fact(supervision, ["fail_closed_policy"], True)

    if not paper_only:
        current_violations.append("PAPER_ONLY_DISABLED")
    if broker_api_used:
        current_violations.append("BROKER_API_USED")
    if broker_credentials_used:
        current_violations.append("BROKER_CREDENTIALS_USED")
    if broker_submission_enabled:
        current_violations.append("BROKER_ORDER_SUBMISSION_ENABLED")
    if real_money_enabled:
        current_violations.append("REAL_MONEY_TRADING_ENABLED")
    if live_release:
        current_violations.append("LIVE_MONEY_RELEASE_AUTHORIZED")
    if not fail_closed_policy:
        current_violations.append("FAIL_CLOSED_POLICY_DISABLED")

    combined_reason_text = " | ".join(
        reason_list(supervision)
        + reason_list(controller)
        + reason_list(lifecycle)
        + reason_list(diagnostic)
        + reason_list(reconciliation)
    ).upper()

    for token in sorted(TRUE_UNSAFE_TOKENS):
        if token in combined_reason_text:
            current_violations.append(f"EXPLICIT_REASON:{token}")

    dates = {
        "supervision": row_date(supervision, "supervision_date", "run_date", "created_at"),
        "controller": row_date(controller, "controller_date", "run_date", "created_at"),
        "lifecycle": row_date(lifecycle, "evidence_date", "run_date", "created_at"),
        "diagnostic": row_date(diagnostic, "diagnostic_date", "created_at"),
        "reconciliation": row_date(reconciliation, "reconciliation_date", "created_at"),
    }

    source_dates = [dates[k] for k in ("supervision", "controller", "lifecycle") if dates[k]]
    newest_source_date = max(source_dates) if source_dates else None

    if newest_source_date:
        for key in ("supervision", "controller", "lifecycle"):
            d = dates[key]
            if d and d != newest_source_date:
                stale_or_legacy_indicators.append(
                    f"{key.upper()}_DATE_MISMATCH:{d}!={newest_source_date}"
                )

    if reconciliation_class == "TRUE_SAFETY_VIOLATION" and not current_violations:
        stale_or_legacy_indicators.append(
            "PRIOR_TRUE_SAFETY_CLASSIFICATION_WITHOUT_CURRENT_EXPLICIT_UNSAFE_FACT"
        )

    if supervision_state == "REVOKED" and not current_violations:
        stale_or_legacy_indicators.append(
            "REVOKED_STATE_WITHOUT_CURRENT_EXPLICIT_UNSAFE_FACT"
        )

    if controller_state == "FAIL_CLOSED" and supervision_state == "REVOKED" and not current_violations:
        stale_or_legacy_indicators.append(
            "DOWNSTREAM_FAIL_CLOSED_PROPAGATED_FROM_REVOKED_SUPERVISION"
        )

    if not supervision:
        evidence_gaps.append("SUPERVISION_ROW_MISSING")
    if not controller:
        evidence_gaps.append("CONTROLLER_ROW_MISSING")
    if not lifecycle:
        evidence_gaps.append("LIFECYCLE_ROW_MISSING")
    if not diagnostic:
        evidence_gaps.append("PHASE3722_DIAGNOSTIC_ROW_MISSING")
    if not reconciliation:
        evidence_gaps.append("PHASE3723_RECONCILIATION_ROW_MISSING")

    hashes = {
        "supervision": sha(supervision),
        "controller": sha(controller),
        "lifecycle": sha(lifecycle),
        "diagnostic": sha(diagnostic),
        "reconciliation": sha(reconciliation),
    }

    for key, value in hashes.items():
        if not value:
            evidence_gaps.append(f"{key.upper()}_EVIDENCE_SHA_MISSING")

    if current_violations:
        classification = RECOVERY_BLOCKED_TRUE
        recovery_eligible = False
        reasons.extend(sorted(set(current_violations)))
    elif evidence_gaps:
        classification = RECOVERY_BLOCKED_EVIDENCE
        recovery_eligible = False
        reasons.extend(sorted(set(evidence_gaps)))
        reasons.extend(sorted(set(stale_or_legacy_indicators)))
    elif supervision_state != "REVOKED":
        classification = NO_ACTIVE_VIOLATION
        recovery_eligible = False
        reasons.append("LATEST_SUPERVISION_NOT_REVOKED")
    elif stale_or_legacy_indicators:
        classification = RECOVERY_ELIGIBLE
        recovery_eligible = True
        reasons.extend(sorted(set(stale_or_legacy_indicators)))
    else:
        classification = RECOVERY_BLOCKED_EVIDENCE
        recovery_eligible = False
        reasons.append("REVOCATION_PRESENT_WITHOUT_PROVABLE_RECOVERY_BASIS")

    return {
        "classification": classification,
        "recovery_eligible": recovery_eligible,
        "historical_rewrite_allowed": False,
        "supervision_state": supervision_state,
        "controller_state": controller_state,
        "lifecycle_state": lifecycle_state,
        "reconciliation_class": reconciliation_class,
        "dates": dates,
        "hashes": hashes,
        "current_violations": sorted(set(current_violations)),
        "stale_or_legacy_indicators": sorted(set(stale_or_legacy_indicators)),
        "evidence_gaps": sorted(set(evidence_gaps)),
        "reason_codes": reasons,
        "safety_facts": {
            "paper_only": paper_only,
            "broker_api_used": broker_api_used,
            "broker_credentials_used": broker_credentials_used,
            "broker_order_submission_enabled": broker_submission_enabled,
            "real_money_trading_enabled": real_money_enabled,
            "live_money_release_authorized": live_release,
            "fail_closed_policy": fail_closed_policy,
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--forensic-date", default=str(date.today()))
    args = parser.parse_args()

    date.fromisoformat(args.forensic_date)

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

    supervision, supervision_table, supervision_notes = latest_compatible(
        sb,
        [
            ("paper_runtime_supervision_state_v92", "supervision_date"),
            ("paper_runtime_supervision_v92", "supervision_date"),
        ],
        args.portfolio_id,
    )

    controller = latest(
        sb,
        "paper_daily_autonomous_controller_v92",
        args.portfolio_id,
        "controller_date",
    )
    lifecycle = latest(
        sb,
        "paper_daily_lifecycle_evidence_v92",
        args.portfolio_id,
        "evidence_date",
    )
    diagnostic = latest(
        sb,
        "paper_observation_fail_closed_diagnostic_v92",
        args.portfolio_id,
        "diagnostic_date",
    )
    reconciliation = latest(
        sb,
        "paper_true_safety_revocation_reconciliation_v92",
        args.portfolio_id,
        "reconciliation_date",
    )

    result = forensic_classify(
        supervision,
        controller,
        lifecycle,
        diagnostic,
        reconciliation,
    )
    result["supervision_table"] = supervision_table
    result["supervision_compatibility_notes"] = supervision_notes
    result["reason_codes"].extend(supervision_notes)

    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "forensic_date": args.forensic_date,
        "result": result,
        "safety": {
            "paper_only": True,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "historical_rewrite_allowed": False,
            "fail_closed_policy": True,
        },
    }
    evidence_sha = stable_hash(evidence_doc)

    payload = {
        "forensic_date": args.forensic_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "classification": result["classification"],
        "recovery_eligible": result["recovery_eligible"],
        "historical_rewrite_allowed": False,

        "supervision_table": result["supervision_table"],
        "supervision_state": result["supervision_state"],
        "controller_state": result["controller_state"],
        "lifecycle_state": result["lifecycle_state"],
        "prior_reconciliation_class": result["reconciliation_class"],

        "supervision_date": result["dates"]["supervision"],
        "controller_date": result["dates"]["controller"],
        "lifecycle_date": result["dates"]["lifecycle"],
        "diagnostic_date": result["dates"]["diagnostic"],
        "reconciliation_date": result["dates"]["reconciliation"],

        "current_violations": result["current_violations"],
        "stale_or_legacy_indicators": result["stale_or_legacy_indicators"],
        "evidence_gaps": result["evidence_gaps"],
        "reason_codes": result["reason_codes"],

        "source_hashes": result["hashes"],

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
        "paper_true_safety_violation_forensics_v92",
        payload,
        "portfolio_id,forensic_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_true_safety_violation_forensics_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.4")
    print()
    print("## True Safety Violation Evidence Forensics + Recovery Eligibility")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Forensic Date: `{args.forensic_date}`")
    print(f"- Classification: **{result['classification']}**")
    print(f"- Recovery Eligible: **{'YES' if result['recovery_eligible'] else 'NO'}**")
    print("- Historical Rewrite Allowed: **NO**")
    print()
    print("## Canonical Evidence Sources")
    print()
    print(f"- Runtime Supervision Table: **{result['supervision_table'] or 'NOT_FOUND'}**")
    print(f"- Supervision: **{result['supervision_state']}** (date `{result['dates']['supervision'] or 'MISSING'}`)")
    print(f"- Controller: **{result['controller_state']}** (date `{result['dates']['controller'] or 'MISSING'}`)")
    print(f"- Lifecycle: **{result['lifecycle_state']}** (date `{result['dates']['lifecycle'] or 'MISSING'}`)")
    print(f"- Prior Reconciliation: **{result['reconciliation_class']}**")
    print()
    print("## Current Unsafe Facts")
    print()
    if result["current_violations"]:
        for item in result["current_violations"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Stale / Legacy Indicators")
    print()
    if result["stale_or_legacy_indicators"]:
        for item in result["stale_or_legacy_indicators"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Evidence Gaps")
    print()
    if result["evidence_gaps"]:
        for item in result["evidence_gaps"]:
            print(f"- `{item}`")
    else:
        print("- `NONE_DETECTED`")
    print()
    print("## Recovery Instruction")
    print()
    if result["classification"] == RECOVERY_ELIGIBLE:
        print("- **RECOVERY ELIGIBLE:** stale/legacy revocation is sufficiently evidenced.")
        print("- Do not edit historical rows.")
        print("- Next phase may perform controlled canonical recovery and then re-run:")
        print("  `3.6.7 -> 3.6.8 -> 3.6.9 -> 3.7.0 -> 3.7.1 -> 3.7.2`")
    elif result["classification"] == RECOVERY_BLOCKED_TRUE:
        print("- **RECOVERY BLOCKED:** current unsafe fact(s) still exist.")
        print("- Resolve the actual safety condition before any recovery attempt.")
    elif result["classification"] == RECOVERY_BLOCKED_EVIDENCE:
        print("- **RECOVERY BLOCKED:** evidence is insufficient to prove a safe recovery.")
        print("- Keep fail-closed and inspect the listed evidence gaps.")
    else:
        print("- Latest supervision is not actively revoked; no special recovery is required.")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Historical evidence rewrite: **DISABLED**")
    print("- Fail-closed policy: **ENABLED**")
    print(f"- Evidence SHA256: `{evidence_sha}`")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3724")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "true_safety_violation_forensics.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {"payload": payload, "evidence_document": evidence_doc},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3724_FATAL: {exc}", file=sys.stderr)
        raise