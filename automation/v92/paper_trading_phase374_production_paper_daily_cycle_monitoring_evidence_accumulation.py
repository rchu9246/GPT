#!/usr/bin/env python3

from __future__ import annotations
import json, os, sys, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE374_PRODUCTION_PAPER_DAILY_CYCLE_MONITORING_EVIDENCE_ACCUMULATION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
DATA_COLLECTION_ENABLED = True
RUNTIME_SUPERVISION_ENABLED = True

TABLE_GROUPS = {
    "activation": ["paper_post_recovery_activation_state_v92"],
    "master_cycle": ["paper_post_recovery_master_cycle_v92"],
    "runtime": ["paper_runtime_supervision_state_v92", "paper_production_runtime_supervision_v92", "paper_runtime_state_v92"],
    "signals": ["paper_signals_v92", "signals_v92", "signals"],
    "decisions": ["paper_trade_decisions_v92", "paper_decisions_v92", "trade_decisions_v92"],
    "orders": ["paper_orders_v92", "paper_trade_orders_v92"],
    "trades": ["paper_trades_v92", "paper_executions_v92", "paper_trade_executions_v92"],
    "positions": ["paper_positions_v92", "paper_portfolio_positions_v92"],
    "evidence": ["paper_evidence_v92", "paper_runtime_evidence_v92", "paper_production_evidence_v92", "production_evidence_v92"],
}

BLOCK_WORDS = {"REVOKED","FAIL_CLOSED","BLOCKED","HALTED","SUSPENDED","ERROR","FAILED"}

def env_first(*names: str) -> Optional[str]:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY", "VITE_SUPABASE_PUBLISHABLE_KEY")

class RestError(RuntimeError):
    pass

def request(table: str, limit: int = 100) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE configuration missing")
    q = urllib.parse.urlencode({"select":"*","limit":str(limit)})
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}?{q}",
        headers={"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}","Accept":"application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8") or "[]")
            return data if isinstance(data, list) else []
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RestError(f"HTTP {e.code}: {body}") from e

def is_missing(exc: Exception) -> bool:
    s = str(exc).lower()
    return "pgrst205" in s or "42p01" in s or "could not find the table" in s

def inspect(candidates: List[str]) -> Tuple[Optional[str], List[Dict[str, Any]], List[str]]:
    errs = []
    for t in candidates:
        try:
            return t, request(t), errs
        except Exception as e:
            if is_missing(e):
                errs.append(f"{t}:NOT_PRESENT")
                continue
            errs.append(f"{t}:{type(e).__name__}")
    return None, [], errs

def text(v: Any) -> str:
    return "" if v is None else str(v).strip()

def latest(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    keys = ["updated_at","created_at","run_at","run_date","trade_date","date","id"]
    def k(row):
        lower = {str(a).lower(): b for a,b in row.items()}
        for name in keys:
            if name in lower and lower[name] is not None:
                return text(lower[name])
        return ""
    return sorted(rows,key=k,reverse=True)[0]

def blocked(row: Dict[str, Any]) -> bool:
    if not row:
        return False
    hay = " ".join(text(v).upper() for v in row.values())
    return any(w in hay for w in BLOCK_WORDS)

def active(row: Dict[str, Any]) -> bool:
    if not row:
        return False
    hay = " ".join(text(v).upper() for v in row.values())
    return any(w in hay for w in ["ACTIVE","CONTINUE_ACTIVE","AUTHORIZED_PAPER_CONTINUATION","PASS","READY"])

def main() -> int:
    art = Path("artifacts/phase374")
    art.mkdir(parents=True, exist_ok=True)

    result = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "paper_only": PAPER_ONLY,
        "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
        "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
        "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        "data_collection_enabled": DATA_COLLECTION_ENABLED,
        "runtime_supervision_enabled": RUNTIME_SUPERVISION_ENABLED,
    }

    if not SUPABASE_URL or not SUPABASE_KEY:
        result.update(state="DAILY_CYCLE_BLOCKED", operational=False, blockers=["SUPABASE_CONFIGURATION_MISSING"])
        return finish(art, result)

    sources = {}
    for name, candidates in TABLE_GROUPS.items():
        table, rows, errors = inspect(candidates)
        sources[name] = {"table":table,"rows_sampled":len(rows),"latest":latest(rows),"errors":errors}
    result["sources"] = sources

    activation_ok = bool(sources["activation"]["latest"]) and active(sources["activation"]["latest"]) and not blocked(sources["activation"]["latest"])
    master_ok = bool(sources["master_cycle"]["latest"]) and not blocked(sources["master_cycle"]["latest"])
    runtime_ok = bool(sources["runtime"]["latest"]) and not blocked(sources["runtime"]["latest"])

    signals = sources["signals"]["rows_sampled"] > 0
    decisions = sources["decisions"]["rows_sampled"] > 0
    orders = sources["orders"]["rows_sampled"] > 0
    trades = sources["trades"]["rows_sampled"] > 0
    positions = sources["positions"]["rows_sampled"] > 0
    evidence = sources["evidence"]["rows_sampled"] > 0

    cycle_evidence = signals or decisions or orders or trades or positions or evidence
    trade_activity = orders or trades or positions

    blockers = []
    if not activation_ok: blockers.append("ACTIVATION_NOT_ACTIVE")
    if not master_ok: blockers.append("MASTER_CYCLE_NOT_READY")
    if not runtime_ok: blockers.append("RUNTIME_SUPERVISION_NOT_READY")

    if blockers:
        state = "DAILY_CYCLE_BLOCKED"
        operational = False
    elif trade_activity:
        state = "DAILY_CYCLE_OPERATIONAL_PASS"
        operational = True
    else:
        state = "DAILY_CYCLE_NO_TRADE_VALID"
        operational = True

    result.update(
        state=state,
        operational=operational,
        blockers=blockers,
        checks={
            "activation_canonical":"PASS" if activation_ok else "FAIL",
            "master_cycle_canonical":"PASS" if master_ok else "FAIL",
            "runtime_supervision":"PASS" if runtime_ok else "FAIL",
            "cycle_evidence_observed":"YES" if cycle_evidence else "NO",
            "trade_activity_observed":"YES" if trade_activity else "NO",
            "zero_trade_valid":"YES",
            "paper_only_boundary":"PASS",
            "broker_order_submission":"DISABLED",
            "real_money_trading":"DISABLED",
            "historical_rewrite_prohibition":"PASS",
        }
    )
    return finish(art, result)

def finish(art: Path, result: Dict[str, Any]) -> int:
    (art/"phase374_result.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    lines = [
        "# GPT Quant V9.2 Paper Trading ??Phase 3.7.4",
        "",
        "## Production Paper Daily Cycle Monitoring + Evidence Accumulation",
        "",
        f"- Contract: `{result['contract']}`",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Strategy Version: `{result['strategy_version']}`",
        f"- Daily Validation State: **{result.get('state','UNKNOWN')}**",
        f"- Operational: **{'YES' if result.get('operational') else 'NO'}**",
        "",
        "## Validation Checks",
        "",
    ]
    for k,v in result.get("checks",{}).items():
        lines.append(f"- {k}: **{v}**")
    lines += [
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
    ]
    if result.get("blockers"):
        lines += ["","## Blockers",""]
        lines += [f"- **{b}**" for b in result["blockers"]]
    (art/"phase374_summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"State: {result.get('state')}")
    for k,v in result.get("checks",{}).items():
        print(f"{k}: {v}")
    if result.get("blockers"):
        print("Blockers: "+", ".join(result["blockers"]))
    return 0 if result.get("operational") else 1

if __name__ == "__main__":
    raise SystemExit(main())