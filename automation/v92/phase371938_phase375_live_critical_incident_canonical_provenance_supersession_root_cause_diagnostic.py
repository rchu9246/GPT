from __future__ import annotations
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase371938"
MODE = "READ_ONLY_NO_MUTATION"

TIME_FIELDS = ("updated_at","created_at","event_time","recorded_at","timestamp","ts")
DATE_FIELDS = ("supervision_date","run_date","business_date","cycle_date","date")

INCIDENT_FIELDS = (
    "open_incident",
    "incident_severity",
    "critical_failures",
    "warning_failures",
    "fail_closed_policy",
    "safety_revocation_triggered",
    "safety_revocation_reason",
    "revocation_reason",
    "reason_codes",
    "health_state",
    "readiness_state",
    "supervision_state",
    "runtime_state",
    "operational_state",
    "state",
    "status",
)

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_live_incident_diag_target", P375)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def first(row: Dict[str, Any], fields) -> str:
    if not row:
        return ""
    for k in fields:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""

def event_time(row: Dict[str, Any]) -> str:
    return first(row, TIME_FIELDS)

def business_date(row: Dict[str, Any]) -> str:
    x = first(row, DATE_FIELDS)
    if x:
        return x[:10]
    t = event_time(row)
    return t[:10] if len(t) >= 10 else "UNKNOWN_DATE"

def row_id(row: Dict[str, Any]) -> str:
    for k in ("id","runtime_id","supervision_id","incident_id","run_id"):
        if row and row.get(k) is not None:
            return str(row.get(k))
    return ""

def incident_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    base = {
        "id": row_id(row),
        "business_date": business_date(row),
        "event_time": event_time(row),
    }
    for k in INCIDENT_FIELDS:
        if k in row:
            base[k] = row.get(k)
    return base

def live_critical_components(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {
            "open_incident_true": False,
            "critical_severity": False,
            "critical_failures_present": False,
            "live_critical_incident_present": False,
        }

    open_incident_true = row.get("open_incident") is True

    severity = str(row.get("incident_severity") or "").strip().upper()
    critical_severity = severity in {"CRITICAL", "HIGH", "SEVERE", "FATAL"}

    critical = row.get("critical_failures")
    critical_failures_present = False
    if isinstance(critical, (list, tuple, set, dict)):
        critical_failures_present = len(critical) > 0
    elif isinstance(critical, str):
        critical_failures_present = critical.strip().upper() not in {"", "[]", "{}", "NONE", "NULL"}
    elif isinstance(critical, (int, float)):
        critical_failures_present = critical > 0

    return {
        "open_incident_true": open_incident_true,
        "incident_severity_raw": row.get("incident_severity"),
        "critical_severity": critical_severity,
        "critical_failures_raw": critical,
        "critical_failures_present": critical_failures_present,
        "live_critical_incident_present": open_incident_true or critical_severity or critical_failures_present,
    }

def chronological_key(row: Dict[str, Any]):
    return (event_time(row), business_date(row), row_id(row))

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect","latest","runtime_supervision_reconstruct","RUNTIME_TABLES","ACTIVATION_TABLES","MASTER_CYCLE_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    runtime_table, runtime_rows, runtime_errors = mod.inspect(mod.RUNTIME_TABLES, portfolio_scoped=True)
    activation_table, activation_rows, activation_errors = mod.inspect(mod.ACTIVATION_TABLES, portfolio_scoped=True)
    master_table, master_rows, master_errors = mod.inspect(mod.MASTER_CYCLE_TABLES, portfolio_scoped=True)

    runtime_rows = [r for r in (runtime_rows or []) if isinstance(r, dict)]
    activation_rows = [r for r in (activation_rows or []) if isinstance(r, dict)]
    master_rows = [r for r in (master_rows or []) if isinstance(r, dict)]

    selected_runtime = mod.latest(runtime_rows)
    selected_activation = mod.latest(activation_rows)
    selected_master = mod.latest(master_rows)

    selected_ok, selected_state, selected_reason = mod.runtime_supervision_reconstruct(selected_runtime)

    all_runtime = []
    for r in runtime_rows:
        ok, state, reason = mod.runtime_supervision_reconstruct(r)
        all_runtime.append({
            "id": row_id(r),
            "business_date": business_date(r),
            "event_time": event_time(r),
            "reconstructed_ok": bool(ok),
            "reconstructed_state": state,
            "reconstruction_reason": reason,
            "incident": incident_snapshot(r),
            "components": live_critical_components(r),
        })
    all_runtime.sort(key=lambda x: (x["event_time"], x["business_date"], x["id"]))

    selected_components = live_critical_components(selected_runtime)
    selected_key = chronological_key(selected_runtime) if selected_runtime else ("","","")

    later_runtime_rows = []
    later_clear_candidates = []

    for r in runtime_rows:
        if not selected_runtime:
            continue
        if chronological_key(r) > selected_key:
            info = {
                "id": row_id(r),
                "business_date": business_date(r),
                "event_time": event_time(r),
                "incident": incident_snapshot(r),
                "components": live_critical_components(r),
            }
            later_runtime_rows.append(info)
            comp = info["components"]
            if not comp["live_critical_incident_present"]:
                later_clear_candidates.append(info)

    activation_newer = bool(selected_runtime and selected_activation and chronological_key(selected_activation) > selected_key)
    master_newer = bool(selected_runtime and selected_master and chronological_key(selected_master) > selected_key)

    activation_snapshot = incident_snapshot(selected_activation)
    master_snapshot = incident_snapshot(selected_master)

    if selected_components["live_critical_incident_present"] and later_clear_candidates:
        conclusion = "LIVE_CRITICAL_INCIDENT_HAS_LATER_RUNTIME_CLEAR_CANDIDATE"
    elif selected_components["live_critical_incident_present"] and (activation_newer or master_newer):
        conclusion = "LIVE_CRITICAL_INCIDENT_PERSISTS_DESPITE_NEWER_UPSTREAM_RECOVERY_CONTEXT"
    elif selected_components["live_critical_incident_present"]:
        conclusion = "LIVE_CRITICAL_INCIDENT_CURRENTLY_CANONICAL_NO_CLEAR_EVIDENCE_FOUND"
    else:
        conclusion = "NO_LIVE_CRITICAL_INCIDENT_ON_SELECTED_RUNTIME_ROW"

    result = {
        "contract": "PHASE371938_PHASE375_LIVE_CRITICAL_INCIDENT_CANONICAL_PROVENANCE_SUPERSESSION_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tables": {
            "runtime": runtime_table,
            "activation": activation_table,
            "master": master_table,
        },
        "read_errors": {
            "runtime": runtime_errors or [],
            "activation": activation_errors or [],
            "master": master_errors or [],
        },
        "selected_runtime": {
            "row": incident_snapshot(selected_runtime),
            "reconstructed_ok": bool(selected_ok),
            "reconstructed_state": selected_state,
            "reconstruction_reason": selected_reason,
            "live_critical_components": selected_components,
        },
        "provenance": {
            "all_runtime_rows": all_runtime,
            "later_runtime_rows": later_runtime_rows,
            "later_runtime_clear_candidates": later_clear_candidates,
        },
        "upstream_context": {
            "activation_latest": activation_snapshot,
            "master_latest": master_snapshot,
            "activation_is_newer_than_runtime": activation_newer,
            "master_is_newer_than_runtime": master_newer,
        },
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
    (OUT / "phase371938_live_critical_incident_root_cause.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.8 - Live Critical Incident Canonical Provenance + Supersession Root Cause",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        "",
        "## Selected Runtime",
        f"- id: `{row_id(selected_runtime)}`",
        f"- business_date: `{business_date(selected_runtime) if selected_runtime else ''}`",
        f"- event_time: `{event_time(selected_runtime) if selected_runtime else ''}`",
        f"- reconstructed_ok: `{bool(selected_ok)}`",
        f"- reconstructed_state: `{selected_state}`",
        f"- reconstruction_reason: `{selected_reason}`",
        f"- open_incident_true: `{selected_components['open_incident_true']}`",
        f"- incident_severity_raw: `{selected_components.get('incident_severity_raw')}`",
        f"- critical_severity: `{selected_components['critical_severity']}`",
        f"- critical_failures_raw: `{selected_components.get('critical_failures_raw')}`",
        f"- critical_failures_present: `{selected_components['critical_failures_present']}`",
        f"- live_critical_incident_present: `{selected_components['live_critical_incident_present']}`",
        "",
        "## Upstream Context",
        f"- activation_is_newer_than_runtime: `{activation_newer}`",
        f"- master_is_newer_than_runtime: `{master_newer}`",
        f"- latest_activation: `{activation_snapshot}`",
        f"- latest_master: `{master_snapshot}`",
        "",
        "## Later Runtime Rows",
    ]

    if later_runtime_rows:
        for x in later_runtime_rows:
            md.append(
                f"- id={x['id']} | {x['event_time']} | live_critical={x['components']['live_critical_incident_present']} | "
                f"open_incident={x['components']['open_incident_true']} | severity={x['components'].get('incident_severity_raw')} | "
                f"critical_failures={x['components'].get('critical_failures_raw')}"
            )
    else:
        md.append("- None")

    md += ["", "## Later Runtime Clear Candidates"]
    if later_clear_candidates:
        for x in later_clear_candidates:
            md.append(f"- id={x['id']} | {x['event_time']} | {x['incident']}")
    else:
        md.append("- None")

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

    (OUT / "phase371938_live_critical_incident_root_cause.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE371938_CONCLUSION=" + conclusion)
    print("SELECTED_RUNTIME_ROW_ID=" + str(row_id(selected_runtime)))
    print("OPEN_INCIDENT_TRUE=" + str(selected_components["open_incident_true"]))
    print("INCIDENT_SEVERITY_RAW=" + str(selected_components.get("incident_severity_raw")))
    print("CRITICAL_SEVERITY=" + str(selected_components["critical_severity"]))
    print("CRITICAL_FAILURES_RAW=" + str(selected_components.get("critical_failures_raw")))
    print("CRITICAL_FAILURES_PRESENT=" + str(selected_components["critical_failures_present"]))
    print("LIVE_CRITICAL_INCIDENT_PRESENT=" + str(selected_components["live_critical_incident_present"]))
    print("ACTIVATION_IS_NEWER_THAN_RUNTIME=" + str(activation_newer))
    print("MASTER_IS_NEWER_THAN_RUNTIME=" + str(master_newer))
    print("LATER_RUNTIME_ROWS=" + str(len(later_runtime_rows)))
    print("LATER_RUNTIME_CLEAR_CANDIDATES=" + str(len(later_clear_candidates)))

if __name__ == "__main__":
    main()
