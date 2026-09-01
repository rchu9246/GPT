from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719317"
MODE = "READ_ONLY_NO_MUTATION"

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
    "phase3719317",
    "phase371937",
    "phase371938",
    "phase371939",
)

DOMAIN_HINTS = {
    "freshness_readiness": ("readiness", "qualification", "readiness_state", "readiness_score"),
    "freshness_health": ("health", "health_state", "health_score", "monitoring"),
    "freshness_sla": ("sla", "service_level", "observability", "freshness"),
    "freshness_master": ("master_cycle", "daily_master_cycle", "master", "orchestrator"),
}

TABLE_PATTERN = re.compile(r'["\']([a-zA-Z0-9_]+_v92)["\']')
PERSIST_HINTS = ("insert(", "upsert(", ".insert", ".upsert", "persist", "write", "postgrest", "supabase")
INVOKE_HINTS = ("subprocess", "python ", "workflow_dispatch", "run:", "uses:", "workflow_call", "invoke", "execute")
RECOVERY_HINTS = ("recovered", "recovery", "pass", "ready", "healthy", "active", "qualified", "completed", "success")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_off_contract_owner_target", P375)
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
    value = getattr(mod, "DAILY_EVIDENCE_TABLES", None)
    if isinstance(value, (list, tuple)):
        return list(value)
    return []

def inspect_daily_contract(mod) -> Dict[str, Any]:
    tables = getattr(mod, "DAILY_EVIDENCE_TABLES", None)
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

def score_owner(target: str, text: str) -> int:
    low = text.lower()
    score = 0
    if target in low:
        score += 6
    score += min(4, sum(1 for h in DOMAIN_HINTS[target] if h in low))
    score += 3 if any(h in low for h in RECOVERY_HINTS) else 0
    score += 4 if any(h in low for h in PERSIST_HINTS) else 0
    score += 2 if any(h in low for h in INVOKE_HINTS) else 0
    return score

def scan_domain(target: str, daily_tables: set[str]) -> Dict[str, Any]:
    refs = []
    table_owners: Dict[str, List[Dict[str, Any]]] = {}

    for path in source_files():
        try:
            text = read_text(path)
        except Exception:
            continue

        low = text.lower()
        if target not in low and not any(h in low for h in DOMAIN_HINTS[target]):
            continue

        rel = str(path.relative_to(ROOT))
        tables = sorted(set(TABLE_PATTERN.findall(text)))
        persist_hits = [h for h in PERSIST_HINTS if h in low]
        invoke_hits = [h for h in INVOKE_HINTS if h in low]
        recovery_hits = [h for h in RECOVERY_HINTS if h in low]

        if not (persist_hits or recovery_hits or invoke_hits):
            continue

        item = {
            "file": rel,
            "score": score_owner(target, text),
            "target_literal": target in low,
            "domain_hits": [h for h in DOMAIN_HINTS[target] if h in low][:12],
            "persistence_hits": persist_hits[:12],
            "invocation_hits": invoke_hits[:12],
            "recovery_hits": recovery_hits[:12],
            "table_mentions": tables[:40],
        }
        refs.append(item)

        for table in tables:
            table_owners.setdefault(table, []).append(item)

    refs.sort(key=lambda x: (-x["score"], x["file"]))

    candidate_tables = sorted(table_owners.keys())
    matching = sorted(set(candidate_tables) & daily_tables)
    off_contract = sorted(set(candidate_tables) - daily_tables)

    off_contract_detail = []
    for table in off_contract:
        owners = sorted(table_owners.get(table, []), key=lambda x: (-x["score"], x["file"]))
        off_contract_detail.append({
            "table": table,
            "top_owner_candidates": owners[:8],
        })

    if off_contract_detail:
        status = "OFF_CONTRACT_PERSISTENCE_TARGETS_WITH_DOMAIN_OWNER_CANDIDATES_FOUND"
    elif refs and matching:
        status = "ONLY_DAILY_CONTRACT_PERSISTENCE_TARGETS_FOUND"
    elif refs:
        status = "DOMAIN_OWNER_REFERENCES_FOUND_BUT_TARGET_TABLE_UNRESOLVED"
    else:
        status = "NO_DOMAIN_OWNER_OR_PERSISTENCE_TARGET_FOUND"

    primary_owner = refs[0] if refs else None

    return {
        "status": status,
        "primary_owner_candidate": primary_owner,
        "all_owner_candidates": refs[:20],
        "candidate_persistence_tables": candidate_tables,
        "matching_daily_contract_tables": matching,
        "off_contract_tables": off_contract,
        "off_contract_table_ownership": off_contract_detail,
    }

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect", "DAILY_EVIDENCE_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    daily_contract = inspect_daily_contract(mod)
    daily_tables = set(declared_daily_tables(mod))

    per_target = {
        target: scan_domain(target, daily_tables)
        for target in TARGETS
    }

    statuses = [v["status"] for v in per_target.values()]
    off_domains = [
        target for target, data in per_target.items()
        if data["off_contract_tables"]
    ]

    if off_domains:
        conclusion = "OFF_CONTRACT_FRESHNESS_RECOVERY_PERSISTENCE_TARGETS_AND_DOMAIN_OWNERS_IDENTIFIED"
    elif any(s == "DOMAIN_OWNER_REFERENCES_FOUND_BUT_TARGET_TABLE_UNRESOLVED" for s in statuses):
        conclusion = "FRESHNESS_DOMAIN_OWNERS_FOUND_BUT_PERSISTENCE_TARGET_UNRESOLVED"
    elif all(s == "ONLY_DAILY_CONTRACT_PERSISTENCE_TARGETS_FOUND" for s in statuses):
        conclusion = "NO_OFF_CONTRACT_TARGETS_FOUND_RECHECK_RUNTIME_PERSISTENCE_EXECUTION"
    else:
        conclusion = "OFF_CONTRACT_DOMAIN_OWNERSHIP_NOT_CONFIRMED"

    result = {
        "contract": "PHASE3719317_PHASE375_FRESHNESS_RECOVERY_OFF_CONTRACT_PERSISTENCE_TARGET_DOMAIN_OWNERSHIP_ROOT_CAUSE_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "daily_evidence_contract": daily_contract,
        "off_contract_domains": off_domains,
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
    (OUT / "phase3719317_off_contract_domain_ownership.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.17 - Freshness Recovery Off-Contract Persistence Target + Domain Ownership Root Cause",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        f"- Off-contract domains: `{off_domains}`",
        "",
        "## Phase 3.7.5 Daily Evidence Contract",
        f"- declared_tables: `{daily_contract['declared_tables']}`",
        f"- selected_table: `{daily_contract['selected_table']}`",
        f"- row_count: `{daily_contract['row_count']}`",
        f"- errors: `{daily_contract['errors']}`",
        "",
        "## Per-Domain Ownership / Target Analysis",
    ]

    for target in TARGETS:
        data = per_target[target]
        md += [
            "",
            f"### {target}",
            f"- status: **{data['status']}**",
            f"- primary_owner_candidate: `{data['primary_owner_candidate']}`",
            f"- candidate_persistence_tables: `{data['candidate_persistence_tables']}`",
            f"- matching_daily_contract_tables: `{data['matching_daily_contract_tables']}`",
            f"- off_contract_tables: `{data['off_contract_tables']}`",
            f"- off_contract_table_ownership: `{data['off_contract_table_ownership']}`",
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

    (OUT / "phase3719317_off_contract_domain_ownership.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719317_CONCLUSION=" + conclusion)
    print("OFF_CONTRACT_DOMAINS=" + ",".join(off_domains))
    for target in TARGETS:
        data = per_target[target]
        print(target.upper() + "_STATUS=" + data["status"])
        print(target.upper() + "_OFF_CONTRACT_TABLES=" + ",".join(data["off_contract_tables"]))
        owner = data["primary_owner_candidate"]
        print(target.upper() + "_PRIMARY_OWNER=" + (owner["file"] if owner else "NONE"))

if __name__ == "__main__":
    main()
