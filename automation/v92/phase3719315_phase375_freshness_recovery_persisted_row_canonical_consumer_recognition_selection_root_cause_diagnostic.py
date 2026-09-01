from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719315"
MODE = "READ_ONLY_NO_MUTATION"

TARGETS = (
    "freshness_readiness",
    "freshness_health",
    "freshness_sla",
    "freshness_master",
)

TIME_FIELDS = ("updated_at", "created_at", "event_time", "recorded_at", "timestamp", "ts")
DATE_FIELDS = ("business_date", "run_date", "supervision_date", "cycle_date", "date")
STATE_FIELDS = (
    "state", "status", "health_state", "readiness_state", "qualification_state",
    "master_cycle_state", "runtime_state", "supervision_state", "operational_state",
    "activation_state", "final_state", "final_result", "result",
)
FAIL_FIELDS = ("critical_failures", "warning_failures", "reason_codes", "blockers")
RECOVERY_TOKENS = ("PASS", "READY", "HEALTHY", "ACTIVE", "QUALIFIED", "COMPLETED", "SUCCESS", "OK")
FAILURE_TOKENS = ("FAIL", "FAILED", "BLOCK", "SUSPEND", "REVOK", "CRITICAL", "STALE", "ERROR")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_consumer_selection_target", P375)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def first(row: Dict[str, Any], fields: Iterable[str]) -> str:
    if not row:
        return ""
    for key in fields:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""

def event_time(row: Dict[str, Any]) -> str:
    return first(row, TIME_FIELDS)

def business_date(row: Dict[str, Any]) -> str:
    value = first(row, DATE_FIELDS)
    if value:
        return value[:10]
    t = event_time(row)
    return t[:10] if len(t) >= 10 else "UNKNOWN_DATE"

def row_id(row: Dict[str, Any]) -> str:
    for key in ("id", "runtime_id", "run_id", "evidence_id", "supervision_id"):
        if row and row.get(key) is not None:
            return str(row.get(key))
    return ""

def chrono_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (event_time(row), business_date(row), row_id(row))

def state_values(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key in STATE_FIELDS + FAIL_FIELDS:
        if key in row:
            out[key] = row.get(key)
    return out

def recovery_semantics(row: Dict[str, Any]) -> Dict[str, Any]:
    vals = state_values(row)
    text = " ".join(str(v).upper() for v in vals.values())
    has_failure = any(tok in text for tok in FAILURE_TOKENS)
    has_recovery = any(tok in text for tok in RECOVERY_TOKENS)
    critical = row.get("critical_failures") if row else None
    critical_clear = critical in (None, [], {}, "", "NONE", "NULL")
    return {
        "has_recovery_token": has_recovery,
        "has_failure_token": has_failure,
        "critical_failures_clear": critical_clear,
        "recognized_recovery_shape": has_recovery and not has_failure and critical_clear,
    }

def target_hits(row: Dict[str, Any]) -> List[str]:
    if not row:
        return []
    blob = json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
    return [t for t in TARGETS if t.lower() in blob]

def inspect_contract(mod, attr: str) -> Dict[str, Any]:
    tables = getattr(mod, attr, None)
    if not tables:
        return {
            "declared_tables": None,
            "selected_table": None,
            "row_count": 0,
            "errors": ["MISSING_OR_EMPTY_CONTRACT"],
            "rows": [],
        }
    try:
        selected, rows, errors = mod.inspect(tables, portfolio_scoped=True)
        clean = [r for r in (rows or []) if isinstance(r, dict)]
        return {
            "declared_tables": list(tables) if isinstance(tables, (list, tuple)) else tables,
            "selected_table": selected,
            "row_count": len(clean),
            "errors": list(errors or []),
            "rows": clean,
        }
    except Exception as exc:
        return {
            "declared_tables": list(tables) if isinstance(tables, (list, tuple)) else tables,
            "selected_table": None,
            "row_count": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "rows": [],
        }

def row_profile(row: Dict[str, Any], table: str | None) -> Dict[str, Any]:
    return {
        "table": table,
        "id": row_id(row),
        "business_date": business_date(row),
        "event_time": event_time(row),
        "time_field_present": next((k for k in TIME_FIELDS if row.get(k) not in (None, "")), None),
        "date_field_present": next((k for k in DATE_FIELDS if row.get(k) not in (None, "")), None),
        "target_hits": target_hits(row),
        "schema_keys": sorted(row.keys()),
        "state_values": state_values(row),
        "recovery_semantics": recovery_semantics(row),
    }

def classify_selection(selected_runtime: Dict[str, Any] | None, candidate: Dict[str, Any]) -> str:
    if not candidate["time_field_present"]:
        return "REJECT_EVENT_TIME_MISSING"
    if not candidate["date_field_present"]:
        return "REJECT_BUSINESS_DATE_MISSING"
    if not candidate["state_values"]:
        return "REJECT_STATE_SCHEMA_MISSING"
    if not candidate["recovery_semantics"]["recognized_recovery_shape"]:
        return "REJECT_RECOVERY_SEMANTICS_NOT_RECOGNIZED"
    if selected_runtime:
        runtime_key = chrono_key(selected_runtime)
        fake_row = {
            "updated_at": candidate["event_time"],
            "business_date": candidate["business_date"],
            "id": candidate["id"],
        }
        if chrono_key(fake_row) <= runtime_key:
            return "REJECT_NOT_NEWER_THAN_SELECTED_RUNTIME"
    return "ELIGIBLE_NEWER_RECOGNIZABLE_RECOVERY"

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect", "latest", "RUNTIME_TABLES", "DAILY_EVIDENCE_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    runtime = inspect_contract(mod, "RUNTIME_TABLES")
    daily = inspect_contract(mod, "DAILY_EVIDENCE_TABLES")

    selected_runtime = mod.latest(runtime["rows"]) if runtime["rows"] else None

    # Inspect every declared DAILY_EVIDENCE table individually to avoid masking by first-selected table.
    declared = daily["declared_tables"] or []
    per_table = []
    all_rows = []
    for table_name in declared:
        try:
            selected, rows, errors = mod.inspect([table_name], portfolio_scoped=True)
            clean = [r for r in (rows or []) if isinstance(r, dict)]
        except Exception as exc:
            selected, clean, errors = None, [], [f"{type(exc).__name__}: {exc}"]
        per_table.append({
            "declared_table": table_name,
            "selected_table": selected,
            "row_count": len(clean),
            "errors": list(errors or []),
        })
        for row in clean:
            all_rows.append((table_name, row))

    per_target = {}
    for target in TARGETS:
        candidates = []
        for table_name, row in all_rows:
            if target not in target_hits(row):
                continue
            prof = row_profile(row, table_name)
            prof["selection_reason"] = classify_selection(selected_runtime, prof)
            candidates.append(prof)

        candidates.sort(key=lambda x: (x["event_time"], x["business_date"], x["id"]))

        eligible = [c for c in candidates if c["selection_reason"] == "ELIGIBLE_NEWER_RECOGNIZABLE_RECOVERY"]
        rejected = [c for c in candidates if c["selection_reason"] != "ELIGIBLE_NEWER_RECOGNIZABLE_RECOVERY"]

        reasons = {}
        for c in rejected:
            reasons[c["selection_reason"]] = reasons.get(c["selection_reason"], 0) + 1

        if eligible:
            status = "ELIGIBLE_RECOVERY_ROW_EXISTS_BUT_PHASE375_CONSUMER_DID_NOT_SELECT_IT"
        elif candidates:
            if "REJECT_RECOVERY_SEMANTICS_NOT_RECOGNIZED" in reasons:
                status = "PERSISTED_ROWS_FOUND_BUT_RECOVERY_SEMANTICS_BLOCK_SELECTION"
            elif "REJECT_NOT_NEWER_THAN_SELECTED_RUNTIME" in reasons:
                status = "PERSISTED_ROWS_FOUND_BUT_CHRONOLOGY_BLOCKS_SELECTION"
            elif "REJECT_EVENT_TIME_MISSING" in reasons:
                status = "PERSISTED_ROWS_FOUND_BUT_EVENT_TIME_BLOCKS_SELECTION"
            elif "REJECT_STATE_SCHEMA_MISSING" in reasons:
                status = "PERSISTED_ROWS_FOUND_BUT_STATE_SCHEMA_BLOCKS_SELECTION"
            else:
                status = "PERSISTED_ROWS_FOUND_BUT_SELECTION_BLOCK_REASON_MIXED"
        else:
            status = "NO_PERSISTED_FRESHNESS_RECOVERY_ROW_FOUND_ACROSS_DECLARED_DAILY_EVIDENCE_TABLES"

        per_target[target] = {
            "status": status,
            "candidate_count": len(candidates),
            "eligible_count": len(eligible),
            "rejected_count": len(rejected),
            "rejection_reasons": reasons,
            "latest_candidate": candidates[-1] if candidates else None,
            "latest_eligible": eligible[-1] if eligible else None,
            "candidates": candidates,
        }

    statuses = [v["status"] for v in per_target.values()]

    if any(s == "ELIGIBLE_RECOVERY_ROW_EXISTS_BUT_PHASE375_CONSUMER_DID_NOT_SELECT_IT" for s in statuses):
        conclusion = "CANONICAL_RECOVERY_ROWS_EXIST_AND_ARE_ELIGIBLE_CONSUMER_SELECTION_LOGIC_GAP_CONFIRMED"
    elif any(s == "PERSISTED_ROWS_FOUND_BUT_RECOVERY_SEMANTICS_BLOCK_SELECTION" for s in statuses):
        conclusion = "PERSISTED_RECOVERY_ROWS_EXIST_BUT_RECOVERY_SEMANTICS_PREVENT_CONSUMER_RECOGNITION"
    elif any(s == "PERSISTED_ROWS_FOUND_BUT_CHRONOLOGY_BLOCKS_SELECTION" for s in statuses):
        conclusion = "PERSISTED_RECOVERY_ROWS_EXIST_BUT_EVENT_CHRONOLOGY_PREVENTS_CONSUMER_SELECTION"
    elif any(s == "PERSISTED_ROWS_FOUND_BUT_EVENT_TIME_BLOCKS_SELECTION" for s in statuses):
        conclusion = "PERSISTED_RECOVERY_ROWS_EXIST_BUT_EVENT_TIME_SCHEMA_PREVENTS_SELECTION"
    elif any(s == "PERSISTED_ROWS_FOUND_BUT_STATE_SCHEMA_BLOCKS_SELECTION" for s in statuses):
        conclusion = "PERSISTED_RECOVERY_ROWS_EXIST_BUT_STATE_SCHEMA_PREVENTS_SELECTION"
    else:
        conclusion = "NO_PERSISTED_CANONICAL_RECOVERY_ROWS_FOUND_ACROSS_DECLARED_DAILY_EVIDENCE_TABLES"

    result = {
        "contract": "PHASE3719315_PHASE375_FRESHNESS_RECOVERY_PERSISTED_ROW_CANONICAL_CONSUMER_RECOGNITION_SELECTION_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_runtime": row_profile(selected_runtime, runtime["selected_table"]) if selected_runtime else None,
        "daily_contract": {
            "declared_tables": daily["declared_tables"],
            "selected_table": daily["selected_table"],
            "row_count": daily["row_count"],
            "errors": daily["errors"],
        },
        "per_declared_daily_table": per_table,
        "per_target": per_target,
        "conclusion": conclusion,
        "safety": {
            "phase375_logic_change": False,
            "supabase_mutation": False,
            "qualification_counter_mutation": False,
            "synthetic_qualification": False,
            "historical_evidence_rewrite": False,
            "broker_order_enablement": False,
            "real_money_enablement": False,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase3719315_consumer_recognition_selection.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.15 - Freshness Recovery Persisted Row Canonical Consumer Recognition + Selection Root Cause",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        "",
        "## Selected Runtime",
        f"- runtime: `{result['selected_runtime']}`",
        "",
        "## Daily Evidence Contract",
        f"- declared_tables: `{daily['declared_tables']}`",
        f"- selected_table: `{daily['selected_table']}`",
        f"- row_count: `{daily['row_count']}`",
        f"- errors: `{daily['errors']}`",
        "",
        "## Per Declared Daily Evidence Table",
    ]

    for item in per_table:
        md.append(
            f"- `{item['declared_table']}` -> selected=`{item['selected_table']}` | "
            f"rows={item['row_count']} | errors=`{item['errors']}`"
        )

    md += ["", "## Per-Domain Consumer Recognition"]

    for target in TARGETS:
        data = per_target[target]
        md += [
            "",
            f"### {target}",
            f"- status: **{data['status']}**",
            f"- candidate_count: `{data['candidate_count']}`",
            f"- eligible_count: `{data['eligible_count']}`",
            f"- rejected_count: `{data['rejected_count']}`",
            f"- rejection_reasons: `{data['rejection_reasons']}`",
            f"- latest_candidate: `{data['latest_candidate']}`",
            f"- latest_eligible: `{data['latest_eligible']}`",
        ]

    md += [
        "",
        "## Safety Contract",
        "- Phase 3.7.5 Logic Change: **NO**",
        "- Supabase Mutation: **NO**",
        "- Qualification Counter Mutation: **NO**",
        "- Synthetic Qualification: **NO**",
        "- Historical Evidence Rewrite: **NO**",
        "- Broker Order Enablement: **NO**",
        "- Real-Money Enablement: **NO**",
    ]

    (OUT / "phase3719315_consumer_recognition_selection.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719315_CONCLUSION=" + conclusion)
    for target in TARGETS:
        data = per_target[target]
        print(target.upper() + "_STATUS=" + data["status"])
        print(target.upper() + "_CANDIDATES=" + str(data["candidate_count"]))
        print(target.upper() + "_ELIGIBLE=" + str(data["eligible_count"]))
        print(target.upper() + "_REJECTION_REASONS=" + json.dumps(data["rejection_reasons"], ensure_ascii=False))

if __name__ == "__main__":
    main()
