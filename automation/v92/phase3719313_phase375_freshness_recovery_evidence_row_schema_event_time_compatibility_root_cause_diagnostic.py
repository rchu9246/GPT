from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719313"
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
    spec = importlib.util.spec_from_file_location("phase375_row_schema_time_target", P375)
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

def normalize_state_values(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key in STATE_FIELDS + FAIL_FIELDS:
        if key in row:
            out[key] = row.get(key)
    return out

def recovery_semantics(row: Dict[str, Any]) -> Dict[str, Any]:
    vals = normalize_state_values(row)
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
        "state_values": vals,
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

def row_profile(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row_id(row),
        "business_date": business_date(row),
        "event_time": event_time(row),
        "time_field_present": next((k for k in TIME_FIELDS if row.get(k) not in (None, "")), None),
        "date_field_present": next((k for k in DATE_FIELDS if row.get(k) not in (None, "")), None),
        "target_hits": target_hits(row),
        "schema_keys": sorted(row.keys()),
        "recovery_semantics": recovery_semantics(row),
    }

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()

    for name in ("inspect", "latest", "RUNTIME_TABLES", "DAILY_EVIDENCE_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    runtime = inspect_contract(mod, "RUNTIME_TABLES")
    daily = inspect_contract(mod, "DAILY_EVIDENCE_TABLES")
    activation = inspect_contract(mod, "ACTIVATION_TABLES")
    master = inspect_contract(mod, "MASTER_CYCLE_TABLES")

    selected_runtime = mod.latest(runtime["rows"]) if runtime["rows"] else None
    runtime_key = chrono_key(selected_runtime) if selected_runtime else ("", "", "")

    daily_profiles = [row_profile(r) for r in daily["rows"]]

    per_target = {}
    for target in TARGETS:
        matching = []
        later = []
        later_recognizable = []
        schema_mismatch = []
        event_time_missing = []

        for row in daily["rows"]:
            if target not in target_hits(row):
                continue

            prof = row_profile(row)
            matching.append(prof)

            if not prof["time_field_present"]:
                event_time_missing.append(prof)

            if prof["event_time"] and selected_runtime and chrono_key(row) > runtime_key:
                later.append(prof)
                if prof["recovery_semantics"]["recognized_recovery_shape"]:
                    later_recognizable.append(prof)

            required_shape = bool(
                prof["time_field_present"]
                and prof["recovery_semantics"]["state_values"]
            )
            if not required_shape:
                schema_mismatch.append(prof)

        if later_recognizable:
            status = "LATER_RECOVERY_ROW_EXISTS_AND_IS_RECOGNIZABLE"
        elif later:
            status = "LATER_ROW_EXISTS_BUT_RECOVERY_SEMANTICS_NOT_RECOGNIZED"
        elif matching and event_time_missing:
            status = "RECOVERY_EVIDENCE_ROWS_PRESENT_BUT_EVENT_TIME_MISSING"
        elif matching and schema_mismatch:
            status = "RECOVERY_EVIDENCE_ROWS_PRESENT_BUT_SCHEMA_INCOMPATIBLE"
        elif matching:
            status = "RECOVERY_ROWS_PRESENT_BUT_NOT_NEWER_THAN_SELECTED_RUNTIME"
        else:
            status = "NO_RECOVERY_ROW_FOUND_IN_DAILY_EVIDENCE_CONTRACT"

        per_target[target] = {
            "status": status,
            "matching_rows": matching,
            "later_rows": later,
            "later_recognizable_recovery_rows": later_recognizable,
            "event_time_missing_rows": event_time_missing,
            "schema_mismatch_rows": schema_mismatch,
        }

    statuses = [v["status"] for v in per_target.values()]

    if any(s == "LATER_ROW_EXISTS_BUT_RECOVERY_SEMANTICS_NOT_RECOGNIZED" for s in statuses):
        conclusion = "RECOVERY_ROWS_EXIST_BUT_STATE_SEMANTICS_INCOMPATIBLE_WITH_PHASE375"
    elif any(s == "RECOVERY_EVIDENCE_ROWS_PRESENT_BUT_EVENT_TIME_MISSING" for s in statuses):
        conclusion = "RECOVERY_ROWS_EXIST_BUT_EVENT_TIME_COMPATIBILITY_GAP_PREVENTS_SUPERSESSION"
    elif any(s == "RECOVERY_EVIDENCE_ROWS_PRESENT_BUT_SCHEMA_INCOMPATIBLE" for s in statuses):
        conclusion = "RECOVERY_ROWS_EXIST_BUT_ROW_SCHEMA_INCOMPATIBLE_WITH_PHASE375"
    elif any(s == "RECOVERY_ROWS_PRESENT_BUT_NOT_NEWER_THAN_SELECTED_RUNTIME" for s in statuses):
        conclusion = "RECOVERY_ROWS_EXIST_BUT_ARE_NOT_NEWER_THAN_SELECTED_RUNTIME"
    elif all(s == "LATER_RECOVERY_ROW_EXISTS_AND_IS_RECOGNIZABLE" for s in statuses):
        conclusion = "RECOVERY_ROWS_ARE_PRESENT_NEWER_AND_RECOGNIZABLE_INVESTIGATE_CONSUMER_SELECTION_LOGIC"
    else:
        conclusion = "NO_CANONICAL_RECOVERY_ROWS_FOUND_FOR_ONE_OR_MORE_FRESHNESS_DOMAINS"

    result = {
        "contract": "PHASE3719313_PHASE375_FRESHNESS_RECOVERY_EVIDENCE_ROW_SCHEMA_EVENT_TIME_COMPATIBILITY_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_runtime": row_profile(selected_runtime) if selected_runtime else None,
        "contracts": {
            "RUNTIME_TABLES": {k: v for k, v in runtime.items() if k != "rows"},
            "DAILY_EVIDENCE_TABLES": {k: v for k, v in daily.items() if k != "rows"},
            "ACTIVATION_TABLES": {k: v for k, v in activation.items() if k != "rows"},
            "MASTER_CYCLE_TABLES": {k: v for k, v in master.items() if k != "rows"},
        },
        "daily_row_profiles": daily_profiles,
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
    (OUT / "phase3719313_row_schema_event_time.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.13 - Freshness Recovery Evidence Row Schema + Event-Time Compatibility Root Cause",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        "",
        "## Selected Runtime",
        f"- runtime: `{result['selected_runtime']}`",
        "",
        "## Contract Snapshot",
    ]

    for name, data in result["contracts"].items():
        md.append(
            f"- {name}: declared=`{data['declared_tables']}` | selected=`{data['selected_table']}` | "
            f"rows={data['row_count']} | errors=`{data['errors']}`"
        )

    md += ["", "## Per-Domain Compatibility"]

    for target in TARGETS:
        data = per_target[target]
        md += [
            "",
            f"### {target}",
            f"- status: **{data['status']}**",
            f"- matching_rows: `{len(data['matching_rows'])}`",
            f"- later_rows: `{len(data['later_rows'])}`",
            f"- later_recognizable_recovery_rows: `{len(data['later_recognizable_recovery_rows'])}`",
            f"- event_time_missing_rows: `{len(data['event_time_missing_rows'])}`",
            f"- schema_mismatch_rows: `{len(data['schema_mismatch_rows'])}`",
            f"- latest_matching_row: `{data['matching_rows'][-1] if data['matching_rows'] else None}`",
            f"- latest_later_row: `{data['later_rows'][-1] if data['later_rows'] else None}`",
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

    (OUT / "phase3719313_row_schema_event_time.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719313_CONCLUSION=" + conclusion)
    if selected_runtime:
        print("SELECTED_RUNTIME_ROW_ID=" + row_id(selected_runtime))
        print("SELECTED_RUNTIME_EVENT_TIME=" + event_time(selected_runtime))
    for target in TARGETS:
        data = per_target[target]
        print(target.upper() + "_STATUS=" + data["status"])
        print(target.upper() + "_MATCHING_ROWS=" + str(len(data["matching_rows"])))
        print(target.upper() + "_LATER_ROWS=" + str(len(data["later_rows"])))
        print(target.upper() + "_LATER_RECOGNIZABLE_RECOVERY_ROWS=" + str(len(data["later_recognizable_recovery_rows"])))
        print(target.upper() + "_EVENT_TIME_MISSING_ROWS=" + str(len(data["event_time_missing_rows"])))
        print(target.upper() + "_SCHEMA_MISMATCH_ROWS=" + str(len(data["schema_mismatch_rows"])))

if __name__ == "__main__":
    main()
