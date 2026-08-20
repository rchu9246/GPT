from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE370_PRODUCTION_PAPER_AUTONOMOUS_OPERATIONS_OBSERVATION_VALIDATION"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

STATE_OBSERVING = "OBSERVING"
STATE_VALIDATED = "VALIDATED"
STATE_LIMITED = "VALIDATED_WITH_LIMITED_TRADE_COVERAGE"
STATE_FAIL_CLOSED = "FAIL_CLOSED"

PASS_LIFECYCLE_STATES = {"PASS", "PASS_WITH_OBSERVATION"}

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

def evidence_history(sb: Supabase, portfolio_id: str, limit: int) -> List[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + "&order=evidence_date.asc"
        + "&limit=" + str(limit)
    )
    return sb.get("paper_daily_lifecycle_evidence_v92", query)

def chain_breaks(rows: List[Dict[str, Any]]) -> List[str]:
    breaks: List[str] = []
    previous_sha: Optional[str] = None

    for index, row in enumerate(rows):
        current_date = str(row.get("evidence_date") or f"row-{index+1}")
        declared_previous = str(row.get("previous_evidence_sha256") or "")
        current_sha = str(row.get("evidence_sha256") or "")

        if index == 0:
            if declared_previous not in {"GENESIS", ""}:
                breaks.append(f"{current_date}:FIRST_RECORD_PREVIOUS_NOT_GENESIS")
        else:
            if declared_previous != (previous_sha or ""):
                breaks.append(f"{current_date}:PREVIOUS_SHA_MISMATCH")

        if len(current_sha) != 64:
            breaks.append(f"{current_date}:INVALID_CURRENT_SHA256")

        previous_sha = current_sha

    return breaks

def nav_metrics(rows: List[Dict[str, Any]]) -> Tuple[float, float, float, float]:
    navs = [as_float(r.get("nav"), 0.0) for r in rows]
    navs = [v for v in navs if v > 0]

    if not navs:
        return 0.0, 0.0, 0.0, 0.0

    initial = navs[0]
    latest = navs[-1]
    cumulative_return = (latest / initial - 1.0) if initial else 0.0

    peak = navs[0]
    max_drawdown = 0.0
    for nav in navs:
        peak = max(peak, nav)
        if peak > 0:
            dd = nav / peak - 1.0
            max_drawdown = min(max_drawdown, dd)

    return initial, latest, cumulative_return, max_drawdown

def evaluate(rows: List[Dict[str, Any]], policy: Dict[str, Any]) -> Dict[str, Any]:
    count = len(rows)

    passed_days = sum(
        1 for r in rows
        if str(r.get("lifecycle_state") or "").upper() in PASS_LIFECYCLE_STATES
        and as_bool(r.get("lifecycle_passed"), False)
    )
    pass_rate = (passed_days / count) if count else 0.0

    fail_closed_days = sum(
        1 for r in rows
        if str(r.get("lifecycle_state") or "").upper() == "FAIL_CLOSED"
    )
    safety_revocation_days = sum(
        1 for r in rows
        if as_bool(r.get("safety_revocation_triggered"), False)
    )
    controller_executed_days = sum(
        1 for r in rows
        if as_bool(r.get("daily_paper_cycle_executed"), False)
    )
    authorized_days = sum(
        1 for r in rows
        if as_bool(r.get("autonomous_daily_operations_authorized"), False)
    )

    signal_days = sum(1 for r in rows if as_int(r.get("eligible_signals"), 0) > 0)
    order_days = sum(1 for r in rows if as_int(r.get("order_intents_created"), 0) > 0)
    fill_days = sum(1 for r in rows if as_int(r.get("simulated_fills_created"), 0) > 0)
    settled_fill_days = sum(1 for r in rows if as_int(r.get("fills_settled"), 0) > 0)

    breaks = chain_breaks(rows)
    initial_nav, latest_nav, cumulative_return, max_drawdown = nav_metrics(rows)

    hard_failures: List[str] = []
    observations: List[str] = []

    if safety_revocation_days > int(policy["max_safety_revocation_days"]):
        hard_failures.append("SAFETY_REVOCATION_TOLERANCE_EXCEEDED")
    if len(breaks) > int(policy["max_chain_breaks"]):
        hard_failures.append("EVIDENCE_CHAIN_BREAK")
    if max_drawdown < -abs(float(policy["max_drawdown_pct"])):
        hard_failures.append("MAX_DRAWDOWN_LIMIT_EXCEEDED")

    min_days = int(policy["min_observation_days"])
    min_pass_rate = float(policy["min_pass_rate"])

    history_ready = count >= min_days
    pass_rate_ready = pass_rate >= min_pass_rate

    if count < min_days:
        observations.append("INSUFFICIENT_OBSERVATION_DAYS")
    if count and pass_rate < min_pass_rate:
        observations.append("PASS_RATE_BELOW_TARGET")
    if signal_days == 0:
        observations.append("NO_SIGNAL_DAY_COVERAGE_YET")
    if fill_days == 0:
        observations.append("NO_SIMULATED_FILL_COVERAGE_YET")

    if hard_failures:
        state = STATE_FAIL_CLOSED
        validated = False
    elif not history_ready or not pass_rate_ready:
        state = STATE_OBSERVING
        validated = False
    elif fill_days == 0:
        state = STATE_LIMITED
        validated = True
    else:
        state = STATE_VALIDATED
        validated = True

    remaining_days = max(0, min_days - count)

    return {
        "observation_state": state,
        "validated": validated,
        "observation_days": count,
        "remaining_minimum_days": remaining_days,
        "passed_days": passed_days,
        "pass_rate": round(pass_rate, 6),
        "fail_closed_days": fail_closed_days,
        "safety_revocation_days": safety_revocation_days,
        "controller_executed_days": controller_executed_days,
        "authorized_days": authorized_days,
        "signal_days": signal_days,
        "order_days": order_days,
        "fill_days": fill_days,
        "settled_fill_days": settled_fill_days,
        "evidence_chain_breaks": breaks,
        "initial_nav": initial_nav,
        "latest_nav": latest_nav,
        "cumulative_return": cumulative_return,
        "max_drawdown": max_drawdown,
        "hard_failures": hard_failures,
        "observations": observations,
        "acceptance_candidate": (
            validated
            and state == STATE_VALIDATED
            and not hard_failures
        ),
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--observation-date", default=str(date.today()))
    parser.add_argument("--history-limit", type=int, default=120)
    args = parser.parse_args()

    date.fromisoformat(args.observation_date)

    policy = {
        "min_observation_days": int(os.getenv("PHASE370_MIN_OBSERVATION_DAYS", "20")),
        "min_pass_rate": float(os.getenv("PHASE370_MIN_PASS_RATE", "0.95")),
        "max_drawdown_pct": float(os.getenv("PHASE370_MAX_DRAWDOWN_PCT", "0.15")),
        "max_safety_revocation_days": int(os.getenv("PHASE370_MAX_SAFETY_REVOCATION_DAYS", "0")),
        "max_chain_breaks": int(os.getenv("PHASE370_MAX_CHAIN_BREAKS", "0")),
    }

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
    rows = evidence_history(sb, args.portfolio_id, args.history_limit)

    if not rows:
        raise RuntimeError("No Phase 3.6.9 lifecycle evidence found")

    result = evaluate(rows, policy)

    source_tail_sha = str(rows[-1].get("evidence_sha256") or "")
    evidence_doc = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "observation_date": args.observation_date,
        "policy": policy,
        "result": result,
        "source_tail_evidence_sha256": source_tail_sha,
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
        "observation_date": args.observation_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,

        "observation_state": result["observation_state"],
        "validated": result["validated"],
        "acceptance_candidate": result["acceptance_candidate"],

        "observation_days": result["observation_days"],
        "remaining_minimum_days": result["remaining_minimum_days"],
        "passed_days": result["passed_days"],
        "pass_rate": result["pass_rate"],

        "controller_executed_days": result["controller_executed_days"],
        "authorized_days": result["authorized_days"],
        "signal_days": result["signal_days"],
        "order_days": result["order_days"],
        "fill_days": result["fill_days"],
        "settled_fill_days": result["settled_fill_days"],

        "fail_closed_days": result["fail_closed_days"],
        "safety_revocation_days": result["safety_revocation_days"],
        "evidence_chain_break_count": len(result["evidence_chain_breaks"]),

        "initial_nav": result["initial_nav"],
        "latest_nav": result["latest_nav"],
        "cumulative_return": result["cumulative_return"],
        "max_drawdown": result["max_drawdown"],

        "hard_failures": result["hard_failures"],
        "observations": result["observations"],
        "policy": policy,

        "source_tail_evidence_sha256": source_tail_sha,

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
        "paper_operations_observation_validation_v92",
        payload,
        "portfolio_id,observation_date",
    )

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["evidence_document"] = evidence_doc
    audit["created_at"] = datetime.now(timezone.utc).isoformat()

    sb.request(
        "POST",
        "paper_operations_observation_validation_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.0")
    print()
    print("## Production Paper Autonomous Operations Observation + Validation")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Observation Date: `{args.observation_date}`")
    print(f"- Observation State: **{result['observation_state']}**")
    print(f"- Observation Validated: **{'YES' if result['validated'] else 'NO'}**")
    print(f"- Acceptance Candidate: **{'YES' if result['acceptance_candidate'] else 'NO'}**")
    print()
    print("## Observation Progress")
    print()
    print(f"- Observation Days: **{result['observation_days']} / {policy['min_observation_days']}**")
    print(f"- Remaining Minimum Days: **{result['remaining_minimum_days']}**")
    print(f"- Lifecycle PASS Days: **{result['passed_days']}**")
    print(f"- Lifecycle PASS Rate: **{result['pass_rate'] * 100:.2f}%**")
    print(f"- Controller Executed Days: **{result['controller_executed_days']}**")
    print(f"- Authorized Days: **{result['authorized_days']}**")
    print()
    print("## Trade-Lifecycle Coverage")
    print()
    print(f"- Signal Days: **{result['signal_days']}**")
    print(f"- Order Days: **{result['order_days']}**")
    print(f"- Simulated Fill Days: **{result['fill_days']}**")
    print(f"- Settled Fill Days: **{result['settled_fill_days']}**")
    print()
    print("## Portfolio Observation")
    print()
    print(f"- Initial NAV: **{result['initial_nav']:.2f}**")
    print(f"- Latest NAV: **{result['latest_nav']:.2f}**")
    print(f"- Cumulative Return: **{result['cumulative_return'] * 100:.4f}%**")
    print(f"- Maximum Drawdown: **{result['max_drawdown'] * 100:.4f}%**")
    print()
    print("## Governance Integrity")
    print()
    print(f"- FAIL_CLOSED Days: **{result['fail_closed_days']}**")
    print(f"- Safety Revocation Days: **{result['safety_revocation_days']}**")
    print(f"- Evidence Chain Breaks: **{len(result['evidence_chain_breaks'])}**")

    if result["hard_failures"]:
        print()
        print("## Hard Failures")
        print()
        for item in result["hard_failures"]:
            print(f"- `{item}`")

    if result["observations"]:
        print()
        print("## Observation Notes")
        print()
        for item in result["observations"]:
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

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase370")
    os.makedirs(out_dir, exist_ok=True)
    with open(
        os.path.join(out_dir, "observation_validation_evidence.json"),
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

    # OBSERVING is a successful governance state while history accumulates.
    # FAIL_CLOSED is also persisted as a governance outcome; only software/runtime
    # errors fail the GitHub job.
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE370_FATAL: {exc}", file=sys.stderr)
        raise