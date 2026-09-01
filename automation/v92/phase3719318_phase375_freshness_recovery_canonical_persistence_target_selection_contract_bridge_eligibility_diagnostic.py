from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719318"
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
    "phase3719318",
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
TIME_HINTS = ("event_time", "updated_at", "created_at", "recorded_at", "timestamp", "ts")
DATE_HINTS = ("business_date", "run_date", "supervision_date", "cycle_date")
STATE_HINTS = ("state", "status", "health_state", "readiness_state", "qualification_state", "master_cycle_state")
FAILURE_HINTS = ("critical_failures", "warning_failures", "reason_codes", "blockers")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_bridge_eligibility_target", P375)
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
    return list(value) if isinstance(value, (list, tuple)) else []

def inspect_daily_contract(mod) -> Dict[str, Any]:
    tables = getattr(mod, "DAILY_EVIDENCE_TABLES", None)
    if not tables:
        return {"declared_tables": None, "selected_table": None, "row_count": 0, "errors": ["MISSING_OR_EMPTY_CONTRACT"]}
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

def candidate_score(target: str, text: str, table: str, in_daily_contract: bool) -> Dict[str, Any]:
    low = text.lower()

    ownership = 0
    if target in low:
        ownership += 6
    ownership += min(4, sum(1 for h in DOMAIN_HINTS[target] if h in low))

    persistence = 4 if any(h in low for h in PERSIST_HINTS) else 0
    invocation = 3 if any(h in low for h in INVOKE_HINTS) else 0
    recovery = 4 if any(h in low for h in RECOVERY_HINTS) else 0
    time_compat = 2 if any(h in low for h in TIME_HINTS) else 0
    date_compat = 2 if any(h in low for h in DATE_HINTS) else 0
    state_compat = 2 if any(h in low for h in STATE_HINTS) else 0
    failure_contract = 1 if any(h in low for h in FAILURE_HINTS) else 0
    contract_bonus = 5 if in_daily_contract else 0

    total = ownership + persistence + invocation + recovery + time_compat + date_compat + state_compat + failure_contract + contract_bonus

    return {
        "total": total,
        "ownership": ownership,
        "persistence": persistence,
        "invocation": invocation,
        "recovery": recovery,
        "time_compat": time_compat,
        "date_compat": date_compat,
        "state_compat": state_compat,
        "failure_contract": failure_contract,
        "daily_contract_bonus": contract_bonus,
        "in_daily_contract": in_daily_contract,
    }

def scan_domain(target: str, daily_tables: set[str]) -> Dict[str, Any]:
    table_refs: Dict[str, List[Dict[str, Any]]] = {}

    for path in source_files():
        try:
            text = read_text(path)
        except Exception:
            continue

        low = text.lower()
        if target not in low and not any(h in low for h in DOMAIN_HINTS[target]):
            continue

        tables = sorted(set(TABLE_PATTERN.findall(text)))
        if not tables:
            continue

        rel = str(path.relative_to(ROOT))
        for table in tables:
            score = candidate_score(target, text, table, table in daily_tables)
            if score["ownership"] == 0:
                continue
            table_refs.setdefault(table, []).append({
                "file": rel,
                "score": score,
                "target_literal": target in low,
                "domain_hits": [h for h in DOMAIN_HINTS[target] if h in low][:12],
                "persistence_hits": [h for h in PERSIST_HINTS if h in low][:12],
                "invocation_hits": [h for h in INVOKE_HINTS if h in low][:12],
                "recovery_hits": [h for h in RECOVERY_HINTS if h in low][:12],
            })

    ranked = []
    for table, refs in table_refs.items():
        refs_sorted = sorted(refs, key=lambda x: (-x["score"]["total"], x["file"]))
        best = refs_sorted[0]
        ranked.append({
            "table": table,
            "in_daily_contract": table in daily_tables,
            "best_score": best["score"]["total"],
            "best_score_breakdown": best["score"],
            "top_owner_reference": best,
            "owner_reference_count": len(refs_sorted),
            "owner_references": refs_sorted[:10],
        })

    ranked.sort(key=lambda x: (-x["best_score"], not x["in_daily_contract"], x["table"]))

    eligible = []
    for item in ranked:
        b = item["best_score_breakdown"]
        if (
            b["ownership"] >= 6
            and b["persistence"] > 0
            and b["recovery"] > 0
            and b["time_compat"] > 0
            and b["state_compat"] > 0
        ):
            eligible.append(item)

    daily_eligible = [x for x in eligible if x["in_daily_contract"]]
    off_eligible = [x for x in eligible if not x["in_daily_contract"]]

    if len(daily_eligible) == 1 and not off_eligible:
        bridge_decision = "CONSUMER_CONTRACT_ALREADY_HAS_UNIQUE_ELIGIBLE_CANONICAL_TARGET"
        canonical_candidate = daily_eligible[0]
    elif len(off_eligible) == 1 and not daily_eligible:
        bridge_decision = "UNIQUE_OFF_CONTRACT_CANONICAL_TARGET_ELIGIBLE_FOR_BRIDGE"
        canonical_candidate = off_eligible[0]
    elif len(daily_eligible) == 1 and len(off_eligible) >= 1:
        bridge_decision = "DAILY_CONTRACT_TARGET_EXISTS_BUT_OFF_CONTRACT_COMPETITORS_REQUIRE_DISAMBIGUATION"
        canonical_candidate = daily_eligible[0]
    elif len(off_eligible) > 1:
        bridge_decision = "MULTIPLE_OFF_CONTRACT_ELIGIBLE_TARGETS_FAIL_CLOSED"
        canonical_candidate = None
    elif eligible:
        bridge_decision = "ELIGIBLE_TARGETS_EXIST_BUT_CANONICAL_SELECTION_AMBIGUOUS"
        canonical_candidate = None
    else:
        bridge_decision = "NO_ELIGIBLE_CANONICAL_PERSISTENCE_TARGET_FOUND"
        canonical_candidate = None

    return {
        "bridge_decision": bridge_decision,
        "canonical_candidate": canonical_candidate,
        "ranked_candidates": ranked[:30],
        "eligible_candidates": eligible[:20],
        "daily_contract_eligible_candidates": daily_eligible[:20],
        "off_contract_eligible_candidates": off_eligible[:20],
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

    decisions = [d["bridge_decision"] for d in per_target.values()]

    if all(d == "UNIQUE_OFF_CONTRACT_CANONICAL_TARGET_ELIGIBLE_FOR_BRIDGE" for d in decisions):
        conclusion = "UNIQUE_OFF_CONTRACT_CANONICAL_TARGETS_IDENTIFIED_BRIDGE_FIX_ELIGIBLE"
    elif any(d == "MULTIPLE_OFF_CONTRACT_ELIGIBLE_TARGETS_FAIL_CLOSED" for d in decisions):
        conclusion = "MULTIPLE_ELIGIBLE_OFF_CONTRACT_TARGETS_AMBIGUOUS_FAIL_CLOSED"
    elif any(d == "NO_ELIGIBLE_CANONICAL_PERSISTENCE_TARGET_FOUND" for d in decisions):
        conclusion = "NO_SAFE_CANONICAL_PERSISTENCE_TARGET_FOR_ONE_OR_MORE_DOMAINS"
    elif any(d == "DAILY_CONTRACT_TARGET_EXISTS_BUT_OFF_CONTRACT_COMPETITORS_REQUIRE_DISAMBIGUATION" for d in decisions):
        conclusion = "CANONICAL_TARGET_COMPETITION_REQUIRES_ADDITIONAL_DISAMBIGUATION"
    else:
        conclusion = "MIXED_CANONICAL_TARGET_ELIGIBILITY_REQUIRES_DOMAIN_SPECIFIC_FIX_PLAN"

    result = {
        "contract": "PHASE3719318_PHASE375_FRESHNESS_RECOVERY_CANONICAL_PERSISTENCE_TARGET_SELECTION_CONTRACT_BRIDGE_ELIGIBILITY_DIAGNOSTIC",
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
    (OUT / "phase3719318_canonical_target_bridge_eligibility.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.18 - Freshness Recovery Canonical Persistence Target Selection + Contract Bridge Eligibility",
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
        "## Per-Domain Canonical Target Selection",
    ]

    for target in TARGETS:
        data = per_target[target]
        md += [
            "",
            f"### {target}",
            f"- bridge_decision: **{data['bridge_decision']}**",
            f"- canonical_candidate: `{data['canonical_candidate']}`",
            f"- daily_contract_eligible_candidates: `{data['daily_contract_eligible_candidates']}`",
            f"- off_contract_eligible_candidates: `{data['off_contract_eligible_candidates']}`",
            f"- ranked_candidates: `{data['ranked_candidates']}`",
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

    (OUT / "phase3719318_canonical_target_bridge_eligibility.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719318_CONCLUSION=" + conclusion)
    for target in TARGETS:
        data = per_target[target]
        print(target.upper() + "_BRIDGE_DECISION=" + data["bridge_decision"])
        cand = data["canonical_candidate"]
        print(target.upper() + "_CANONICAL_CANDIDATE=" + (cand["table"] if cand else "NONE"))
        print(target.upper() + "_OFF_CONTRACT_ELIGIBLE=" + ",".join(x["table"] for x in data["off_contract_eligible_candidates"]))

if __name__ == "__main__":
    main()
