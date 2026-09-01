from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase371939"
MODE = "READ_ONLY_NO_MUTATION"

TARGET_FAILURES = (
    "freshness_readiness",
    "freshness_health",
    "freshness_sla",
    "freshness_master",
)

TIME_FIELDS = ("updated_at", "created_at", "event_time", "recorded_at", "timestamp", "ts")
DATE_FIELDS = ("business_date", "run_date", "supervision_date", "cycle_date", "date")

CANDIDATE_TABLE_ATTRS = (
    "RUNTIME_TABLES",
    "ACTIVATION_TABLES",
    "MASTER_CYCLE_TABLES",
    "DAILY_EVIDENCE_TABLES",
)

RECOVERY_TOKENS = ("PASS", "READY", "HEALTHY", "ACTIVE", "QUALIFIED", "COMPLETED", "OK", "SUCCESS")
FAILURE_TOKENS = ("FAIL", "FAILED", "BLOCK", "SUSPEND", "REVOK", "CRITICAL", "STALE", "ERROR")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_freshness_diag_target", P375)
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

def row_text(row: Dict[str, Any]) -> str:
    return json.dumps(row or {}, ensure_ascii=False, sort_keys=True).lower()

def extract_failure_hits(row: Dict[str, Any]) -> List[str]:
    text = row_text(row)
    return [name for name in TARGET_FAILURES if name.lower() in text]

def state_values(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "state", "status", "health_state", "readiness_state", "qualification_state",
        "master_cycle_state", "runtime_state", "supervision_state", "operational_state",
        "activation_state", "result", "final_state", "final_result",
        "critical_failures", "warning_failures", "reason_codes", "blockers",
    )
    return {k: row.get(k) for k in keys if k in row}

def looks_recovered(row: Dict[str, Any]) -> bool:
    if not row:
        return False
    values = " ".join(str(v).upper() for v in state_values(row).values())
    if any(token in values for token in FAILURE_TOKENS):
        return False
    return any(token in values for token in RECOVERY_TOKENS)

def chrono_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (event_time(row), business_date(row), row_id(row))

def inspect_tables(mod) -> List[Dict[str, Any]]:
    seen = set()
    results: List[Dict[str, Any]] = []

    for attr in CANDIDATE_TABLE_ATTRS:
        tables = getattr(mod, attr, None)
        if not tables:
            continue

        try:
            table, rows, errors = mod.inspect(tables, portfolio_scoped=True)
        except Exception as exc:
            results.append({
                "contract_attr": attr,
                "selected_table": None,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "rows": [],
            })
            continue

        key = (attr, str(table))
        if key in seen:
            continue
        seen.add(key)

        clean_rows = [r for r in (rows or []) if isinstance(r, dict)]
        results.append({
            "contract_attr": attr,
            "selected_table": table,
            "errors": list(errors or []),
            "rows": clean_rows,
        })

    return results

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()

    for name in ("inspect", "latest", "RUNTIME_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    runtime_table, runtime_rows, runtime_errors = mod.inspect(mod.RUNTIME_TABLES, portfolio_scoped=True)
    runtime_rows = [r for r in (runtime_rows or []) if isinstance(r, dict)]
    selected_runtime = mod.latest(runtime_rows)

    selected_runtime_key = chrono_key(selected_runtime) if selected_runtime else ("", "", "")
    selected_runtime_failures = extract_failure_hits(selected_runtime)

    sources = inspect_tables(mod)

    evidence_matches: Dict[str, List[Dict[str, Any]]] = {name: [] for name in TARGET_FAILURES}
    later_recovery_candidates: Dict[str, List[Dict[str, Any]]] = {name: [] for name in TARGET_FAILURES}

    for source in sources:
        attr = source["contract_attr"]
        table = source["selected_table"]
        for row in source["rows"]:
            hits = extract_failure_hits(row)
            if not hits:
                continue

            item = {
                "contract_attr": attr,
                "table": table,
                "id": row_id(row),
                "business_date": business_date(row),
                "event_time": event_time(row),
                "state_values": state_values(row),
                "looks_recovered": looks_recovered(row),
            }

            for hit in hits:
                evidence_matches[hit].append(item)
                if selected_runtime and chrono_key(row) > selected_runtime_key and item["looks_recovered"]:
                    later_recovery_candidates[hit].append(item)

    per_failure = {}
    for name in TARGET_FAILURES:
        matches = sorted(
            evidence_matches[name],
            key=lambda x: (x["event_time"], x["business_date"], x["id"]),
        )
        recoveries = sorted(
            later_recovery_candidates[name],
            key=lambda x: (x["event_time"], x["business_date"], x["id"]),
        )
        latest_match = matches[-1] if matches else None
        latest_recovery = recoveries[-1] if recoveries else None

        if latest_recovery:
            status = "LATER_RECOVERY_EVIDENCE_FOUND"
        elif matches:
            status = "FAILURE_PROVENANCE_FOUND_NO_LATER_RECOVERY"
        else:
            status = "NO_CANONICAL_PROVENANCE_FOUND"

        per_failure[name] = {
            "status": status,
            "latest_match": latest_match,
            "latest_later_recovery": latest_recovery,
            "all_matches": matches,
            "later_recovery_candidates": recoveries,
        }

    unresolved = [
        name for name, data in per_failure.items()
        if data["status"] != "LATER_RECOVERY_EVIDENCE_FOUND"
    ]

    if not selected_runtime_failures:
        conclusion = "SELECTED_RUNTIME_ROW_DOES_NOT_EXPOSE_TARGET_FRESHNESS_FAILURES"
    elif not unresolved:
        conclusion = "ALL_FRESHNESS_FAILURES_HAVE_LATER_RECOVERY_EVIDENCE"
    elif any(per_failure[name]["status"] == "NO_CANONICAL_PROVENANCE_FOUND" for name in unresolved):
        conclusion = "FRESHNESS_FAILURE_PROVENANCE_INCOMPLETE"
    else:
        conclusion = "FRESHNESS_FAILURES_REMAIN_CANONICAL_WITHOUT_LATER_RECOVERY"

    result = {
        "contract": "PHASE371939_PHASE375_FRESHNESS_CRITICAL_FAILURES_CANONICAL_PROVENANCE_RECOVERY_ELIGIBILITY_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_runtime": {
            "table": runtime_table,
            "read_errors": list(runtime_errors or []),
            "id": row_id(selected_runtime),
            "business_date": business_date(selected_runtime) if selected_runtime else "",
            "event_time": event_time(selected_runtime) if selected_runtime else "",
            "target_freshness_failures_present": selected_runtime_failures,
            "state_values": state_values(selected_runtime) if selected_runtime else {},
        },
        "source_discovery": [
            {
                "contract_attr": s["contract_attr"],
                "selected_table": s["selected_table"],
                "errors": s["errors"],
                "row_count": len(s["rows"]),
            }
            for s in sources
        ],
        "per_failure": per_failure,
        "unresolved_failures": unresolved,
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
    (OUT / "phase371939_freshness_provenance.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.9 - Freshness Critical Failures Canonical Provenance + Recovery Eligibility",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        "",
        "## Selected Runtime",
        f"- table: `{runtime_table}`",
        f"- id: `{row_id(selected_runtime)}`",
        f"- business_date: `{business_date(selected_runtime) if selected_runtime else ''}`",
        f"- event_time: `{event_time(selected_runtime) if selected_runtime else ''}`",
        f"- target_freshness_failures_present: `{selected_runtime_failures}`",
        "",
        "## Source Discovery",
    ]

    for source in result["source_discovery"]:
        md.append(
            f"- {source['contract_attr']} -> `{source['selected_table']}` | "
            f"rows={source['row_count']} | errors=`{source['errors']}`"
        )

    md += ["", "## Per-Failure Provenance"]
    for name in TARGET_FAILURES:
        data = per_failure[name]
        md += [
            "",
            f"### {name}",
            f"- status: **{data['status']}**",
            f"- latest_match: `{data['latest_match']}`",
            f"- latest_later_recovery: `{data['latest_later_recovery']}`",
        ]

    md += [
        "",
        "## Unresolved",
        f"- unresolved_failures: `{unresolved}`",
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

    (OUT / "phase371939_freshness_provenance.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE371939_CONCLUSION=" + conclusion)
    print("SELECTED_RUNTIME_ROW_ID=" + row_id(selected_runtime))
    print("SELECTED_RUNTIME_EVENT_TIME=" + (event_time(selected_runtime) if selected_runtime else ""))
    print("TARGET_FRESHNESS_FAILURES_PRESENT=" + ",".join(selected_runtime_failures))
    for name in TARGET_FAILURES:
        print(f"{name.upper()}_STATUS=" + per_failure[name]["status"])
        print(f"{name.upper()}_LATER_RECOVERY_COUNT=" + str(len(per_failure[name]["later_recovery_candidates"])))
    print("UNRESOLVED_FAILURES=" + ",".join(unresolved))

if __name__ == "__main__":
    main()
