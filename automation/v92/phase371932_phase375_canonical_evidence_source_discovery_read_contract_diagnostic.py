from __future__ import annotations
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

MODE = "READ_ONLY_NO_MUTATION"
ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase371932"

SAFETY_CONTRACT = {
    "phase375_logic_change": False,
    "source_mutation": False,
    "workflow_business_logic_mutation": False,
    "supabase_mutation": False,
    "qualification_counter_mutation": False,
    "synthetic_qualification": False,
    "historical_evidence_rewrite": False,
    "broker_order_enablement": False,
    "real_money_enablement": False,
}

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_source_discovery_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def safe_repr(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple, set)):
        return [safe_repr(x) for x in v]
    if isinstance(v, dict):
        return {str(k): safe_repr(val) for k, val in v.items()}
    return repr(v)

def snapshot(mod) -> Dict[str, Any]:
    names = [
        "DAILY_EVIDENCE_TABLES",
        "ACTIVATION_TABLES",
        "MASTER_CYCLE_TABLES",
        "RUNTIME_TABLES",
        "MAX_BLOCKED_CYCLES",
        "MIN_OBSERVED_CYCLES",
        "MIN_VALID_CYCLES",
    ]
    return {name: safe_repr(getattr(mod, name, None)) for name in names}

def inspect_one(mod, label: str, tables, portfolio_scoped: bool) -> Dict[str, Any]:
    result = {
        "label": label,
        "tables": safe_repr(tables),
        "portfolio_scoped": portfolio_scoped,
        "selected_table": None,
        "row_count": 0,
        "errors": [],
        "sample_keys": [],
    }
    try:
        table, rows, errors = mod.inspect(tables, portfolio_scoped=portfolio_scoped)
        rows = list(rows or [])
        result["selected_table"] = table
        result["row_count"] = len(rows)
        result["errors"] = safe_repr(errors or [])
        if rows and isinstance(rows[0], dict):
            result["sample_keys"] = sorted(str(k) for k in rows[0].keys())
    except Exception as exc:
        result["errors"] = [f"{type(exc).__name__}: {exc}"]
    return result

def main():
    if not TARGET.exists():
        raise SystemExit(f"Missing Phase 3.7.5 source: {TARGET}")

    mod = load_target()
    for name in ("inspect", "DAILY_EVIDENCE_TABLES"):
        if not hasattr(mod, name):
            raise SystemExit(f"Missing required Phase 3.7.5 contract: {name}")

    contract = snapshot(mod)
    discoveries: List[Dict[str, Any]] = []

    daily_tables = getattr(mod, "DAILY_EVIDENCE_TABLES", [])
    discoveries.append(inspect_one(mod, "daily_evidence_portfolio_scoped_true", daily_tables, True))
    discoveries.append(inspect_one(mod, "daily_evidence_portfolio_scoped_false", daily_tables, False))

    for attr, label in (
        ("ACTIVATION_TABLES", "activation"),
        ("MASTER_CYCLE_TABLES", "master_cycle"),
        ("RUNTIME_TABLES", "runtime"),
    ):
        tables = getattr(mod, attr, None)
        if tables:
            discoveries.append(inspect_one(mod, f"{label}_portfolio_scoped_true", tables, True))

    env_presence = {
        "SUPABASE_URL_present": bool(os.getenv("SUPABASE_URL")),
        "SUPABASE_SERVICE_ROLE_KEY_present": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        "SUPABASE_KEY_present": bool(os.getenv("SUPABASE_KEY")),
    }

    daily_true = discoveries[0]
    daily_false = discoveries[1]

    if daily_true["selected_table"]:
        conclusion = "DAILY_EVIDENCE_SOURCE_RESOLVED_PORTFOLIO_SCOPED"
    elif daily_false["selected_table"]:
        conclusion = "DAILY_EVIDENCE_SOURCE_RESOLVED_ONLY_WITHOUT_PORTFOLIO_SCOPE"
    elif daily_true["errors"] or daily_false["errors"]:
        conclusion = "DAILY_EVIDENCE_SOURCE_READ_CONTRACT_ERROR"
    else:
        conclusion = "DAILY_EVIDENCE_SOURCE_UNRESOLVED"

    result = {
        "contract": "PHASE371932_CANONICAL_EVIDENCE_SOURCE_DISCOVERY_READ_CONTRACT_DIAGNOSTIC",
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase375_source": str(TARGET.relative_to(ROOT)),
        "environment_presence": env_presence,
        "phase375_contract_snapshot": contract,
        "discoveries": discoveries,
        "conclusion": conclusion,
        "safety": SAFETY_CONTRACT,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase371932_source_discovery.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = [
        "# Phase 3.7.19.3.2 - Phase 3.7.5 Canonical Evidence Source Discovery",
        "",
        f"- Mode: **{MODE}**",
        f"- Conclusion: **{conclusion}**",
        f"- SUPABASE_URL Present: **{'YES' if env_presence['SUPABASE_URL_present'] else 'NO'}**",
        f"- SUPABASE_SERVICE_ROLE_KEY Present: **{'YES' if env_presence['SUPABASE_SERVICE_ROLE_KEY_present'] else 'NO'}**",
        "",
        "## Phase 3.7.5 Contract Snapshot",
        "",
    ]
    for k, v in contract.items():
        md.append(f"- `{k}`: `{v}`")

    md += ["", "## Read Contract Discovery", ""]
    for d in discoveries:
        md += [
            f"### {d['label']}",
            f"- Tables: `{d['tables']}`",
            f"- Portfolio Scoped: **{'YES' if d['portfolio_scoped'] else 'NO'}**",
            f"- Selected Table: `{d['selected_table']}`",
            f"- Row Count: **{d['row_count']}**",
            f"- Errors: `{d['errors']}`",
            f"- Sample Keys: `{d['sample_keys']}`",
            "",
        ]

    md += [
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

    (OUT / "phase371932_source_discovery.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("PHASE371932_CONCLUSION=" + conclusion)
    print("SUPABASE_URL_PRESENT=" + ("YES" if env_presence["SUPABASE_URL_present"] else "NO"))
    print("SUPABASE_SERVICE_ROLE_KEY_PRESENT=" + ("YES" if env_presence["SUPABASE_SERVICE_ROLE_KEY_present"] else "NO"))
    print("DAILY_EVIDENCE_TABLES=" + repr(contract.get("DAILY_EVIDENCE_TABLES")))
    print("PORTFOLIO_SCOPED_SELECTED_TABLE=" + str(daily_true["selected_table"]))
    print("PORTFOLIO_SCOPED_ROW_COUNT=" + str(daily_true["row_count"]))
    print("PORTFOLIO_SCOPED_ERRORS=" + repr(daily_true["errors"]))
    print("UNSCOPED_SELECTED_TABLE=" + str(daily_false["selected_table"]))
    print("UNSCOPED_ROW_COUNT=" + str(daily_false["row_count"]))
    print("UNSCOPED_ERRORS=" + repr(daily_false["errors"]))

if __name__ == "__main__":
    main()
