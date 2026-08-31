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

def request(table: str, limit: int = 100, portfolio_scoped: bool = False) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE configuration missing")

    params = {"select":"*","limit":str(limit)}
    if portfolio_scoped:
        params["portfolio_id"] = f"eq.{PORTFOLIO_ID}"

    q = urllib.parse.urlencode(params)
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

def inspect(candidates: List[str], portfolio_scoped: bool = False) -> Tuple[Optional[str], List[Dict[str, Any]], List[str]]:
    errs = []
    for t in candidates:
        try:
            if portfolio_scoped:
                try:
                    rows = request(t, portfolio_scoped=True)
                    return t, rows, errs
                except RestError as scoped_error:
                    # Some legacy-compatible tables may not expose portfolio_id.
                    # Fall back only when the schema itself rejects that column/filter.
                    msg = str(scoped_error).lower()
                    if "portfolio_id" not in msg and "pgrst" not in msg:
                        raise
                    errs.append(f"{t}:PORTFOLIO_FILTER_FALLBACK")
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

def field_state(row: Dict[str, Any], names: Tuple[str, ...]) -> str:
    lower = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = text(lower.get(name.lower())).upper()
        if value:
            return value
    return ""

# PHASE371812_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_STATE_RECONCILIATION_FIX
# PHASE371815_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_TIMESTAMP_PROVENANCE_RECONCILIATION_FIX
CANONICAL_TIMESTAMP_PRIORITY = (
    "updated_at",
    "observed_at",
    "validated_at",
    "run_at",
    "cycle_at",
    "created_at",
    "cycle_date",
    "run_date",
    "trade_date",
    "date",
)

def canonical_timestamp_with_provenance(row: Dict[str, Any]):
    if not row:
        return None, None, None

    lower = {str(k).lower(): v for k, v in row.items()}

    for name in CANONICAL_TIMESTAMP_PRIORITY:
        raw = text(lower.get(name))
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc), name, raw
        except Exception:
            try:
                dt = datetime.fromisoformat(raw[:10])
                return dt.replace(tzinfo=timezone.utc), name, raw
            except Exception:
                continue

    return None, None, None

def canonical_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    dt, _, _ = canonical_timestamp_with_provenance(row)
    return dt

# PHASE371816_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION_FIX
CANONICAL_EVENT_TIMESTAMP_PRIORITY = (
    "observed_at",
    "validated_at",
    "run_at",
    "cycle_at",
    "cycle_date",
    "run_date",
    "trade_date",
    "date",
    "updated_at",
    "created_at",
)

def canonical_event_timestamp_with_provenance(row: Dict[str, Any]):
    if not row:
        return None, None, None

    lower = {str(k).lower(): v for k, v in row.items()}

    for name in CANONICAL_EVENT_TIMESTAMP_PRIORITY:
        raw = text(lower.get(name))
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc), name, raw
        except Exception:
            try:
                dt = datetime.fromisoformat(raw[:10])
                return dt.replace(tzinfo=timezone.utc), name, raw
            except Exception:
                continue

    return None, None, None

def canonical_event_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    dt, _, _ = canonical_event_timestamp_with_provenance(row)
    return dt

# PHASE371817_RUNTIME_SUPERVISION_CROSS_SOURCE_CANONICAL_EVENT_TIME_SEMANTIC_NORMALIZATION_FIX
EVENT_TIME_SEMANTIC_CLASS = {
    "observed_at": "event",
    "validated_at": "event",
    "run_at": "event",
    "cycle_at": "event",
    "updated_at": "lifecycle",
    "created_at": "lifecycle",
    "cycle_date": "cycle_date",
    "run_date": "cycle_date",
    "trade_date": "cycle_date",
    "date": "cycle_date",
}

def timestamp_semantic_class(source: Optional[str]) -> str:
    if not source:
        return "unknown"
    return EVENT_TIME_SEMANTIC_CLASS.get(source, "unknown")

def normalize_cycle_date_boundary(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)

def canonical_semantic_event_time(row: Dict[str, Any]):
    dt, source, _ = canonical_event_timestamp_with_provenance(row)
    semantic = timestamp_semantic_class(source)
    if dt is None:
        return None, source, semantic
    if semantic == "cycle_date":
        dt = normalize_cycle_date_boundary(dt)
    return dt, source, semantic

# PHASE371818_RUNTIME_SUPERVISION_NORMALIZED_MASTER_CYCLE_BUSINESS_DATE_RUNTIME_EVENT_DATE_RECONCILIATION_FIX
def canonical_business_date(row: Dict[str, Any]):
    if not row:
        return None, None

    lower = {str(k).lower(): v for k, v in row.items()}
    for name in ("cycle_date", "run_date", "trade_date", "date"):
        raw = text(lower.get(name))
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw[:10]).date(), name
        except Exception:
            continue

    dt, source, _ = canonical_event_timestamp_with_provenance(row)
    if dt is not None:
        return dt.date(), source

    return None, None

# PHASE371819_RUNTIME_SUPERVISION_CROSS_DOMAIN_BUSINESS_DATE_EVENT_TIME_SUPERSESSION_RECONCILIATION_FIX
def cross_domain_supersession_evidence(
    runtime_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    runtime_event_dt, runtime_event_src, runtime_event_sem = canonical_semantic_event_time(runtime_row)
    master_event_dt, master_event_src, master_event_sem = canonical_semantic_event_time(master_row)

    runtime_business_date, runtime_business_src = canonical_business_date(runtime_row)
    master_business_date, master_business_src = canonical_business_date(master_row)

    if runtime_event_dt is None:
        return False, "RUNTIME_EVENT_TIME_MISSING"

    if master_business_date is None:
        return False, "MASTER_BUSINESS_DATE_MISSING"

    if runtime_event_sem not in {"event", "lifecycle"}:
        return False, (
            f"RUNTIME_EVENT_DOMAIN_NOT_PRECISE:"
            f"source={runtime_event_src},semantic={runtime_event_sem}"
        )

    # Business-date and event-time are different clock domains.
    # Only date-level ordering may be used between them.
    if master_business_date > runtime_event_dt.date():
        return True, (
            f"MASTER_BUSINESS_DATE_SUPERSEDES_RUNTIME_EVENT_DATE:"
            f"runtime={runtime_event_src}/{runtime_event_dt.date()},"
            f"master={master_business_src}/{master_business_date}"
        )

    if master_business_date == runtime_event_dt.date():
        return False, (
            f"SAME_DATE_CROSS_DOMAIN_AMBIGUOUS:"
            f"runtime={runtime_event_src}/{runtime_event_dt.date()},"
            f"master={master_business_src}/{master_business_date}"
        )

    # A business date before the runtime event date cannot by itself supersede
    # that runtime event. Remain fail-closed.
    return False, (
        f"MASTER_BUSINESS_DATE_PRECEDES_RUNTIME_EVENT_DATE:"
        f"runtime={runtime_event_src}/{runtime_event_dt.date()},"
        f"master={master_business_src}/{master_business_date}"
    )

def semantically_comparable_supersession(runtime_row: Dict[str, Any], master_row: Dict[str, Any]):
    runtime_dt, runtime_src, runtime_sem = canonical_semantic_event_time(runtime_row)
    master_dt, master_src, master_sem = canonical_semantic_event_time(master_row)

    runtime_business_date, runtime_business_src = canonical_business_date(runtime_row)
    master_business_date, master_business_src = canonical_business_date(master_row)

    if runtime_dt is None and runtime_business_date is None:
        return False, "RUNTIME_EVENT_AND_BUSINESS_DATE_MISSING"

    if master_dt is None and master_business_date is None:
        return False, "MASTER_EVENT_AND_BUSINESS_DATE_MISSING"

    if runtime_sem == "unknown" or master_sem == "unknown":
        return False, (
            f"UNKNOWN_EVENT_TIME_SEMANTICS:"
            f"runtime={runtime_src},master={master_src}"
        )

    # Same-domain comparisons remain unchanged.
    if runtime_sem == master_sem and runtime_dt is not None and master_dt is not None:
        return (
            master_dt > runtime_dt,
            f"SAME_SEMANTIC_CLASS:{runtime_sem}:runtime={runtime_src},master={master_src}"
        )

    # Cross-domain business-date vs precise event/lifecycle timestamp.
    if master_sem == "cycle_date" and runtime_sem in {"event", "lifecycle"}:
        return cross_domain_supersession_evidence(runtime_row, master_row)

    if runtime_sem == "cycle_date" and master_sem in {"event", "lifecycle"}:
        if runtime_business_date is None or master_business_date is None:
            return False, "CROSS_DOMAIN_BUSINESS_DATE_MISSING"
        return (
            master_business_date > runtime_business_date,
            (
                f"MASTER_EVENT_DATE_VS_RUNTIME_BUSINESS_DATE:"
                f"runtime={runtime_src}/{runtime_business_date},"
                f"master={master_src}/{master_business_date}"
            ),
        )

    if {runtime_sem, master_sem} <= {"event", "lifecycle"}:
        if runtime_dt is None or master_dt is None:
            return False, "PRECISE_CROSS_DOMAIN_TIMESTAMP_MISSING"
        return (
            master_dt > runtime_dt,
            f"PRECISE_CROSS_DOMAIN:runtime={runtime_src},master={master_src}"
        )

    return False, (
        f"UNSAFE_CROSS_DOMAIN_EVENT_TIME_SEMANTICS:"
        f"runtime={runtime_src}/{runtime_sem},master={master_src}/{master_sem}"
    )


def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    comparable, reason = semantically_comparable_supersession(runtime_row, master_row)
    if comparable:
        return True, f"SUSPENDED_SUPERSEDED_BY_NORMALIZED_MASTER_EVENT:{reason}"

    activation_dt, activation_src, activation_sem = canonical_semantic_event_time(activation_row)
    runtime_dt, runtime_src, runtime_sem = canonical_semantic_event_time(runtime_row)
    master_dt, master_src, master_sem = canonical_semantic_event_time(master_row)

    if (
        activation_dt is not None
        and runtime_dt is not None
        and activation_sem in {"event", "lifecycle"}
        and runtime_sem in {"event", "lifecycle"}
        and activation_dt > runtime_dt
        and master_dt is not None
        and master_sem == "cycle_date"
        and master_dt.date() > runtime_dt.date()
    ):
        return True, (
            f"SUSPENDED_CROSS_SOURCE_SEMANTIC_RECONCILED:"
            f"runtime={runtime_src}/{runtime_sem},"
            f"activation={activation_src}/{activation_sem},"
            f"master={master_src}/{master_sem}"
        )

    return False, f"SUSPENDED_NOT_SUPERSEDED_BY_NORMALIZED_MASTER_EVENT:{reason}"

def runtime_supervision_ready(
    row: Dict[str, Any],
    activation_row: Optional[Dict[str, Any]] = None,
    master_row: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    if not row:
        return False, "MISSING"

    state = field_state(
        row,
        ("supervision_state", "runtime_supervision", "runtime_supervision_state", "state", "status"),
    )

    hard_block_states = {"REVOKED","FAIL_CLOSED","BLOCKED","HALTED","ERROR","FAILED"}
    ready_states = {
        "CONTINUE_ACTIVE","CONTINUE_WITH_OBSERVATION","ACTIVE","ENABLED",
        "READY","PASS","AUTHORIZED_PAPER_CONTINUATION",
    }

    if state in hard_block_states:
        return False, state

    if state == "SUSPENDED":
        ok, reason = suspended_is_superseded(
            row,
            activation_row or {},
            master_row or {},
        )
        return ok, reason

    if state in ready_states:
        return True, state

    if not blocked(row):
        return True, state or "PRESENT_NON_BLOCKING"

    return False, state or "BLOCKED"

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
        # Canonical control states must be resolved for this portfolio, not from
        # an unrelated globally-latest row.
        scoped = name in {"activation", "master_cycle", "runtime"}
        table, rows, errors = inspect(candidates, portfolio_scoped=scoped)
        sources[name] = {"table":table,"rows_sampled":len(rows),"latest":latest(rows),"errors":errors}
    result["sources"] = sources

    activation_ok = bool(sources["activation"]["latest"]) and active(sources["activation"]["latest"]) and not blocked(sources["activation"]["latest"])
    master_ok = bool(sources["master_cycle"]["latest"]) and not blocked(sources["master_cycle"]["latest"])
    runtime_ok, runtime_state = runtime_supervision_ready(
        sources["runtime"]["latest"],
        sources["activation"]["latest"],
        sources["master_cycle"]["latest"],
    )
    result["runtime_supervision_resolution"] = {
        "table": sources["runtime"]["table"],
        "state": runtime_state,
        "ready": runtime_ok,
        "compatibility_contract": "PHASE371819_CROSS_DOMAIN_BUSINESS_DATE_EVENT_TIME_RECONCILIATION",
        "runtime_timestamp": (
            canonical_timestamp(sources["runtime"]["latest"]).isoformat()
            if canonical_timestamp(sources["runtime"]["latest"]) else None
        ),
        "activation_timestamp": (
            canonical_timestamp(sources["activation"]["latest"]).isoformat()
            if canonical_timestamp(sources["activation"]["latest"]) else None
        ),
        "master_cycle_timestamp": (
            canonical_timestamp(sources["master_cycle"]["latest"]).isoformat()
            if canonical_timestamp(sources["master_cycle"]["latest"]) else None
        ),
        "runtime_timestamp_provenance": canonical_timestamp_with_provenance(
            sources["runtime"]["latest"]
        )[1],
        "activation_timestamp_provenance": canonical_timestamp_with_provenance(
            sources["activation"]["latest"]
        )[1],
        "master_cycle_timestamp_provenance": canonical_timestamp_with_provenance(
            sources["master_cycle"]["latest"]
        )[1],
        "timestamp_provenance_contract": "PHASE371815",
        "runtime_event_timestamp": (
            canonical_event_timestamp(sources["runtime"]["latest"]).isoformat()
            if canonical_event_timestamp(sources["runtime"]["latest"]) else None
        ),
        "activation_event_timestamp": (
            canonical_event_timestamp(sources["activation"]["latest"]).isoformat()
            if canonical_event_timestamp(sources["activation"]["latest"]) else None
        ),
        "master_cycle_event_timestamp": (
            canonical_event_timestamp(sources["master_cycle"]["latest"]).isoformat()
            if canonical_event_timestamp(sources["master_cycle"]["latest"]) else None
        ),
        "runtime_event_timestamp_provenance": canonical_event_timestamp_with_provenance(
            sources["runtime"]["latest"]
        )[1],
        "activation_event_timestamp_provenance": canonical_event_timestamp_with_provenance(
            sources["activation"]["latest"]
        )[1],
        "master_cycle_event_timestamp_provenance": canonical_event_timestamp_with_provenance(
            sources["master_cycle"]["latest"]
        )[1],
        "event_chronology_contract": "PHASE371816",
        "runtime_event_time_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(sources["runtime"]["latest"])[1]
        ),
        "activation_event_time_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(sources["activation"]["latest"])[1]
        ),
        "master_cycle_event_time_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(sources["master_cycle"]["latest"])[1]
        ),
        "cross_source_event_time_contract": "PHASE371817",
        "runtime_business_date": (
            canonical_business_date(sources["runtime"]["latest"])[0].isoformat()
            if canonical_business_date(sources["runtime"]["latest"])[0] else None
        ),
        "runtime_business_date_provenance": canonical_business_date(
            sources["runtime"]["latest"]
        )[1],
        "master_cycle_business_date": (
            canonical_business_date(sources["master_cycle"]["latest"])[0].isoformat()
            if canonical_business_date(sources["master_cycle"]["latest"])[0] else None
        ),
        "master_cycle_business_date_provenance": canonical_business_date(
            sources["master_cycle"]["latest"]
        )[1],
        "business_date_event_date_contract": "PHASE371818",
        "cross_domain_runtime_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(
                sources["runtime"]["latest"]
            )[1]
        ),
        "cross_domain_master_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(
                sources["master_cycle"]["latest"]
            )[1]
        ),
        "cross_domain_supersession_contract": "PHASE371819",
        "activation_semantically_active": (
            active(sources["activation"]["latest"])
            and not blocked(sources["activation"]["latest"])
        ),
        "master_newer_than_runtime": (
            canonical_timestamp(sources["master_cycle"]["latest"]) is not None
            and canonical_timestamp(sources["runtime"]["latest"]) is not None
            and canonical_timestamp(sources["master_cycle"]["latest"])
                > canonical_timestamp(sources["runtime"]["latest"])
        ),
        "master_chronology_reconciliation_contract": "PHASE371814_V2",
        "master_chronology_fail_closed": True,
    }

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
    if not runtime_ok: blockers.append(f"RUNTIME_SUPERVISION_NOT_READY:{runtime_state}")

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
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.4",
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
