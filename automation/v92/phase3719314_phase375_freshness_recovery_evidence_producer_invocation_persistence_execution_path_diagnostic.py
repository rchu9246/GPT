from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
P375 = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase3719314"
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
    "phase371939",
    "phase371938",
    "phase371937",
)

DOMAIN_HINTS = {
    "freshness_readiness": ("readiness", "qualification", "readiness_state", "readiness_score"),
    "freshness_health": ("health", "health_state", "health_score", "monitoring"),
    "freshness_sla": ("sla", "service_level", "observability", "freshness"),
    "freshness_master": ("master_cycle", "daily_master_cycle", "master", "orchestrator"),
}

INVOKE_HINTS = (
    "subprocess", "run(", "python ", "workflow_dispatch", "uses:", "repository_dispatch",
    "workflow_call", "gh workflow run", "dispatches", "invoke", "execute",
)

PERSIST_HINTS = (
    "insert(", "upsert(", ".insert", ".upsert", "postgrest", "supabase",
    "persist", "write", "table(", "from(",
)

SUCCESS_HINTS = ("pass", "ready", "healthy", "recovered", "recovery", "active", "qualified", "completed", "success", "ok")
FAIL_HINTS = ("fail", "failed", "critical", "stale", "suspend", "blocked", "revoked", "error")

TABLE_PATTERN = re.compile(r'["\']([a-zA-Z0-9_]+_v92)["\']')
PY_CALL_PATTERN = re.compile(r'([A-Za-z0-9_./\\-]+\.py)')
WF_CALL_PATTERN = re.compile(r'([A-Za-z0-9_.\-/]+\.ya?ml)')

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_invocation_diag_target", P375)
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

def source_files() -> List[Path]:
    out = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".yml", ".yaml", ".ps1", ".sql"}:
                rel = str(path.relative_to(ROOT))
                if not is_excluded(rel):
                    out.append(path)
    return out

def scan_domain(target: str) -> List[Dict[str, Any]]:
    rows = []
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

        invoke_hits = [h for h in INVOKE_HINTS if h in low]
        persist_hits = [h for h in PERSIST_HINTS if h in low]
        success_hits = [h for h in SUCCESS_HINTS if h in low]
        fail_hits = [h for h in FAIL_HINTS if h in low]
        tables = sorted(set(TABLE_PATTERN.findall(text)))

        py_calls = sorted(set(PY_CALL_PATTERN.findall(text)))
        wf_calls = sorted(set(WF_CALL_PATTERN.findall(text)))

        rel = str(path.relative_to(ROOT))

        score = 0
        score += 5 if literal else 0
        score += min(4, len(semantic))
        score += 3 if invoke_hits else 0
        score += 4 if persist_hits else 0
        score += 2 if success_hits else 0
        score += 2 if tables else 0
        score += 1 if py_calls or wf_calls else 0
        score -= 1 if fail_hits and not success_hits else 0

        rows.append({
            "file": rel,
            "score": score,
            "target_literal": literal,
            "semantic_hits": semantic[:12],
            "invocation_hits": invoke_hits[:12],
            "persistence_hits": persist_hits[:12],
            "success_hits": success_hits[:12],
            "failure_hits": fail_hits[:12],
            "table_mentions": tables[:30],
            "python_call_targets": py_calls[:30],
            "workflow_call_targets": wf_calls[:30],
        })

    rows.sort(key=lambda x: (-x["score"], x["file"]))
    return rows[:100]

def declared_tables(mod, attr: str):
    value = getattr(mod, attr, None)
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return value

def contract_snapshot(mod) -> Dict[str, Any]:
    result = {}
    for attr in ("DAILY_EVIDENCE_TABLES", "RUNTIME_TABLES", "ACTIVATION_TABLES", "MASTER_CYCLE_TABLES"):
        tables = getattr(mod, attr, None)
        selected = None
        row_count = 0
        errors = []
        if tables:
            try:
                table, rows, errs = mod.inspect(tables, portfolio_scoped=True)
                selected = table
                row_count = len([r for r in (rows or []) if isinstance(r, dict)])
                errors = list(errs or [])
            except Exception as exc:
                errors = [f"{type(exc).__name__}: {exc}"]
        result[attr] = {
            "declared_tables": declared_tables(mod, attr),
            "selected_table": selected,
            "row_count": row_count,
            "errors": errors,
        }
    return result

def classify(entries: List[Dict[str, Any]], consumer_tables: set[str]) -> Dict[str, Any]:
    invokers = [e for e in entries if e["invocation_hits"]]
    persisters = [e for e in entries if e["persistence_hits"] and e["table_mentions"]]
    producers = [e for e in entries if e["success_hits"] and (e["persistence_hits"] or e["invocation_hits"])]

    persistence_tables = sorted({
        t for e in persisters for t in e["table_mentions"]
    })

    matching = sorted(set(persistence_tables) & consumer_tables)
    off_contract = sorted(set(persistence_tables) - consumer_tables)

    if producers and persisters and matching and invokers:
        status = "PRODUCER_INVOKED_AND_PERSISTS_TO_CONSUMER_CONTRACT_TABLE"
    elif producers and persisters and matching and not invokers:
        status = "PRODUCER_PERSISTS_TO_CONSUMER_TABLE_BUT_INVOCATION_PATH_NOT_FOUND"
    elif producers and persisters and off_contract:
        status = "PRODUCER_PERSISTS_BUT_TO_OFF_CONTRACT_TABLE"
    elif producers and not persisters:
        status = "PRODUCER_LOGIC_FOUND_BUT_NO_CONFIRMED_PERSISTENCE_EXECUTION"
    elif invokers and not producers:
        status = "INVOCATION_PATH_FOUND_BUT_NO_CONFIRMED_RECOVERY_PRODUCER"
    else:
        status = "NO_CONFIRMED_PRODUCER_INVOCATION_PERSISTENCE_PATH"

    return {
        "status": status,
        "invocation_candidates": invokers[:15],
        "producer_candidates": producers[:15],
        "persistence_candidates": persisters[:15],
        "persistence_tables": persistence_tables,
        "matching_consumer_tables": matching,
        "off_contract_tables": off_contract,
    }

def main():
    if not P375.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {P375}")

    mod = load_target()
    for name in ("inspect", "RUNTIME_TABLES", "DAILY_EVIDENCE_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing Phase 3.7.5 contract: {name}")

    contracts = contract_snapshot(mod)
    consumer_tables = set(contracts["DAILY_EVIDENCE_TABLES"]["declared_tables"] or [])

    per_target = {}
    for target in TARGETS:
        entries = scan_domain(target)
        per_target[target] = classify(entries, consumer_tables)

    statuses = [d["status"] for d in per_target.values()]

    if all(s == "PRODUCER_INVOKED_AND_PERSISTS_TO_CONSUMER_CONTRACT_TABLE" for s in statuses):
        conclusion = "PRODUCER_INVOCATION_AND_PERSISTENCE_PATHS_EXIST_INVESTIGATE_RUNTIME_EXECUTION_RECENCY"
    elif any(s == "PRODUCER_PERSISTS_TO_CONSUMER_TABLE_BUT_INVOCATION_PATH_NOT_FOUND" for s in statuses):
        conclusion = "RECOVERY_PERSISTENCE_CODE_EXISTS_BUT_PRODUCER_INVOCATION_PATH_GAP_DETECTED"
    elif any(s == "PRODUCER_LOGIC_FOUND_BUT_NO_CONFIRMED_PERSISTENCE_EXECUTION" for s in statuses):
        conclusion = "RECOVERY_PRODUCER_LOGIC_EXISTS_BUT_PERSISTENCE_EXECUTION_GAP_DETECTED"
    elif any(s == "PRODUCER_PERSISTS_BUT_TO_OFF_CONTRACT_TABLE" for s in statuses):
        conclusion = "RECOVERY_PERSISTENCE_EXECUTES_OUTSIDE_PHASE375_CONSUMER_CONTRACT"
    else:
        conclusion = "NO_CONFIRMED_END_TO_END_RECOVERY_PRODUCER_INVOCATION_PERSISTENCE_PATH"

    result = {
        "contract": "PHASE3719314_PHASE375_FRESHNESS_RECOVERY_EVIDENCE_PRODUCER_INVOCATION_PERSISTENCE_EXECUTION_PATH_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contracts": contracts,
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
    (OUT / "phase3719314_invocation_persistence_path.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.14 - Freshness Recovery Evidence Producer Invocation + Persistence Execution Path Diagnostic",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        "",
        "## Phase 3.7.5 Contract Snapshot",
    ]

    for attr, data in contracts.items():
        md.append(
            f"- {attr}: declared=`{data['declared_tables']}` | selected=`{data['selected_table']}` | "
            f"rows={data['row_count']} | errors=`{data['errors']}`"
        )

    md += ["", "## Per-Domain Invocation / Persistence Path"]

    for target in TARGETS:
        data = per_target[target]
        md += [
            "",
            f"### {target}",
            f"- status: **{data['status']}**",
            f"- persistence_tables: `{data['persistence_tables']}`",
            f"- matching_consumer_tables: `{data['matching_consumer_tables']}`",
            f"- off_contract_tables: `{data['off_contract_tables']}`",
            f"- invocation_candidates: `{data['invocation_candidates']}`",
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

    (OUT / "phase3719314_invocation_persistence_path.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE3719314_CONCLUSION=" + conclusion)
    for target in TARGETS:
        data = per_target[target]
        print(target.upper() + "_STATUS=" + data["status"])
        print(target.upper() + "_MATCHING_CONSUMER_TABLES=" + ",".join(data["matching_consumer_tables"]))
        print(target.upper() + "_OFF_CONTRACT_TABLES=" + ",".join(data["off_contract_tables"]))

if __name__ == "__main__":
    main()
