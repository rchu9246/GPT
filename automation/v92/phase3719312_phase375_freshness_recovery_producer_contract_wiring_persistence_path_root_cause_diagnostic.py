from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719312"
MODE = "READ_ONLY_NO_MUTATION"

TARGETS = (
    "freshness_readiness",
    "freshness_health",
    "freshness_sla",
    "freshness_master",
)

# Exclude the diagnostic chain itself so it cannot falsely become the "owner".
EXCLUDE_PATH_TOKENS = (
    "phase3719310",
    "phase3719311",
    "phase3719312",
    "phase371939",
    "phase371938",
    "phase371937",
)

SEARCH_ROOTS = (
    ROOT / "automation",
    ROOT / ".github" / "workflows",
)

DOMAIN_HINTS = {
    "freshness_readiness": ("readiness", "qualification", "readiness_state", "readiness_score"),
    "freshness_health": ("health", "health_state", "health_score", "monitoring"),
    "freshness_sla": ("sla", "service_level", "observability", "freshness"),
    "freshness_master": ("master_cycle", "daily_master_cycle", "master", "orchestrator"),
}

RECOVERY_HINTS = ("pass", "ready", "healthy", "recovered", "recovery", "active", "qualified", "completed", "success")
FAIL_HINTS = ("fail", "failed", "critical", "stale", "suspend", "blocked", "revoked", "error")
PERSIST_HINTS = ("insert(", "upsert(", ".insert", ".upsert", "postgrest", "supabase", "persist", "write")
READ_HINTS = ("select(", ".select", "from(", "table(", "postgrest", "supabase")
WORKFLOW_HINTS = ("workflow_dispatch", "schedule:", "cron:", "python ", "run:")
TABLE_PATTERN = re.compile(r'["\']([a-zA-Z0-9_]+_v92)["\']')

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_wiring_diag_target", P375)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def declared_tables(mod, attr: str):
    value = getattr(mod, attr, None)
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return value

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def is_excluded(rel: str) -> bool:
    low = rel.lower()
    return any(token in low for token in EXCLUDE_PATH_TOKENS)

def file_profile(path: Path, target: str) -> Dict[str, Any] | None:
    try:
        text = read_text(path)
    except Exception:
        return None

    low = text.lower()
    hints = DOMAIN_HINTS[target]

    target_literal = target in low
    semantic_hits = [h for h in hints if h in low]
    recovery_hits = [h for h in RECOVERY_HINTS if h in low]
    failure_hits = [h for h in FAIL_HINTS if h in low]
    persist_hits = [h for h in PERSIST_HINTS if h in low]
    read_hits = [h for h in READ_HINTS if h in low]
    workflow_hits = [h for h in WORKFLOW_HINTS if h in low]
    tables = sorted(set(TABLE_PATTERN.findall(text)))

    if not target_literal and not semantic_hits:
        return None

    rel = str(path.relative_to(ROOT))

    score = 0
    score += 5 if target_literal else 0
    score += min(4, len(semantic_hits))
    score += 4 if persist_hits else 0
    score += 3 if recovery_hits else 0
    score += 2 if tables else 0
    score += 1 if workflow_hits else 0
    score -= 2 if failure_hits and not recovery_hits else 0

    return {
        "file": rel,
        "score": score,
        "target_literal": target_literal,
        "semantic_hits": semantic_hits[:12],
        "recovery_hits": recovery_hits[:12],
        "failure_hits": failure_hits[:12],
        "persistence_hits": persist_hits[:12],
        "read_hits": read_hits[:12],
        "workflow_hits": workflow_hits[:12],
        "table_mentions": tables[:30],
    }

def scan_target(target: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".yml", ".yaml", ".ps1", ".sql"}:
                continue
            rel = str(path.relative_to(ROOT))
            if is_excluded(rel):
                continue
            prof = file_profile(path, target)
            if prof:
                rows.append(prof)
    rows.sort(key=lambda x: (-x["score"], x["file"]))
    return rows[:80]

def source_contract_snapshot(mod) -> Dict[str, Any]:
    result = {}
    for attr in ("DAILY_EVIDENCE_TABLES", "RUNTIME_TABLES", "ACTIVATION_TABLES", "MASTER_CYCLE_TABLES"):
        tables = declared_tables(mod, attr)
        selected = None
        row_count = 0
        errors: List[str] = []
        if tables:
            try:
                table, rows, errs = mod.inspect(getattr(mod, attr), portfolio_scoped=True)
                selected = table
                row_count = len([r for r in (rows or []) if isinstance(r, dict)])
                errors = list(errs or [])
            except Exception as exc:
                errors = [f"{type(exc).__name__}: {exc}"]
        result[attr] = {
            "declared_tables": tables,
            "selected_table": selected,
            "row_count": row_count,
            "errors": errors,
        }
    return result

def consumer_table_mentions() -> List[str]:
    text = read_text(P375)
    return sorted(set(TABLE_PATTERN.findall(text)))

def rank_contract_wiring(entries: List[Dict[str, Any]], phase375_tables: set[str]) -> Dict[str, Any]:
    producer_candidates = [e for e in entries if e["persistence_hits"] or e["workflow_hits"]]
    persistence_candidates = [e for e in entries if e["persistence_hits"] and e["table_mentions"]]
    recovery_candidates = [e for e in entries if e["recovery_hits"]]

    candidate_tables = sorted({
        t
        for e in persistence_candidates
        for t in e["table_mentions"]
    })

    matching_consumer_tables = sorted(set(candidate_tables) & phase375_tables)
    off_contract_tables = sorted(set(candidate_tables) - phase375_tables)

    if persistence_candidates and matching_consumer_tables:
        wiring_status = "PRODUCER_PERSISTENCE_MATCHES_PHASE375_CONSUMER_TABLE_CONTRACT"
    elif persistence_candidates and off_contract_tables:
        wiring_status = "PRODUCER_PERSISTS_TO_TABLES_OUTSIDE_PHASE375_CONSUMER_CONTRACT"
    elif producer_candidates and not persistence_candidates:
        wiring_status = "OWNER_OR_WORKFLOW_FOUND_BUT_NO_CONFIRMED_TABLE_PERSISTENCE"
    else:
        wiring_status = "NO_CONFIRMED_PRODUCER_PERSISTENCE_PATH"

    return {
        "wiring_status": wiring_status,
        "producer_candidates": producer_candidates[:12],
        "persistence_candidates": persistence_candidates[:12],
        "recovery_candidates": recovery_candidates[:12],
        "candidate_persistence_tables": candidate_tables,
        "matching_phase375_consumer_tables": matching_consumer_tables,
        "off_contract_persistence_tables": off_contract_tables,
    }

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect", "RUNTIME_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    contracts = source_contract_snapshot(mod)
    p375_tables = set(consumer_table_mentions())

    per_target = {}
    for target in TARGETS:
        entries = scan_target(target)
        per_target[target] = rank_contract_wiring(entries, p375_tables)

    statuses = [v["wiring_status"] for v in per_target.values()]

    if all(s == "PRODUCER_PERSISTENCE_MATCHES_PHASE375_CONSUMER_TABLE_CONTRACT" for s in statuses):
        conclusion = "PRODUCER_AND_CONSUMER_TABLE_CONTRACTS_ALIGN_INVESTIGATE_ROW_SCHEMA_OR_EVENT_TIME"
    elif any(s == "PRODUCER_PERSISTS_TO_TABLES_OUTSIDE_PHASE375_CONSUMER_CONTRACT" for s in statuses):
        conclusion = "PRODUCER_PERSISTENCE_EXISTS_BUT_PHASE375_CONSUMER_CONTRACT_MISWIRED"
    elif any(s == "OWNER_OR_WORKFLOW_FOUND_BUT_NO_CONFIRMED_TABLE_PERSISTENCE" for s in statuses):
        conclusion = "RECOVERY_OWNER_FOUND_BUT_CANONICAL_PERSISTENCE_PATH_NOT_CONFIRMED"
    else:
        conclusion = "NO_CONFIRMED_FRESHNESS_RECOVERY_PERSISTENCE_PATH"

    result = {
        "contract": "PHASE3719312_PHASE375_FRESHNESS_RECOVERY_PRODUCER_CONTRACT_WIRING_PERSISTENCE_PATH_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase375_contracts": contracts,
        "phase375_consumer_table_mentions": sorted(p375_tables),
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
    (OUT / "phase3719312_contract_wiring.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.12 - Freshness Recovery Producer Contract Wiring + Persistence Path Root Cause Diagnostic",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        "",
        "## Phase 3.7.5 Consumer Contract",
    ]

    for attr, data in contracts.items():
        md.append(
            f"- {attr}: declared=`{data['declared_tables']}` | selected=`{data['selected_table']}` | "
            f"rows={data['row_count']} | errors=`{data['errors']}`"
        )

    md += [
        "",
        f"- consumer_table_mentions: `{sorted(p375_tables)}`",
        "",
        "## Per-Domain Wiring",
    ]

    for target in TARGETS:
        data = per_target[target]
        md += [
            "",
            f"### {target}",
            f"- wiring_status: **{data['wiring_status']}**",
            f"- candidate_persistence_tables: `{data['candidate_persistence_tables']}`",
            f"- matching_phase375_consumer_tables: `{data['matching_phase375_consumer_tables']}`",
            f"- off_contract_persistence_tables: `{data['off_contract_persistence_tables']}`",
            f"- producer_candidates: `{data['producer_candidates']}`",
            f"- persistence_candidates: `{data['persistence_candidates']}`",
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

    (OUT / "phase3719312_contract_wiring.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719312_CONCLUSION=" + conclusion)
    for target in TARGETS:
        data = per_target[target]
        print(target.upper() + "_WIRING_STATUS=" + data["wiring_status"])
        print(target.upper() + "_MATCHING_TABLES=" + ",".join(data["matching_phase375_consumer_tables"]))
        print(target.upper() + "_OFF_CONTRACT_TABLES=" + ",".join(data["off_contract_persistence_tables"]))

if __name__ == "__main__":
    main()
