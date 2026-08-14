#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation" / "gpt_quant_v91_adaptive_risk_manager.py"
OUT = ROOT / "supabase" / "GPT_QUANT_V91_ADAPTIVE_RISK_400_FIX_V4.sql"

TARGET = "gpt_quant_v91_adaptive_risk_state"
DEFAULT_CONFLICT = "state_date"

TEXT_HINTS = {
    "status", "risk_status", "regime", "mode", "reason", "rationale",
    "decision", "action", "source", "state"
}
JSON_HINTS = {"metadata", "diagnostics", "details", "inputs", "breaches", "config"}

def infer_from_name(name: str) -> str:
    low = name.lower()
    if low.endswith("_at"):
        return "timestamptz"
    if low.endswith("_date") or low == "state_date":
        return "date"
    if low in TEXT_HINTS or low.endswith(("_status", "_regime", "_mode", "_reason")):
        return "text"
    if low in JSON_HINTS or any(t in low for t in ("metadata", "details", "diagnostics", "payload", "config", "inputs")):
        return "jsonb"
    if low.startswith(("is_", "has_")) or low.endswith(("_enabled", "_valid")):
        return "boolean"
    if any(t in low for t in ("count", "days", "rank", "position", "limit")):
        return "integer"
    if any(t in low for t in (
        "score", "pct", "ratio", "risk", "drawdown", "exposure", "volatility",
        "weight", "loss", "value", "equity", "cash", "budget", "concentration",
        "multiplier", "confidence", "var", "shortfall", "pnl"
    )):
        return "numeric"
    return "text"

def infer_from_value(node: ast.AST, key: str) -> str:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "boolean"
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            return "integer"
        if isinstance(node.value, float):
            return "numeric"
        if isinstance(node.value, str):
            return infer_from_name(key)
        if node.value is None:
            return infer_from_name(key)

    if isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
        return "jsonb"

    if isinstance(node, ast.Call):
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr

        if name in {"float", "round", "abs", "min", "max", "n"}:
            return "numeric"
        if name in {"int", "len"}:
            return "integer"
        if name == "bool":
            return "boolean"
        if name == "str":
            return "text"

    return infer_from_name(key)

class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.payload = {}
        self.conflict = None
        self.matches = 0

    def visit_Call(self, node):
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
                    for key_node, value_node in zip(payload_arg.keys, payload_arg.values):
                        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                            key = key_node.value
                            self.payload[key] = infer_from_value(value_node, key)

                    if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                        if isinstance(node.args[2].value, str):
                            self.conflict = node.args[2].value

        self.generic_visit(node)

def cast_using(key: str, pgtype: str) -> str:
    q = f'"{key}"'
    if pgtype == "numeric":
        return f'nullif({q}::text, \'\')::numeric'
    if pgtype == "integer":
        return f'nullif({q}::text, \'\')::integer'
    if pgtype == "boolean":
        return (
            f"case when lower({q}::text) in ('true','t','1','yes') then true "
            f"when lower({q}::text) in ('false','f','0','no') then false else null end"
        )
    if pgtype == "date":
        return f'nullif({q}::text, \'\')::date'
    if pgtype == "timestamptz":
        return f'nullif({q}::text, \'\')::timestamptz'
    if pgtype == "jsonb":
        return f'case when {q} is null then null else {q}::text::jsonb end'
    return f'{q}::text'

def main():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    v = Visitor()
    v.visit(tree)

    if v.matches == 0:
        raise SystemExit(f"Could not find literal upsert payload for {TARGET}")

    conflict = v.conflict or DEFAULT_CONFLICT
    payload = dict(sorted(v.payload.items()))
    payload.setdefault(conflict, "date")

    cols = []
    for key, pgtype in sorted(payload.items()):
        suffix = " not null" if key == conflict else ""
        cols.append(f'  "{key}" {pgtype}{suffix}')

    sql = f"""-- GPT Quant V9.1 Adaptive Risk 400 Fix v4
-- Exact payload/schema alignment generated from CURRENT Python.
-- No synthetic rows inserted.
-- Safe to run repeatedly.

begin;

create table if not exists public.{TARGET} (
  id bigserial primary key,
{",\n".join(cols)}
);

"""

    for key, pgtype in sorted(payload.items()):
        sql += (
            f'alter table public.{TARGET} '
            f'add column if not exists "{key}" {pgtype};\n'
        )

    sql += "\n-- Align existing column types with the actual Python payload.\n"
    for key, pgtype in sorted(payload.items()):
        using_expr = cast_using(key, pgtype)
        sql += (
            f'alter table public.{TARGET} '
            f'alter column "{key}" type {pgtype} using {using_expr};\n'
        )

    sql += f"""
drop index if exists public.{TARGET}_{conflict}_uidx;

create unique index {TARGET}_{conflict}_uidx
on public.{TARGET}("{conflict}");

alter table public.{TARGET} enable row level security;

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 400 fix v4 installed' as result,
  to_regclass('public.{TARGET}') is not null as table_exists,
  '{conflict}' as conflict_key;
"""

    OUT.write_text(sql, encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "target_table": TARGET,
        "conflict_key": conflict,
        "upsert_matches": v.matches,
        "payload_schema": payload,
        "sql": str(OUT),
        "synthetic_rows_inserted": 0,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()