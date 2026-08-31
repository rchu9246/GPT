#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE379_PRODUCTION_PAPER_QUALIFICATION_STATE_RECONCILIATION_AUTOMATIC_PROMOTION_READINESS"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

PHASE375_RESULT_PATH = Path(os.getenv("PHASE375_RESULT_PATH", "artifacts/phase379/input/phase375_result.json"))
PHASE376_RESULT_PATH = Path(os.getenv("PHASE376_RESULT_PATH", "artifacts/phase379/input/phase376_result.json"))

TARGET_TABLE = "paper_production_promotion_readiness_v92"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False

def env_first(*names: str) -> Optional[str]:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

def request(method: str, path: str, body: Optional[Any] = None, prefer: str = "") -> Any:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e

def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def b(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE", "YES", "Y", "1", "PASS", "ENABLED"}

def digest(payload: Dict[str, Any]) -> str:
    stable = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()

def main() -> int:
    art = Path("artifacts/phase379")
    art.mkdir(parents=True, exist_ok=True)

    p375 = load_json(PHASE375_RESULT_PATH)
    p376 = load_json(PHASE376_RESULT_PATH)

    blockers: List[str] = []

    p375_present = bool(p375)
    p376_present = bool(p376)

    p375_state = str(p375.get("state", "")).strip().upper()
    p375_qualified = b(p375.get("qualified", False))
    p375_operational = b(p375.get("operational", False))

    p375_checks = p375.get("checks", {}) if isinstance(p375.get("checks"), dict) else {}
    p375_counts = p375.get("evidence_counts", {}) if isinstance(p375.get("evidence_counts"), dict) else {}

    runtime_pass = str(p375_checks.get("runtime_supervision", "")).upper() == "PASS"
    observed = int(p375_counts.get("observed", 0) or 0)
    valid = int(p375_counts.get("valid", 0) or 0)
    blocked = int(p375_counts.get("blocked", 0) or 0)

    p376_state = str(p376.get("state", "")).strip().upper()
    p376_authorized = b(p376.get("promotion_authorized", False))
    p376_operational = b(p376.get("operational", False))

    if p375_present and p375_state == "MULTI_CYCLE_STABILITY_BLOCKED":
        blockers.append("PHASE375_BLOCKED")
    if p376_present and p376_state == "PRODUCTION_PAPER_PROMOTION_BLOCKED":
        blockers.append("PHASE376_BLOCKED")
    if blocked > 0:
        blockers.append(f"BLOCKED_CYCLES_PRESENT:{blocked}")

    qualification_ready = (
        p375_present
        and p375_state == "MULTI_CYCLE_STABILITY_QUALIFIED"
        and p375_qualified
        and p375_operational
        and runtime_pass
        and observed >= 3
        and valid >= 3
        and blocked == 0
    )

    gate_ready = (
        p376_present
        and p376_state == "PRODUCTION_PAPER_PROMOTION_AUTHORIZED"
        and p376_authorized
        and p376_operational
    )

    if blockers:
        state = "PROMOTION_READINESS_BLOCKED"
        promotion_ready = False
        operational = False
    elif qualification_ready and gate_ready:
        state = "PROMOTION_READINESS_READY"
        promotion_ready = True
        operational = True
    else:
        state = "PROMOTION_READINESS_WAITING"
        promotion_ready = False
        operational = True

    payload = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "qualification_state": p375_state or "NOT_AVAILABLE",
        "promotion_gate_state": p376_state or "NOT_AVAILABLE",
        "promotion_readiness_state": state,
        "promotion_ready": promotion_ready,
        "operational": operational,
        "blockers": blockers,
        "counts": {
            "observed": observed,
            "valid": valid,
            "blocked": blocked,
        },
        "checks": {
            "phase375_present": p375_present,
            "phase376_present": p376_present,
            "runtime_supervision_pass": runtime_pass,
            "phase375_qualified": p375_qualified,
            "phase376_authorized": p376_authorized,
            "qualification_ready": qualification_ready,
            "gate_ready": gate_ready,
        },
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        },
    }

    readiness_date = datetime.now(timezone.utc).date().isoformat()
    row = {
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "readiness_date": readiness_date,
        "qualification_state": payload["qualification_state"],
        "promotion_readiness_state": state,
        "promotion_ready": promotion_ready,
        "observed_cycles": observed,
        "valid_cycles": valid,
        "blocked_cycles": blocked,
        "runtime_supervision_pass": runtime_pass,
        "paper_only_boundary_pass": True,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "historical_rewrite_allowed": False,
        "source_phase375_run_id": os.getenv("PHASE375_RUN_ID"),
        "source_phase376_run_id": os.getenv("PHASE376_RUN_ID"),
        "raw_state": payload,
    }
    row["reconciliation_hash"] = digest({
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "readiness_date": readiness_date,
        "qualification_state": row["qualification_state"],
        "promotion_readiness_state": state,
        "promotion_ready": promotion_ready,
        "observed_cycles": observed,
        "valid_cycles": valid,
        "blocked_cycles": blocked,
    })

    persisted = False
    if p375_present or p376_present:
        request(
            "POST",
            f"{TARGET_TABLE}?on_conflict=portfolio_id,strategy_version,readiness_date",
            [row],
            prefer="resolution=merge-duplicates,return=minimal",
        )
        persisted = True

    payload["persisted"] = persisted
    payload["target_table"] = TARGET_TABLE

    (art / "phase379_result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.9",
        "",
        "## Production Paper Qualification State Reconciliation + Automatic Promotion Readiness",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Promotion Ready: **{'YES' if promotion_ready else 'NO'}**",
        f"- Persisted: **{'YES' if persisted else 'NO'}**",
        "",
        "## Reconciled Qualification Evidence",
        "",
        f"- Phase 3.7.5 State: **{p375_state or 'NOT_AVAILABLE'}**",
        f"- Observed Cycles: **{observed}**",
        f"- Valid Cycles: **{valid}**",
        f"- Blocked Cycles: **{blocked}**",
        f"- Runtime Supervision: **{'PASS' if runtime_pass else 'WAITING'}**",
        "",
        "## Promotion Gate",
        "",
        f"- Phase 3.7.6 State: **{p376_state or 'NOT_AVAILABLE'}**",
        f"- Promotion Authorized: **{'YES' if p376_authorized else 'NO'}**",
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
    ]
    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{x}**" for x in blockers]

    (art / "phase379_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Promotion Ready: {'YES' if promotion_ready else 'NO'}")
    print(f"Observed Cycles: {observed}")
    print(f"Valid Cycles: {valid}")
    print(f"Blocked Cycles: {blocked}")
    print(f"Persisted: {'YES' if persisted else 'NO'}")
    if blockers:
        print("Blockers: " + ", ".join(blockers))

    return 1 if state == "PROMOTION_READINESS_BLOCKED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
