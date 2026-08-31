from __future__ import annotations
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase371935"
MODE = "READ_ONLY_NO_MUTATION"

TABLE_GROUPS = {
    "runtime": "RUNTIME_TABLES",
    "activation": "ACTIVATION_TABLES",
    "master": "MASTER_CYCLE_TABLES",
}

DATE_FIELDS = ("supervision_date","run_date","business_date","cycle_date","date")
TIME_FIELDS = ("updated_at","created_at","event_time","recorded_at","timestamp","ts")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_rootcause_target", P375)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def first(row: Dict[str, Any], fields) -> str:
    for k in fields:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""

def business_date(row: Dict[str, Any]) -> str:
    x = first(row, DATE_FIELDS)
    if x:
        return x[:10]
    t = first(row, TIME_FIELDS)
    return t[:10] if len(t) >= 10 else "UNKNOWN_DATE"

def event_time(row: Dict[str, Any]) -> str:
    return first(row, TIME_FIELDS)

def row_id(row: Dict[str, Any]) -> str:
    for k in ("id","runtime_id","supervision_id","run_id"):
        if row.get(k) is not None:
            return str(row.get(k))
    return ""

def snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "id","portfolio_id","strategy_version",
        "supervision_state","runtime_state","operational_state","state","status",
        "activation_state","master_cycle_state","qualification_state",
        "safety_revocation_triggered","safety_revocation_reason","revocation_reason",
        "fail_closed_policy","readiness_state","health_state","incident_severity",
        "warning_failures","critical_failures","open_incident",
        "reason_codes","contract","canonical_dates","evidence_sha256",
        "created_at","updated_at","supervision_date","run_date","business_date"
    )
    return {k: row.get(k) for k in keys if k in row}

def inspect_group(mod, attr: str) -> Tuple[Any, List[Dict[str, Any]], List[Any]]:
    tables = getattr(mod, attr, [])
    table, rows, errors = mod.inspect(tables, portfolio_scoped=True)
    return table, [r for r in (rows or []) if isinstance(r, dict)], list(errors or [])

def classify_runtime(mod, row: Dict[str, Any]) -> Dict[str, Any]:
    ok, state, reason = mod.runtime_supervision_reconstruct(row)
    return {
        "id": row_id(row),
        "business_date": business_date(row),
        "event_time": event_time(row),
        "ok": bool(ok),
        "state": state,
        "reason": reason,
        "row": snapshot(row),
    }

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect","latest","runtime_supervision_reconstruct","RUNTIME_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    runtime_table, runtime_rows, runtime_errors = inspect_group(mod, "RUNTIME_TABLES")
    selected = mod.latest(runtime_rows)
    selected_class = classify_runtime(mod, selected) if selected else None

    all_runtime = [classify_runtime(mod, r) for r in runtime_rows]
    all_runtime = sorted(all_runtime, key=lambda x: (x["event_time"], x["business_date"], x["id"]))

    # Inspect activation/master context using exactly Phase 3.7.5's own adapters.
    activation_table = activation_rows = activation_errors = None
    master_table = master_rows = master_errors = None

    if hasattr(mod, "ACTIVATION_TABLES"):
        activation_table, activation_rows, activation_errors = inspect_group(mod, "ACTIVATION_TABLES")
    else:
        activation_rows, activation_errors = [], []

    if hasattr(mod, "MASTER_CYCLE_TABLES"):
        master_table, master_rows, master_errors = inspect_group(mod, "MASTER_CYCLE_TABLES")
    else:
        master_rows, master_errors = [], []

    latest_activation = mod.latest(activation_rows) if activation_rows else None
    latest_master = mod.latest(master_rows) if master_rows else None

    # Search runtime history for the most recent revocation=True row and any later row that clears it.
    revocation_rows = []
    clear_rows = []
    for x in all_runtime:
        r = x["row"]
        if r.get("safety_revocation_triggered") is True:
            revocation_rows.append(x)
        if r.get("safety_revocation_triggered") is False and x["ok"]:
            clear_rows.append(x)

    latest_revocation = revocation_rows[-1] if revocation_rows else None
    later_clear_after_revocation = []
    if latest_revocation:
        key0 = (latest_revocation["event_time"], latest_revocation["business_date"], latest_revocation["id"])
        for x in clear_rows:
            keyx = (x["event_time"], x["business_date"], x["id"])
            if keyx > key0:
                later_clear_after_revocation.append(x)

    # Evaluate whether upstream canonical rows indicate recovery while runtime remains blocked.
    upstream_recovery_signals = {}
    if latest_activation:
        upstream_recovery_signals["activation"] = snapshot(latest_activation)
    if latest_master:
        upstream_recovery_signals["master"] = snapshot(latest_master)

    selected_blocked = bool(selected_class and not selected_class["ok"])
    has_later_clear = bool(later_clear_after_revocation)

    activation_text = json.dumps(snapshot(latest_activation) if latest_activation else {}, ensure_ascii=False).upper()
    master_text = json.dumps(snapshot(latest_master) if latest_master else {}, ensure_ascii=False).upper()

    activation_recovered = any(tok in activation_text for tok in ("ACTIVE", "READY", "PASS", "OBSERVATION"))
    master_recovered = any(tok in master_text for tok in ("PASS", "READY", "COMPLETED", "QUALIFIED"))

    if selected_blocked and latest_revocation and has_later_clear:
        conclusion = "REVOCATION_HAS_LATER_RUNTIME_CLEAR_BUT_BLOCKED_SELECTION_PERSISTS"
    elif selected_blocked and latest_revocation and (activation_recovered or master_recovered):
        conclusion = "UPSTREAM_RECOVERY_PRESENT_RUNTIME_REVOCATION_NOT_RECONCILED"
    elif selected_blocked and latest_revocation:
        conclusion = "ACTIVE_RUNTIME_REVOCATION_NO_RECOVERY_EVIDENCE_FOUND"
    elif selected_blocked:
        conclusion = "BLOCKED_RUNTIME_WITHOUT_EXPLICIT_REVOCATION_PROVENANCE"
    else:
        conclusion = "RUNTIME_SUPERVISION_NOT_BLOCKED"

    result = {
        "contract": "PHASE371935_RUNTIME_SUPERVISION_EXPLICIT_BLOCK_SAFETY_REVOCATION_PROVENANCE_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "table": runtime_table,
            "errors": runtime_errors,
            "row_count": len(runtime_rows),
            "selected": selected_class,
            "all_rows": all_runtime,
            "latest_revocation": latest_revocation,
            "later_clear_after_revocation": later_clear_after_revocation,
        },
        "activation": {
            "table": activation_table,
            "errors": activation_errors,
            "latest": snapshot(latest_activation) if latest_activation else None,
        },
        "master": {
            "table": master_table,
            "errors": master_errors,
            "latest": snapshot(latest_master) if latest_master else None,
        },
        "signals": {
            "activation_recovered": activation_recovered,
            "master_recovered": master_recovered,
            "later_runtime_clear_present": has_later_clear,
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
    (OUT / "phase371935_root_cause.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = [
        "# Phase 3.7.19.3.5 - Runtime Supervision Explicit Block / Safety Revocation Provenance Root Cause",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        f"- Runtime Table: `{runtime_table}`",
        f"- Runtime Row Count: **{len(runtime_rows)}**",
        f"- Runtime Read Errors: `{runtime_errors}`",
        "",
        "## Selected Runtime Row",
        "",
    ]
    if selected_class:
        md += [
            f"- id: `{selected_class['id']}`",
            f"- business_date: `{selected_class['business_date']}`",
            f"- event_time: `{selected_class['event_time']}`",
            f"- reconstructed_ok: `{selected_class['ok']}`",
            f"- reconstructed_state: `{selected_class['state']}`",
            f"- reconstruction_reason: `{selected_class['reason']}`",
            f"- row: `{selected_class['row']}`",
        ]
    else:
        md.append("- None")

    md += ["", "## Latest Revocation Provenance", ""]
    if latest_revocation:
        md += [
            f"- id: `{latest_revocation['id']}`",
            f"- business_date: `{latest_revocation['business_date']}`",
            f"- event_time: `{latest_revocation['event_time']}`",
            f"- state: `{latest_revocation['state']}`",
            f"- reason: `{latest_revocation['reason']}`",
            f"- row: `{latest_revocation['row']}`",
        ]
    else:
        md.append("- None")

    md += ["", "## Later Runtime Clear Rows", ""]
    if later_clear_after_revocation:
        for x in later_clear_after_revocation:
            md.append(f"- {x['business_date']} | {x['event_time']} | {x['state']} | {x['reason']} | id {x['id']}")
    else:
        md.append("- None")

    md += ["", "## Upstream Canonical Context", ""]
    md.append(f"- Activation Table: `{activation_table}`")
    md.append(f"- Latest Activation: `{snapshot(latest_activation) if latest_activation else None}`")
    md.append(f"- Master Table: `{master_table}`")
    md.append(f"- Latest Master: `{snapshot(latest_master) if latest_master else None}`")
    md.append(f"- Activation Recovery Signal: **{'YES' if activation_recovered else 'NO'}**")
    md.append(f"- Master Recovery Signal: **{'YES' if master_recovered else 'NO'}**")

    md += [
        "",
        "## Safety",
        "",
        "- Phase 3.7.5 Logic Change: **NO**",
        "- Supabase Mutation: **NO**",
        "- Qualification Counter Mutation: **NO**",
        "- Synthetic Qualification: **NO**",
        "- Historical Evidence Rewrite: **NO**",
        "- Broker Order Enablement: **NO**",
        "- Real-Money Enablement: **NO**",
    ]

    (OUT / "phase371935_root_cause.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("PHASE371935_CONCLUSION=" + conclusion)
    print("SELECTED_RUNTIME_TABLE=" + str(runtime_table))
    print("SELECTED_RUNTIME_ROW_ID=" + str(selected_class["id"] if selected_class else None))
    print("SELECTED_RUNTIME_STATE=" + str(selected_class["state"] if selected_class else None))
    print("SELECTED_RUNTIME_REASON=" + str(selected_class["reason"] if selected_class else None))
    print("LATEST_REVOCATION_ROW_ID=" + str(latest_revocation["id"] if latest_revocation else None))
    print("LATER_RUNTIME_CLEAR_ROWS=" + str(len(later_clear_after_revocation)))
    print("ACTIVATION_RECOVERY_SIGNAL=" + ("YES" if activation_recovered else "NO"))
    print("MASTER_RECOVERY_SIGNAL=" + ("YES" if master_recovered else "NO"))

if __name__ == "__main__":
    main()
