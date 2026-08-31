from __future__ import annotations
import importlib.util, json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

MODE = "READ_ONLY_NO_MUTATION"
ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "automation" / "v92" / "paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
OUT = ROOT / "artifacts" / "phase371931"

DATE_FIELDS = ("business_date","trade_date","run_date","cycle_date","evidence_date","market_date","date")
TIME_FIELDS = ("event_time","event_at","occurred_at","created_at","updated_at","recorded_at","timestamp","ts")

def load_target():
    spec = importlib.util.spec_from_file_location("phase375_diag_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Phase 3.7.5 source")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def first(row, fields):
    for k in fields:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""

def bizdate(row):
    v = first(row, DATE_FIELDS)
    if v:
        return v[:10]
    t = first(row, TIME_FIELDS)
    return t[:10] if len(t) >= 10 else "UNKNOWN_DATE"

def evt(row):
    return first(row, TIME_FIELDS)

def classify(mod, row):
    state = str(mod.extract_state(row) or "")
    if state in set(getattr(mod, "VALID_STATES", set())):
        return "VALID", state
    if state in set(getattr(mod, "BLOCK_STATES", set())):
        return "BLOCKED", state
    return "UNKNOWN", state

def row_id(row):
    for k in ("id","evidence_id","cycle_id","run_id"):
        if row.get(k) is not None:
            return str(row.get(k))
    return ""

def main():
    mod = load_target()
    for name in ("DAILY_EVIDENCE_TABLES","inspect","extract_state"):
        if not hasattr(mod, name):
            raise RuntimeError("Missing Phase 3.7.5 contract: " + name)

    table, rows, errors = mod.inspect(mod.DAILY_EVIDENCE_TABLES, portfolio_scoped=True)
    rows = [r for r in (rows or []) if isinstance(r, dict)]

    evidence = []
    for i, r in enumerate(rows):
        cls, state = classify(mod, r)
        evidence.append({
            "index": i,
            "id": row_id(r),
            "business_date": bizdate(r),
            "event_time": evt(r),
            "state": state,
            "classification": cls,
            "source_table": table,
        })

    groups = defaultdict(list)
    for x in evidence:
        groups[x["business_date"]].append(x)

    canonical = {}
    superseded = []
    active = []

    for d, items in groups.items():
        ordered = sorted(items, key=lambda x: (x["event_time"], x["id"], x["index"]))
        latest = ordered[-1]
        canonical[d] = latest
        for idx, x in enumerate(ordered):
            if x["classification"] != "BLOCKED":
                continue
            if idx == len(ordered) - 1:
                active.append(x)
            else:
                later_valid = any(y["classification"] == "VALID" for y in ordered[idx+1:])
                superseded.append({
                    **x,
                    "later_valid_exists": later_valid,
                    "latest_state": latest["state"],
                    "latest_classification": latest["classification"],
                    "supersession_candidate": later_valid and latest["classification"] == "VALID",
                })

    candidates = [x for x in superseded if x["supersession_candidate"]]
    result = {
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_table": table,
        "source_errors": errors or [],
        "raw_counts": {
            "observed": len(evidence),
            "valid": sum(x["classification"]=="VALID" for x in evidence),
            "blocked": sum(x["classification"]=="BLOCKED" for x in evidence),
            "unknown": sum(x["classification"]=="UNKNOWN" for x in evidence),
        },
        "canonical_counts": {
            "business_dates": len(canonical),
            "valid": sum(x["classification"]=="VALID" for x in canonical.values()),
            "blocked": sum(x["classification"]=="BLOCKED" for x in canonical.values()),
            "unknown": sum(x["classification"]=="UNKNOWN" for x in canonical.values()),
        },
        "active_blocked_rows": active,
        "superseded_blocked_rows": superseded,
        "canonical_by_business_date": canonical,
        "diagnostic_conclusion": "STALE_BLOCKED_SUPERSESSION_CANDIDATE" if candidates else "NO_CONFIRMED_STALE_BLOCKED_SUPERSESSION",
        "safety": {
            "source_mutation": False,
            "workflow_mutation": False,
            "supabase_mutation": False,
            "qualification_counter_mutation": False,
            "synthetic_qualification": False,
            "historical_evidence_rewrite": False,
            "broker_order_enablement": False,
            "real_money_enablement": False,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/"phase371931_blocked_evidence_provenance.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    md = [
        "# Phase 3.7.19.3.1 - Blocked Evidence Provenance",
        "",
        "- Mode: **%s**" % MODE,
        "- Source Table: `%s`" % table,
        "- Raw Blocked: **%s**" % result["raw_counts"]["blocked"],
        "- Canonical Blocked: **%s**" % result["canonical_counts"]["blocked"],
        "- Superseded Blocked Candidates: **%s**" % len(candidates),
        "- Conclusion: **%s**" % result["diagnostic_conclusion"],
        "",
        "## Active Blocked Rows",
    ]
    if active:
        for x in active:
            md.append("- %s | %s | %s | id %s" % (x["business_date"], x["state"], x["event_time"], x["id"]))
    else:
        md.append("- None")
    md += ["", "## Superseded Blocked Candidates"]
    if candidates:
        for x in candidates:
            md.append("- %s | blocked %s -> latest %s" % (x["business_date"], x["state"], x["latest_state"]))
    else:
        md.append("- None")
    md += ["", "## Canonical State by Business Date"]
    for d in sorted(canonical):
        x = canonical[d]
        md.append("- %s -> %s / %s / %s" % (d, x["state"], x["classification"], x["event_time"]))

    (OUT/"phase371931_blocked_evidence_provenance.md").write_text("\n".join(md)+"\n", encoding="utf-8")

    print("PHASE371931_CONCLUSION=" + result["diagnostic_conclusion"])
    print("SOURCE_TABLE=" + str(table))
    print("RAW_BLOCKED=" + str(result["raw_counts"]["blocked"]))
    print("CANONICAL_BLOCKED=" + str(result["canonical_counts"]["blocked"]))
    print("SUPERSEDED_BLOCKED_CANDIDATES=" + str(len(candidates)))

if __name__ == "__main__":
    main()
