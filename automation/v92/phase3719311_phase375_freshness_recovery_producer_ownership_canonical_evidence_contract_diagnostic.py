from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719311"
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

OWNERSHIP_HINTS = {
    "freshness_readiness": ("readiness", "qualification", "readiness_score", "readiness_state"),
    "freshness_health": ("health", "health_score", "health_state", "monitoring"),
    "freshness_sla": ("sla", "freshness_sla", "observability", "service_level"),
    "freshness_master": ("master", "master_cycle", "daily_master_cycle", "orchestrator"),
}

PERSIST_HINTS = ("insert", "upsert", "update", "postgrest", "supabase", "persist", "write", "table")
RECOVERY_HINTS = ("pass", "ready", "healthy", "recovered", "recovery", "active", "qualified", "completed", "success")
WORKFLOW_HINTS = ("workflow_dispatch", "schedule:", "cron:", "python ", "run:")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_ownership_diag_target", P375)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def extract_declared_tables(mod, attr: str):
    value = getattr(mod, attr, None)
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return value

def scan_repository() -> Dict[str, List[Dict[str, Any]]]:
    results: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TARGETS}

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

            low = text.lower()
            rel = str(path.relative_to(ROOT))

            for target in TARGETS:
                target_hit = target in low
                semantic_hit = any(h in low for h in OWNERSHIP_HINTS[target])

                if not (target_hit or semantic_hit):
                    continue

                persist = any(h in low for h in PERSIST_HINTS)
                recovery = any(h in low for h in RECOVERY_HINTS)
                workflow = path.suffix.lower() in {".yml", ".yaml"} and any(h in low for h in WORKFLOW_HINTS)

                table_mentions = sorted(set(re.findall(r'["\']([a-zA-Z0-9_]+_v92)["\']', text)))
                phase_mentions = sorted(set(re.findall(r'Phase\s+3\.[0-9.]+', text, flags=re.IGNORECASE)))

                score = 0
                score += 4 if target_hit else 0
                score += 2 if semantic_hit else 0
                score += 2 if persist else 0
                score += 2 if recovery else 0
                score += 1 if workflow else 0

                results[target].append({
                    "file": rel,
                    "score": score,
                    "target_literal_present": target_hit,
                    "semantic_domain_present": semantic_hit,
                    "persistence_like": persist,
                    "recovery_like": recovery,
                    "workflow_like": workflow,
                    "table_mentions": table_mentions[:20],
                    "phase_mentions": phase_mentions[:20],
                })

    for target in TARGETS:
        results[target].sort(key=lambda x: (-x["score"], x["file"]))
        results[target] = results[target][:40]

    return results

def classify_ownership(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not entries:
        return {
            "status": "NO_OWNER_CANDIDATE_FOUND",
            "primary_candidate": None,
            "persistence_candidates": [],
            "workflow_candidates": [],
        }

    persistence = [e for e in entries if e["persistence_like"]]
    workflow = [e for e in entries if e["workflow_like"]]
    primary = entries[0]

    if primary["score"] >= 8 and persistence:
        status = "STRONG_OWNER_AND_PERSISTENCE_CANDIDATE_FOUND"
    elif persistence:
        status = "PERSISTENCE_CANDIDATE_FOUND_OWNER_AMBIGUOUS"
    else:
        status = "OWNER_REFERENCE_FOUND_NO_PERSISTENCE_PATH"

    return {
        "status": status,
        "primary_candidate": primary,
        "persistence_candidates": persistence[:12],
        "workflow_candidates": workflow[:12],
    }

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()

    contracts = {
        attr: extract_declared_tables(mod, attr)
        for attr in ("DAILY_EVIDENCE_TABLES", "RUNTIME_TABLES", "ACTIVATION_TABLES", "MASTER_CYCLE_TABLES")
    }

    scans = scan_repository()
    ownership = {target: classify_ownership(scans[target]) for target in TARGETS}

    daily_tables = contracts.get("DAILY_EVIDENCE_TABLES")
    daily_contract_missing = not daily_tables

    unresolved = [
        target for target, info in ownership.items()
        if info["status"] in {
            "NO_OWNER_CANDIDATE_FOUND",
            "OWNER_REFERENCE_FOUND_NO_PERSISTENCE_PATH",
        }
    ]

    if daily_contract_missing and len(unresolved) == len(TARGETS):
        conclusion = "NO_CANONICAL_DAILY_EVIDENCE_CONTRACT_AND_NO_CONFIRMED_RECOVERY_PERSISTENCE_OWNER"
    elif daily_contract_missing:
        conclusion = "DAILY_EVIDENCE_CONTRACT_MISSING_WITH_PARTIAL_RECOVERY_OWNER_CANDIDATES"
    elif unresolved:
        conclusion = "CANONICAL_EVIDENCE_CONTRACT_PRESENT_BUT_RECOVERY_OWNERSHIP_GAPS_REMAIN"
    else:
        conclusion = "RECOVERY_OWNER_AND_PERSISTENCE_CANDIDATES_FOUND_VALIDATE_CONTRACT_WIRING"

    result = {
        "contract": "PHASE3719311_PHASE375_FRESHNESS_RECOVERY_PRODUCER_OWNERSHIP_CANONICAL_EVIDENCE_CONTRACT_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase375_contracts": contracts,
        "daily_evidence_contract_missing": daily_contract_missing,
        "ownership": ownership,
        "unresolved_ownership": unresolved,
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
    (OUT / "phase3719311_ownership_contract.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.11 - Freshness Recovery Producer Ownership + Canonical Evidence Contract Diagnostic",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        f"- DAILY_EVIDENCE_TABLES Missing: **{'YES' if daily_contract_missing else 'NO'}**",
        "",
        "## Phase 3.7.5 Contract Snapshot",
    ]

    for attr, value in contracts.items():
        md.append(f"- {attr}: `{value}`")

    md += ["", "## Ownership Analysis"]

    for target in TARGETS:
        info = ownership[target]
        md += [
            "",
            f"### {target}",
            f"- status: **{info['status']}**",
            f"- primary_candidate: `{info['primary_candidate']}`",
            f"- persistence_candidates: `{info['persistence_candidates']}`",
            f"- workflow_candidates: `{info['workflow_candidates']}`",
        ]

    md += [
        "",
        "## Unresolved Ownership",
        f"- unresolved_ownership: `{unresolved}`",
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

    (OUT / "phase3719311_ownership_contract.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719311_CONCLUSION=" + conclusion)
    print("DAILY_EVIDENCE_CONTRACT_MISSING=" + str(daily_contract_missing))
    for target in TARGETS:
        print(target.upper() + "_OWNERSHIP_STATUS=" + ownership[target]["status"])
        primary = ownership[target]["primary_candidate"]
        print(target.upper() + "_PRIMARY_OWNER_CANDIDATE=" + (primary["file"] if primary else "NONE"))
    print("UNRESOLVED_OWNERSHIP=" + ",".join(unresolved))

if __name__ == "__main__":
    main()
