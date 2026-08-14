#!/usr/bin/env python3
"""
GPT Quant V9.1 Confidence Calibration 404 Fix helper.

Reads the CURRENT repository's original
automation/gpt_quant_v91_confidence_calibration.py with Python AST,
extracts the dict keys actually sent to:
    gpt_quant_v91_confidence_calibration
and generates a schema-compatible Supabase SQL migration.

This avoids guessing the original V9.1 payload schema.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation" / "gpt_quant_v91_confidence_calibration.py"
OUT = ROOT / "supabase" / "GPT_QUANT_V91_CONFIDENCE_CALIBRATION_404_FIX.sql"

TARGET = "gpt_quant_v91_confidence_calibration"

# Conservative PostgreSQL types for common calibration fields.
TYPE_HINTS = {
    "ranking_id": "text",
    "strategy_version": "text",
    "symbol": "text",
    "stock_id": "text",
    "trade_date": "date",
    "ranking_date": "date",
    "calibration_date": "date",
    "run_date": "date",
    "rank": "integer",
    "rank_position": "integer",
    "sample_count": "integer",
    "confidence": "numeric",
    "original_confidence": "numeric",
    "raw_confidence": "numeric",
    "calibrated_confidence": "numeric",
    "confidence_before": "numeric",
    "confidence_after": "numeric",
    "confidence_delta": "numeric",
    "calibration_factor": "numeric",
    "score": "numeric",
    "total_score": "numeric",
    "risk_score": "numeric",
    "expected_return": "numeric",
    "expected_return_pct": "numeric",
    "weight": "numeric",
    "target_weight": "numeric",
    "recommended_weight": "numeric",
    "is_calibrated": "boolean",
    "enabled": "boolean",
    "status": "text",
    "method": "text",
    "calibration_method": "text",
    "reason": "text",
    "rationale": "text",
    "notes": "text",
    "metadata": "jsonb",
    "diagnostics": "jsonb",
    "details": "jsonb",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
}

class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.keys = set()
        self.matches = 0

    def visit_Call(self, node):
        # Match c.upsert("gpt_quant_v91_confidence_calibration", {...}, ...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "upsert":
            if len(node.args) >= 2:
                table_arg = node.args[0]
                payload_arg = node.args[1]
                if (
                    isinstance(table_arg, ast.Constant)
                    and table_arg.value == TARGET
                    and isinstance(payload_arg, ast.Dict)
                ):
                    self.matches += 1
                    for key_node in payload_arg.keys:
                        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                            self.keys.add(key_node.value)
        self.generic_visit(node)

def pg_type(name: str) -> str:
    if name in TYPE_HINTS:
        return TYPE_HINTS[name]
    low = name.lower()
    if low.endswith("_at"):
        return "timestamptz"
    if low.endswith("_date"):
        return "date"
    if low.startswith(("is_", "has_")) or low.endswith(("_enabled", "_valid")):
        return "boolean"
    if any(token in low for token in ("score", "confidence", "weight", "rate", "pct", "ratio", "return", "risk")):
        return "numeric"
    if any(token in low for token in ("count", "rank", "position", "days", "limit")):
        return "integer"
    if any(token in low for token in ("metadata", "details", "diagnostics", "payload", "config")):
        return "jsonb"
    return "text"

def main():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    visitor = Visitor()
    visitor.visit(tree)

    if visitor.matches == 0:
        raise SystemExit(
            "Could not locate a literal upsert payload for "
            "gpt_quant_v91_confidence_calibration."
        )

    keys = sorted(visitor.keys)
    if "ranking_id" not in keys:
        keys.insert(0, "ranking_id")

    cols = []
    for key in keys:
        col_type = pg_type(key)
        suffix = ""
        if key == "ranking_id":
            suffix = " not null"
        elif key == "created_at":
            suffix = " default now()"
        elif key == "updated_at":
            suffix = " default now()"
        cols.append(f'  "{key}" {col_type}{suffix}')

    sql = f"""-- GPT Quant V9.1 Confidence Calibration 404 Fix
-- Generated from the CURRENT Python upsert payload.
-- Safe to run repeatedly.

begin;

create table if not exists public.{TARGET} (
  id bigserial primary key,
{",\n".join(cols)}
);

-- Add any payload columns that may be absent on an older partial table.
"""

    for key in keys:
        if key == "ranking_id":
            sql += f'alter table public.{TARGET} add column if not exists "{key}" {pg_type(key)};\n'
        else:
            sql += f'alter table public.{TARGET} add column if not exists "{key}" {pg_type(key)};\n'

    sql += f"""
create unique index if not exists {TARGET}_ranking_id_uidx
on public.{TARGET}(ranking_id);

alter table public.{TARGET} enable row level security;

-- Service-role GitHub Actions bypasses RLS.
-- Read-only dashboard access may be enabled separately if needed.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 confidence calibration 404 fix installed' as result,
  to_regclass('public.{TARGET}') is not null as table_exists;
"""

    OUT.write_text(sql, encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "source": str(SOURCE),
        "target_table": TARGET,
        "upsert_matches": visitor.matches,
        "payload_columns": keys,
        "sql": str(OUT),
    }, indent=2))

if __name__ == "__main__":
    main()