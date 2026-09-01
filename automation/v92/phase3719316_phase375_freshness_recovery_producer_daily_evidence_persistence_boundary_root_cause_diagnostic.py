from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719316"
MODE = "READ_ONLY_NO_MUTATION"

DAILY_CONTRACT_ATTR = "DAILY_EVIDENCE_TABLES"

TARGETS = (
    "freshness_readiness",
    "freshness_health",
    "freshness_sla",
    "freshness_master",
)

SEARCH_ROOTS = (
    ROOT / "automation",
    ROOT / ".github" / "workflows",
)

EXCLUDE_PATH_TOKENS = (
    "phase3719310",
    "phase3719311",
    "phase3719312",
    "phase3719313",
    "phase3719314",
    "phase3719315",
    "phase3719316",
    "phase371937",
    "phase371938",
    "phase371939",
)

DOMAIN_HINTS = {
    "freshness_readiness": ("readiness", "qualification", "readiness_state"),
    "freshness_health": ("health", "health_state", "monitoring"),
    "freshness_sla": ("sla", "service_level", "observability", "freshness"),
    "freshness_master": ("master_cycle", "daily_master_cycle", "master", "orchestrator"),
}

TABLE_PATTERN = re.compile(r'["\']([a-zA-Z0-9_]+_v92)["\']')
PERSIST_HINTS = ("insert(", "upsert(", ".insert", ".upsert", "persist", "write", "postgrest", "supabase")
INVOKE_HINTS = ("subprocess", "python ", "workflow_dispatch", "run:", "uses:", "workflow_call", "invoke", "execute")
RECOVERY_HINTS = ("recovered", "recovery", "pass", "ready", "healthy", "active", "qualified", "completed", "success")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_boundary_target", P375)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def is_excluded(rel: str) -> bool:
    low = rel.lower()
    return any(token in low for token in EXCLUDE_PATH_TOKENS)

def source_files():
    files = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".yml", ".yaml", ".ps1", ".sql"}:
                rel = str(path.relative_to(ROOT))
                if not is_excluded(rel):
                    files.append(path)
    return files

def declared_daily_tables(mod) -> List[str]:
    value = getattr(mod, DAILY_CONTRACT_ATTR, None)
    if isinstance(value, (list, tuple)):
        return list(value)
    return []

def scan_domain(target: str, daily_tables: set[str]) -> Dict[str, Any]:
    producer_refs = []
    persistence_refs = []
    invocation_refs = []
    candidate_tables = set()

    for path in source_files():
        try:
            text = read_text(path)
        except Exception:
            continue

        low = text.lower()
        semantic = [h for h in DOMAIN_HINTS[target] if h in low]
        literal = target in low
        if not literal and not semantic:
            continue

        rel = str(path.relative_to(ROOT))
        tables = sorted(set(TABLE_PATTERN.findall(text)))
        persist_hits = [h for h in PERSIST_HINTS if h in low]
        invoke_hits = [h for h in INVOKE_HINTS if h in low]
        recovery_hits = [h for h in RECOVERY_HINTS if h in low]

        item = {
            "file": rel,
            "target_literal": literal,
            "semantic_hits": semantic[:12],
            "table_mentions": tables[:30],
            "persistence_hits": persist_hits[:12],
            "invocation_hits": invoke_hits[:12],
            "recovery_hits": recovery_hits[:12],
        }

        if recovery_hits:
            producer_refs.append(item)
        if persist_hits:
            persistence_refs.append(item)
            candidate_tables.update(tables)
        if invoke_hits:
            invocation_refs.append(item)

    matching = sorted(candidate_tables & daily_tables)
    outside = sorted(candidate_tables - daily_tables)

    if producer_refs and persistence_refs and matching:
        boundary_status = "PRODUCER_PERSISTENCE_PATH_TOUCHES_DAILY_EVIDENCE_CONTRACT"
    elif producer_refs and persistence_refs and outside:
        boundary_status = "PRODUCER_PERSISTENCE_PATH_STOPS_OUTSIDE_DAILY_EVIDENCE_CONTRACT"
    elif producer_refs and persistence_refs and not candidate_tables:
        boundary_status = "PERSISTENCE_LOGIC_FOUND_BUT_TARGET_TABLE_UNRESOLVED"
    elif producer_refs and not persistence_refs:
        boundary_status = "RECOVERY_PRODUCER_FOUND_WITHOUT_PERSISTENCE_BOUNDARY"
    else:
        boundary_status = "NO_CONFIRMED_RECOVERY_PRODUCER_PERSISTENCE_BOUNDARY"

    return {
        "boundary_status": boundary_status,
        "producer_references": producer_refs[:20],
        "persistence_references": persistence_refs[:20],
        "invocation_references": invocation_refs[:20],
        "candidate_persistence_tables": sorted(candidate_tables),
        "matching_daily_contract_tables": matching,
        "outside_daily_contract_tables": outside,
    }

def inspect_daily_contract(mod) -> Dict[str, Any]:
    tables = getattr(mod, DAILY_CONTRACT_ATTR, None)
    if not tables:
        return {
            "declared_tables": None,
            "selected_table": None,
            "row_count": 0,
            "errors": ["MISSING_OR_EMPTY_CONTRACT"],
        }
    try:
        selected, rows, errors = mod.inspect(tables, portfolio_scoped=True)
        return {
            "declared_tables": list(tables) if isinstance(tables, (list, tuple)) else tables,
            "selected_table": selected,
            "row_count": len([r for r in (rows or []) if isinstance(r, dict)]),
            "errors": list(errors or []),
        }
    except Exception as exc:
        return {
            "declared_tables": list(tables) if isinstance(tables, (list, tuple)) else tables,
            "selected_table": None,
            "row_count": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect", DAILY_CONTRACT_ATTR):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    daily_contract = inspect_daily_contract(mod)
    daily_tables = set(declared_daily_tables(mod))

    per_target = {
        target: scan_domain(target, daily_tables)
        for target in TARGETS
    }

    statuses = [v["boundary_status"] for v in per_target.values()]

    if any(s == "PRODUCER_PERSISTENCE_PATH_STOPS_OUTSIDE_DAILY_EVIDENCE_CONTRACT" for s in statuses):
        conclusion = "FRESHNESS_RECOVERY_PERSISTENCE_BOUNDARY_STOPS_OUTSIDE_PHASE375_DAILY_EVIDENCE_CONTRACT"
    elif any(s == "PERSISTENCE_LOGIC_FOUND_BUT_TARGET_TABLE_UNRESOLVED" for s in statuses):
        conclusion = "FRESHNESS_RECOVERY_PERSISTENCE_TARGET_TABLE_UNRESOLVED"
    elif any(s == "RECOVERY_PRODUCER_FOUND_WITHOUT_PERSISTENCE_BOUNDARY" for s in statuses):
        conclusion = "FRESHNESS_RECOVERY_PRODUCER_EXISTS_WITHOUT_CANONICAL_DAILY_EVIDENCE_PERSISTENCE_BOUNDARY"
    elif all(s == "PRODUCER_PERSISTENCE_PATH_TOUCHES_DAILY_EVIDENCE_CONTRACT" for s in statuses):
        conclusion = "RECOVERY_PERSISTENCE_PATHS_TOUCH_DAILY_CONTRACT_INVESTIGATE_RUNTIME_EXECUTION_AND_ROW_CREATION"
    else:
        conclusion = "NO_CONFIRMED_END_TO_END_FRESHNESS_RECOVERY_DAILY_EVIDENCE_PERSISTENCE_BOUNDARY"

    result = {
        "contract": "PHASE3719316_PHASE375_FRESHNESS_RECOVERY_PRODUCER_DAILY_EVIDENCE_PERSISTENCE_BOUNDARY_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "daily_evidence_contract": daily_contract,
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
    (OUT / "phase3719316_persistence_boundary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.16 - Freshness Recovery Producer → Daily Evidence Persistence Boundary Root Cause",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        "",
        "## Phase 3.7.5 Daily Evidence Contract",
        f"- declared_tables: `{daily_contract['declared_tables']}`",
        f"- selected_table: `{daily_contract['selected_table']}`",
        f"- row_count: `{daily_contract['row_count']}`",
        f"- errors: `{daily_contract['errors']}`",
        "",
        "## Per-Domain Persistence Boundary",
    ]

    for target in TARGETS:
        data = per_target[target]
        md += [
            "",
            f"### {target}",
            f"- boundary_status: **{data['boundary_status']}**",
            f"- candidate_persistence_tables: `{data['candidate_persistence_tables']}`",
            f"- matching_daily_contract_tables: `{data['matching_daily_contract_tables']}`",
            f"- outside_daily_contract_tables: `{data['outside_daily_contract_tables']}`",
            f"- producer_references: `{data['producer_references']}`",
            f"- persistence_references: `{data['persistence_references']}`",
            f"- invocation_references: `{data['invocation_references']}`",
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

    (OUT / "phase3719316_persistence_boundary.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719316_CONCLUSION=" + conclusion)
    for target in TARGETS:
        data = per_target[target]
        print(target.upper() + "_BOUNDARY_STATUS=" + data["boundary_status"])
        print(target.upper() + "_MATCHING_DAILY_TABLES=" + ",".join(data["matching_daily_contract_tables"]))
        print(target.upper() + "_OUTSIDE_DAILY_TABLES=" + ",".join(data["outside_daily_contract_tables"]))

if __name__ == "__main__":
    main()
