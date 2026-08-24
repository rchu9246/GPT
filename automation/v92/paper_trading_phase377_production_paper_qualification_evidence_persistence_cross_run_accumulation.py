#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE377_PRODUCTION_PAPER_QUALIFICATION_EVIDENCE_PERSISTENCE_CROSS_RUN_ACCUMULATION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")
TARGET_TABLE = "paper_production_qualification_evidence_v92"

PHASE374_RESULT_PATH = Path(
    os.getenv("PHASE374_RESULT_PATH", "artifacts/phase377/input/phase374_result.json")
)

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False

VALID_STATES = {
    "DAILY_CYCLE_OPERATIONAL_PASS",
    "DAILY_CYCLE_NO_TRADE_VALID",
}
BLOCK_STATES = {
    "DAILY_CYCLE_BLOCKED",
    "BLOCKED",
    "FAIL_CLOSED",
    "FAILED",
    "ERROR",
}

def env_first(*names: str) -> Optional[str]:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first(
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_KEY",
)

class RestError(RuntimeError):
    pass

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
        raise RestError(f"HTTP {e.code}: {detail}") from e

def load_phase374() -> Dict[str, Any]:
    if not PHASE374_RESULT_PATH.exists():
        return {}
    try:
        obj = json.loads(PHASE374_RESULT_PATH.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def first_present(d: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None

def boolish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE", "T", "1", "YES", "Y", "PASS", "ENABLED"}

def resolve_cycle_date(src: Dict[str, Any]) -> str:
    candidates = [
        first_present(src, "run_date", "validation_date", "cycle_date", "trade_date", "date"),
        os.getenv("GITHUB_RUN_STARTED_AT"),
    ]
    for v in candidates:
        if not v:
            continue
        s = str(v).strip()
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            try:
                return date.fromisoformat(s[:10]).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).date().isoformat()

def extract_state(src: Dict[str, Any]) -> str:
    for k in ("daily_validation_state", "validation_state", "state", "status", "result"):
        v = src.get(k)
        if v:
            return str(v).strip().upper()
    return "UNKNOWN"

def evidence_digest(payload: Dict[str, Any]) -> str:
    stable = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()

def get_counts() -> Dict[str, int]:
    q = urllib.parse.urlencode({
        "select": "cycle_state,valid_cycle,blocked_cycle,cycle_date",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request("GET", f"{TARGET_TABLE}?{q}") or []
    return {
        "observed": len(rows),
        "valid": sum(1 for r in rows if boolish(r.get("valid_cycle"))),
        "blocked": sum(1 for r in rows if boolish(r.get("blocked_cycle"))),
    }

def main() -> int:
    art = Path("artifacts/phase377")
    art.mkdir(parents=True, exist_ok=True)

    src = load_phase374()
    blockers: List[str] = []

    if not src:
        state = "EVIDENCE_PERSISTENCE_WAITING_FOR_PHASE374"
        operational = True
        persisted = False
        counts = {"observed": 0, "valid": 0, "blocked": 0}
    else:
        cycle_state = extract_state(src)
        cycle_date = resolve_cycle_date(src)

        checks = src.get("checks", {}) if isinstance(src.get("checks"), dict) else {}
        safety = src.get("safety", {}) if isinstance(src.get("safety"), dict) else {}

        runtime_pass = str(checks.get("runtime_supervision", "")).upper() == "PASS"
        paper_only_pass = (
            str(checks.get("paper_only_boundary", "")).upper() == "PASS"
            or safety.get("paper_only") is True
        )
        trade_activity = boolish(
            first_present(src, "trade_activity_observed", "trade_activity", "trade_observed")
        )

        valid_cycle = cycle_state in VALID_STATES
        blocked_cycle = cycle_state in BLOCK_STATES

        if blocked_cycle:
            blockers.append(f"UPSTREAM_PHASE374_BLOCKED:{cycle_state}")
        if valid_cycle and not runtime_pass:
            blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
        if valid_cycle and not paper_only_pass:
            blockers.append("PAPER_ONLY_BOUNDARY_NOT_PASS")

        canonical = {
            "portfolio_id": PORTFOLIO_ID,
            "strategy_version": STRATEGY_VERSION,
            "cycle_date": cycle_date,
            "cycle_state": cycle_state,
            "valid_cycle": valid_cycle,
            "blocked_cycle": blocked_cycle,
            "runtime_supervision_pass": runtime_pass,
            "paper_only_boundary_pass": paper_only_pass,
            "trade_activity_observed": trade_activity,
            "source_workflow": os.getenv("GITHUB_WORKFLOW", "manual"),
            "source_run_id": os.getenv("GITHUB_RUN_ID", "local"),
            "source_run_attempt": int(os.getenv("GITHUB_RUN_ATTEMPT", "1")),
            "source_commit_sha": os.getenv("GITHUB_SHA"),
            "raw_evidence": src,
        }
        canonical["evidence_hash"] = evidence_digest({
            "portfolio_id": PORTFOLIO_ID,
            "strategy_version": STRATEGY_VERSION,
            "cycle_date": cycle_date,
            "cycle_state": cycle_state,
            "valid_cycle": valid_cycle,
            "blocked_cycle": blocked_cycle,
            "runtime_supervision_pass": runtime_pass,
            "paper_only_boundary_pass": paper_only_pass,
        })

        if blockers:
            state = "EVIDENCE_PERSISTENCE_BLOCKED"
            operational = False
            persisted = False
            counts = {"observed": 0, "valid": 0, "blocked": 0}
        else:
            # Idempotent per portfolio/strategy/cycle_date.
            path = (
                f"{TARGET_TABLE}"
                "?on_conflict=portfolio_id,strategy_version,cycle_date"
            )
            request(
                "POST",
                path,
                [canonical],
                prefer="resolution=merge-duplicates,return=minimal",
            )
            persisted = True
            counts = get_counts()
            state = "EVIDENCE_PERSISTENCE_OPERATIONAL"
            operational = True

    result = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "persisted": persisted,
        "blockers": blockers,
        "cross_run_counts": counts,
        "target_table": TARGET_TABLE,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_api_used": BROKER_API_USED,
            "broker_credentials_used": BROKER_CREDENTIALS_USED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        },
    }

    (art / "phase377_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.7",
        "",
        "## Production Paper Qualification Evidence Persistence + Cross-Run Accumulation",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Persisted Current Cycle: **{'YES' if persisted else 'NO'}**",
        f"- Canonical Table: `{TARGET_TABLE}`",
        "",
        "## Cross-Run Evidence",
        "",
        f"- Observed Cycles: **{counts['observed']}**",
        f"- Valid Cycles: **{counts['valid']}**",
        f"- Blocked Cycles: **{counts['blocked']}**",
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
    ]
    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{b}**" for b in blockers]

    (art / "phase377_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Operational: {'YES' if operational else 'NO'}")
    print(f"Persisted: {'YES' if persisted else 'NO'}")
    print(f"Observed Cycles: {counts['observed']}")
    print(f"Valid Cycles: {counts['valid']}")
    print(f"Blocked Cycles: {counts['blocked']}")
    if blockers:
        print("Blockers: " + ", ".join(blockers))

    return 1 if state == "EVIDENCE_PERSISTENCE_BLOCKED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
