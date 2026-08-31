from __future__ import annotations
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase371934"
MODE = "READ_ONLY_NO_MUTATION"

DATE_FIELDS = ("supervision_date","run_date","business_date","cycle_date","date")
TIME_FIELDS = ("updated_at","created_at","event_time","recorded_at","timestamp","ts")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_runtime_diag_target", P375)
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

def row_id(row: Dict[str, Any]) -> str:
    for k in ("id","runtime_id","supervision_id","run_id"):
        if row.get(k) is not None:
            return str(row.get(k))
    return ""

def event_time(row: Dict[str, Any]) -> str:
    return first(row, TIME_FIELDS)

def business_date(row: Dict[str, Any]) -> str:
    v = first(row, DATE_FIELDS)
    if v:
        return v[:10]
    t = event_time(row)
    return t[:10] if len(t) >= 10 else "UNKNOWN_DATE"

def state_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "runtime_state","supervision_state","operational_state","state","status",
        "activation_state","master_cycle_state","qualification_state",
        "safety_revocation_triggered","fail_closed_policy","readiness_state",
        "health_state","incident_severity"
    )
    return {k: row.get(k) for k in keys if k in row}

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect","RUNTIME_TABLES","latest","runtime_supervision_reconstruct"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 runtime contract: {name}")

    table, rows, errors = mod.inspect(mod.RUNTIME_TABLES, portfolio_scoped=True)
    rows = [r for r in (rows or []) if isinstance(r, dict)]

    selected = mod.latest(rows)
    selected_ok, selected_state, selected_reason = mod.runtime_supervision_reconstruct(selected)

    normalized: List[Dict[str, Any]] = []
    for i, r in enumerate(rows):
        ok, state, reason = mod.runtime_supervision_reconstruct(r)
        normalized.append({
            "index": i,
            "id": row_id(r),
            "business_date": business_date(r),
            "event_time": event_time(r),
            "reconstructed_ok": bool(ok),
            "reconstructed_state": state,
            "reconstruction_reason": reason,
            "fields": state_fields(r),
        })

    chronological = sorted(
        normalized,
        key=lambda x: (x["event_time"], x["business_date"], x["id"], x["index"])
    )

    latest_by_event = chronological[-1] if chronological else None

    selected_id = row_id(selected) if selected else ""
    selected_norm = next((x for x in normalized if x["id"] == selected_id and selected_id), None)
    if selected_norm is None and selected:
        selected_norm = {
            "index": None,
            "id": selected_id,
            "business_date": business_date(selected),
            "event_time": event_time(selected),
            "reconstructed_ok": bool(selected_ok),
            "reconstructed_state": selected_state,
            "reconstruction_reason": selected_reason,
            "fields": state_fields(selected),
        }

    newer_pass_rows = []
    if selected_norm:
        s_key = (selected_norm["event_time"], selected_norm["business_date"], selected_norm["id"])
        for x in chronological:
            x_key = (x["event_time"], x["business_date"], x["id"])
            if x_key > s_key and x["reconstructed_ok"]:
                newer_pass_rows.append(x)

    if selected_norm and not selected_norm["reconstructed_ok"] and newer_pass_rows:
        conclusion = "SELECTED_BLOCKED_ROW_HAS_NEWER_PASS_CANDIDATE"
    elif selected_norm and not selected_norm["reconstructed_ok"]:
        conclusion = "SELECTED_BLOCKED_ROW_NO_NEWER_PASS_FOUND"
    elif selected_norm and selected_norm["reconstructed_ok"]:
        conclusion = "SELECTED_RUNTIME_ROW_ALREADY_PASS"
    else:
        conclusion = "RUNTIME_ROW_UNRESOLVED"

    result = {
        "contract": "PHASE371934_PHASE375_RUNTIME_SUPERVISION_CANONICAL_ROW_PROVENANCE_SUPERSESSION_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_runtime_table": table,
        "read_errors": errors or [],
        "row_count": len(rows),
        "selected_row": selected_norm,
        "latest_by_event_time": latest_by_event,
        "newer_pass_candidates": newer_pass_rows,
        "all_rows": chronological,
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
    (OUT / "phase371934_runtime_provenance.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.4 - Phase 3.7.5 Runtime Supervision Canonical Row Provenance",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        f"- Selected Runtime Table: `{table}`",
        f"- Row Count: **{len(rows)}**",
        f"- Read Errors: `{errors or []}`",
        "",
        "## Selected Row",
        "",
    ]
    if selected_norm:
        for k in ("id","business_date","event_time","reconstructed_ok","reconstructed_state","reconstruction_reason"):
            md.append(f"- {k}: `{selected_norm.get(k)}`")
        md.append(f"- fields: `{selected_norm.get('fields')}`")
    else:
        md.append("- None")

    md += ["", "## Latest By Event Time", ""]
    if latest_by_event:
        for k in ("id","business_date","event_time","reconstructed_ok","reconstructed_state","reconstruction_reason"):
            md.append(f"- {k}: `{latest_by_event.get(k)}`")
        md.append(f"- fields: `{latest_by_event.get('fields')}`")
    else:
        md.append("- None")

    md += ["", "## Newer PASS Candidates", ""]
    if newer_pass_rows:
        for x in newer_pass_rows:
            md.append(
                f"- {x['business_date']} | {x['event_time']} | {x['reconstructed_state']} | "
                f"{x['reconstruction_reason']} | id {x['id']}"
            )
    else:
        md.append("- None")

    md += ["", "## All Runtime Rows", ""]
    for x in chronological:
        md.append(
            f"- {x['business_date']} | {x['event_time']} | ok={x['reconstructed_ok']} | "
            f"state={x['reconstructed_state']} | reason={x['reconstruction_reason']} | id={x['id']}"
        )

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

    (OUT / "phase371934_runtime_provenance.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE371934_CONCLUSION=" + conclusion)
    print("SELECTED_RUNTIME_TABLE=" + str(table))
    print("ROW_COUNT=" + str(len(rows)))
    print("SELECTED_ROW_ID=" + str(selected_norm.get("id") if selected_norm else None))
    print("SELECTED_STATE=" + str(selected_norm.get("reconstructed_state") if selected_norm else None))
    print("SELECTED_REASON=" + str(selected_norm.get("reconstruction_reason") if selected_norm else None))
    print("LATEST_EVENT_ROW_ID=" + str(latest_by_event.get("id") if latest_by_event else None))
    print("LATEST_EVENT_STATE=" + str(latest_by_event.get("reconstructed_state") if latest_by_event else None))
    print("NEWER_PASS_CANDIDATES=" + str(len(newer_pass_rows)))

if __name__ == "__main__":
    main()
