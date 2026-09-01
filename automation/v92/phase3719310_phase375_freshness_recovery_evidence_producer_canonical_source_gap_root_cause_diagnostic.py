from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719310"
MODE = "READ_ONLY_NO_MUTATION"

TARGET_FAILURES = (
    "freshness_readiness",
    "freshness_health",
    "freshness_sla",
    "freshness_master",
)

SEARCH_ROOTS = (
    ROOT / "automation",
    ROOT / ".github" / "workflows",
)

TIME_FIELDS = ("updated_at", "created_at", "event_time", "recorded_at", "timestamp", "ts")
DATE_FIELDS = ("business_date", "run_date", "supervision_date", "cycle_date", "date")

RECOVERY_WORDS = ("pass", "ready", "healthy", "recovered", "recovery", "active", "qualified", "completed", "success")
FAIL_WORDS = ("fail", "failed", "critical", "stale", "suspend", "blocked", "revoked", "error")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_source_gap_target", P375)
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

def looks_recovery_text(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in RECOVERY_WORDS) and not any(w in t for w in FAIL_WORDS)

def source_hits() -> Dict[str, List[Dict[str, Any]]]:
    hits: Dict[str, List[Dict[str, Any]]] = {name: [] for name in TARGET_FAILURES}
    patterns = {
        name: re.compile(re.escape(name), re.IGNORECASE)
        for name in TARGET_FAILURES
    }

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".yml", ".yaml", ".ps1", ".sql"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = str(path.relative_to(ROOT))
            for name, pattern in patterns.items():
                for match in pattern.finditer(text):
                    start = max(0, match.start() - 220)
                    end = min(len(text), match.end() + 320)
                    snippet = text[start:end].replace("\r", " ").replace("\n", " ")
                    hits[name].append({
                        "file": rel,
                        "recovery_like_context": looks_recovery_text(snippet),
                        "snippet": snippet[:600],
                    })

    return hits

def inspect_contract(mod, attr: str) -> Dict[str, Any]:
    tables = getattr(mod, attr, None)
    if not tables:
        return {
            "contract_attr": attr,
            "declared_tables": None,
            "selected_table": None,
            "row_count": 0,
            "errors": ["CONTRACT_ATTR_MISSING_OR_EMPTY"],
            "latest_row": None,
        }

    try:
        table, rows, errors = mod.inspect(tables, portfolio_scoped=True)
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        latest = mod.latest(rows) if rows else None
        return {
            "contract_attr": attr,
            "declared_tables": list(tables) if isinstance(tables, (list, tuple)) else tables,
            "selected_table": table,
            "row_count": len(rows),
            "errors": list(errors or []),
            "latest_row": {
                "id": row_id(latest),
                "business_date": business_date(latest) if latest else "",
                "event_time": event_time(latest) if latest else "",
                "keys": sorted(list(latest.keys())) if latest else [],
            } if latest else None,
        }
    except Exception as exc:
        return {
            "contract_attr": attr,
            "declared_tables": list(tables) if isinstance(tables, (list, tuple)) else tables,
            "selected_table": None,
            "row_count": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "latest_row": None,
        }

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

    contracts = {
        attr: inspect_contract(mod, attr)
        for attr in ("DAILY_EVIDENCE_TABLES", "RUNTIME_TABLES", "ACTIVATION_TABLES", "MASTER_CYCLE_TABLES")
    }

    producer_hits = source_hits()

    producer_summary = {}
    for name in TARGET_FAILURES:
        entries = producer_hits[name]
        recovery_like = [x for x in entries if x["recovery_like_context"]]
        unique_files = sorted({x["file"] for x in entries})
        recovery_files = sorted({x["file"] for x in recovery_like})

        if recovery_files:
            status = "RECOVERY_PRODUCER_CODE_REFERENCES_FOUND"
        elif unique_files:
            status = "FAILURE_REFERENCES_FOUND_NO_CLEAR_RECOVERY_PRODUCER"
        else:
            status = "NO_PRODUCER_REFERENCE_FOUND"

        producer_summary[name] = {
            "status": status,
            "all_reference_files": unique_files,
            "recovery_like_reference_files": recovery_files,
            "sample_hits": entries[:12],
        }

    daily = contracts["DAILY_EVIDENCE_TABLES"]
    daily_gap = (
        not daily.get("declared_tables")
        or daily.get("selected_table") is None
        or daily.get("row_count", 0) == 0
    )

    no_recovery_producer = [
        name for name, data in producer_summary.items()
        if data["status"] != "RECOVERY_PRODUCER_CODE_REFERENCES_FOUND"
    ]

    if daily_gap and len(no_recovery_producer) == len(TARGET_FAILURES):
        conclusion = "DAILY_EVIDENCE_CONTRACT_GAP_AND_NO_CLEAR_RECOVERY_PRODUCER_REFERENCES"
    elif daily_gap:
        conclusion = "DAILY_EVIDENCE_CANONICAL_SOURCE_GAP_WITH_PARTIAL_RECOVERY_PRODUCER_REFERENCES"
    elif no_recovery_producer:
        conclusion = "RECOVERY_PRODUCER_GAPS_REMAIN_WITH_DAILY_EVIDENCE_CONTRACT_AVAILABLE"
    else:
        conclusion = "RECOVERY_PRODUCER_REFERENCES_FOUND_INVESTIGATE_RUNTIME_WIRING"

    result = {
        "contract": "PHASE3719310_PHASE375_FRESHNESS_RECOVERY_EVIDENCE_PRODUCER_CANONICAL_SOURCE_GAP_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_runtime": {
            "table": runtime_table,
            "read_errors": list(runtime_errors or []),
            "id": row_id(selected_runtime),
            "business_date": business_date(selected_runtime) if selected_runtime else "",
            "event_time": event_time(selected_runtime) if selected_runtime else "",
            "critical_failures": selected_runtime.get("critical_failures") if selected_runtime else None,
        },
        "contracts": contracts,
        "producer_summary": producer_summary,
        "daily_evidence_gap": daily_gap,
        "producer_gaps": no_recovery_producer,
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
    (OUT / "phase3719310_source_gap.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.10 - Freshness Recovery Evidence Producer / Canonical Source Gap Root Cause",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        f"- Daily Evidence Gap: **{'YES' if daily_gap else 'NO'}**",
        "",
        "## Selected Runtime",
        f"- table: `{runtime_table}`",
        f"- id: `{row_id(selected_runtime)}`",
        f"- business_date: `{business_date(selected_runtime) if selected_runtime else ''}`",
        f"- event_time: `{event_time(selected_runtime) if selected_runtime else ''}`",
        f"- critical_failures: `{selected_runtime.get('critical_failures') if selected_runtime else None}`",
        "",
        "## Phase 3.7.5 Contract Discovery",
    ]

    for attr, data in contracts.items():
        md.append(
            f"- {attr}: declared=`{data['declared_tables']}` | selected=`{data['selected_table']}` | "
            f"rows={data['row_count']} | errors=`{data['errors']}`"
        )

    md += ["", "## Freshness Recovery Producer Discovery"]
    for name in TARGET_FAILURES:
        data = producer_summary[name]
        md += [
            "",
            f"### {name}",
            f"- status: **{data['status']}**",
            f"- all_reference_files: `{data['all_reference_files']}`",
            f"- recovery_like_reference_files: `{data['recovery_like_reference_files']}`",
        ]

    md += [
        "",
        "## Producer Gaps",
        f"- producer_gaps: `{no_recovery_producer}`",
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

    (OUT / "phase3719310_source_gap.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719310_CONCLUSION=" + conclusion)
    print("DAILY_EVIDENCE_GAP=" + str(daily_gap))
    print("DAILY_EVIDENCE_DECLARED_TABLES=" + str(daily.get("declared_tables")))
    print("DAILY_EVIDENCE_SELECTED_TABLE=" + str(daily.get("selected_table")))
    print("DAILY_EVIDENCE_ROW_COUNT=" + str(daily.get("row_count")))
    for name in TARGET_FAILURES:
        print(f"{name.upper()}_PRODUCER_STATUS=" + producer_summary[name]["status"])
        print(f"{name.upper()}_RECOVERY_REFERENCE_FILES=" + ",".join(producer_summary[name]["recovery_like_reference_files"]))
    print("PRODUCER_GAPS=" + ",".join(no_recovery_producer))

if __name__ == "__main__":
    main()
