from __future__ import annotations
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase371937"
MODE = "READ_ONLY_NO_MUTATION"

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_exec_path_target", P375)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def first(row: Dict[str, Any], *fields: str) -> str:
    if not row:
        return ""
    for k in fields:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""

def event_time(row: Dict[str, Any]) -> str:
    return first(row, "updated_at", "created_at", "event_time", "recorded_at", "timestamp", "ts")

def row_id(row: Dict[str, Any]) -> str:
    return first(row, "id", "runtime_id", "supervision_id", "run_id")

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()

    required = ["inspect","latest","runtime_supervision_reconstruct","RUNTIME_TABLES","ACTIVATION_TABLES","MASTER_CYCLE_TABLES"]
    for name in required:
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    runtime_table, run_rows, run_errors = mod.inspect(mod.RUNTIME_TABLES, portfolio_scoped=True)
    activation_table, act_rows, act_errors = mod.inspect(mod.ACTIVATION_TABLES, portfolio_scoped=True)
    master_table, mst_rows, mst_errors = mod.inspect(mod.MASTER_CYCLE_TABLES, portfolio_scoped=True)

    runtime_row = mod.latest(run_rows)
    activation_row = mod.latest(act_rows)
    master_row = mod.latest(mst_rows)

    runtime_ok, runtime_state, runtime_reason = mod.runtime_supervision_reconstruct(runtime_row)

    helper_present = hasattr(mod, "_phase371936_stale_revocation_superseded")
    helper_invoked = False
    eligible = False
    helper_error = None

    if helper_present:
        try:
            helper_invoked = True
            eligible = bool(mod._phase371936_stale_revocation_superseded(runtime_row, activation_row, master_row))
        except Exception as exc:
            helper_error = f"{type(exc).__name__}: {exc}"

    runtime_time = event_time(runtime_row)
    activation_time = event_time(activation_row)
    master_time = event_time(master_row)

    activation_is_newer = bool(runtime_time and activation_time and activation_time > runtime_time)
    master_is_newer = bool(runtime_time and master_time and master_time > runtime_time)
    chronology_unambiguous = bool(runtime_time and (activation_time or master_time))

    live_critical = False
    if runtime_row:
        if runtime_row.get("open_incident") is True:
            live_critical = True
        severity = str(runtime_row.get("incident_severity") or "").strip().upper()
        if severity in {"CRITICAL","HIGH","SEVERE","FATAL"}:
            live_critical = True
        critical = runtime_row.get("critical_failures")
        if isinstance(critical, (list, tuple, set, dict)) and len(critical) > 0:
            live_critical = True
        elif isinstance(critical, str) and critical.strip().upper() not in {"", "[]", "{}", "NONE", "NULL"}:
            live_critical = True
        elif isinstance(critical, (int, float)) and critical > 0:
            live_critical = True

    source = P375.read_text(encoding="utf-8")
    bridge_present = "PHASE371936_STALE_REVOCATION_RECOVERY_BRIDGE" in source
    bridge_condition = (not runtime_ok) and runtime_reason == "EXPLICIT_BLOCK_STATE" and eligible

    if not helper_present:
        rejection = "RECOVERY_HELPER_NOT_PRESENT"
    elif helper_error:
        rejection = "RECOVERY_HELPER_ERROR"
    elif live_critical:
        rejection = "LIVE_CRITICAL_INCIDENT_FAIL_CLOSED"
    elif not chronology_unambiguous:
        rejection = "CHRONOLOGY_AMBIGUOUS_FAIL_CLOSED"
    elif not eligible:
        if not activation_is_newer and not master_is_newer:
            rejection = "NO_STRICTLY_NEWER_UPSTREAM_RECOVERY"
        else:
            rejection = "RECOVERY_ELIGIBILITY_REJECTED"
    elif not bridge_present:
        rejection = "RECOVERY_BRIDGE_NOT_PRESENT"
    elif not bridge_condition:
        rejection = "RECOVERY_BRIDGE_CONDITION_NOT_MET"
    else:
        rejection = "NONE_EXPECTED_TO_APPLY"

    result = {
        "contract": "PHASE371937_PHASE375_STALE_REVOCATION_RECOVERY_EXECUTION_PATH_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tables": {"runtime": runtime_table, "activation": activation_table, "master": master_table},
        "read_errors": {"runtime": run_errors or [], "activation": act_errors or [], "master": mst_errors or []},
        "recovery_execution": {
            "helper_present": helper_present,
            "helper_invoked": helper_invoked,
            "helper_error": helper_error,
            "stale_revocation_recovery_eligible": eligible,
            "bridge_present": bridge_present,
            "bridge_condition_should_apply": bridge_condition,
            "recovery_rejection_reason": rejection,
        },
        "chronology": {
            "selected_runtime_row_id": row_id(runtime_row),
            "runtime_event_time": runtime_time,
            "activation_row_id": row_id(activation_row),
            "activation_recovery_event_time": activation_time,
            "activation_recovery_is_newer": activation_is_newer,
            "master_row_id": row_id(master_row),
            "master_recovery_event_time": master_time,
            "master_recovery_is_newer": master_is_newer,
            "chronology_unambiguous": chronology_unambiguous,
        },
        "safety": {
            "live_critical_incident_present": live_critical,
            "runtime_safety_revocation_triggered": runtime_row.get("safety_revocation_triggered") if runtime_row else None,
            "phase375_logic_change": False,
            "supabase_mutation": False,
            "qualification_counter_mutation": False,
            "synthetic_qualification": False,
            "historical_evidence_rewrite": False,
            "broker_order_enablement": False,
            "real_money_enablement": False,
        },
        "final_decision_observed": {
            "runtime_supervision": bool(runtime_ok),
            "runtime_supervision_state": runtime_state,
            "runtime_reconstruction_reason": runtime_reason,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase371937_execution_path.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Phase 3.7.19.3.7 - Phase 3.7.5 Stale Revocation Recovery Execution Path Diagnostic",
        "",
        f"- Mode: **{MODE}**",
        "",
        "## Recovery Execution",
        f"- recovery_helper_present: `{helper_present}`",
        f"- recovery_helper_invoked: `{helper_invoked}`",
        f"- stale_revocation_recovery_eligible: `{eligible}`",
        f"- recovery_bridge_present: `{bridge_present}`",
        f"- recovery_bridge_condition_should_apply: `{bridge_condition}`",
        f"- recovery_rejection_reason: `{rejection}`",
        f"- helper_error: `{helper_error}`",
        "",
        "## Chronology",
        f"- selected_runtime_row_id: `{row_id(runtime_row)}`",
        f"- runtime_event_time: `{runtime_time}`",
        f"- activation_recovery_event_time: `{activation_time}`",
        f"- activation_recovery_is_newer: `{activation_is_newer}`",
        f"- master_recovery_event_time: `{master_time}`",
        f"- master_recovery_is_newer: `{master_is_newer}`",
        f"- chronology_unambiguous: `{chronology_unambiguous}`",
        "",
        "## Safety",
        f"- live_critical_incident_present: `{live_critical}`",
        f"- runtime_safety_revocation_triggered: `{runtime_row.get('safety_revocation_triggered') if runtime_row else None}`",
        "",
        "## Final Decision Observed",
        f"- final_runtime_supervision: `{bool(runtime_ok)}`",
        f"- final_runtime_supervision_state: `{runtime_state}`",
        f"- final_runtime_reconstruction_reason: `{runtime_reason}`",
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
    (OUT / "phase371937_execution_path.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("RECOVERY_HELPER_PRESENT=" + str(helper_present))
    print("RECOVERY_HELPER_INVOKED=" + str(helper_invoked))
    print("STALE_REVOCATION_RECOVERY_ELIGIBLE=" + str(eligible))
    print("RECOVERY_BRIDGE_PRESENT=" + str(bridge_present))
    print("RECOVERY_BRIDGE_CONDITION_SHOULD_APPLY=" + str(bridge_condition))
    print("RECOVERY_REJECTION_REASON=" + rejection)
    print("RUNTIME_EVENT_TIME=" + runtime_time)
    print("ACTIVATION_RECOVERY_EVENT_TIME=" + activation_time)
    print("ACTIVATION_RECOVERY_IS_NEWER=" + str(activation_is_newer))
    print("MASTER_RECOVERY_EVENT_TIME=" + master_time)
    print("MASTER_RECOVERY_IS_NEWER=" + str(master_is_newer))
    print("LIVE_CRITICAL_INCIDENT_PRESENT=" + str(live_critical))
    print("FINAL_RUNTIME_SUPERVISION=" + str(bool(runtime_ok)))
    print("FINAL_RUNTIME_SUPERVISION_STATE=" + str(runtime_state))
    print("FINAL_RUNTIME_RECONSTRUCTION_REASON=" + str(runtime_reason))

if __name__ == "__main__":
    main()
