#!/usr/bin/env python3
"""
GPT Quant V9.1 Paper Trading 404 Fix v1.

Targets:
  public.gpt_quant_v91_paper_sessions

Reads CURRENT:
  automation/gpt_quant_v91_paper_trading_engine.py

Extracts the literal dict payload used in:
  c.upsert("gpt_quant_v91_paper_sessions", {...}, "...")

Then creates:
- table
- exact payload columns
- UNIQUE conflict index for session_date
- RLS enable
- PostgREST schema reload

No synthetic session rows are inserted.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation" / "gpt_quant_v91_paper_trading_engine.py"
OUT = ROOT / "supabase" / "GPT_QUANT_V91_PAPER_TRADING_404_FIX_V1.sql"

TARGET = "gpt_quant_v91_paper_sessions"
DEFAULT_CONFLICT = "session_date"

TYPE_HINTS = {
    "session_date": "date",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
    "starting_equity": "numeric",
    "ending_equity": "numeric",
    "equity": "numeric",
    "cash": "numeric",
    "pnl": "numeric",
    "daily_pnl": "numeric",
    "daily_pnl_pct": "numeric",
    "return_pct": "numeric",
    "gross_exposure": "numeric",
    "gross_exposure_pct": "numeric",
    "net_exposure": "numeric",
    "net_exposure_pct": "numeric",
    "drawdown": "numeric",
    "drawdown_pct": "numeric",
    "open_positions": "integer",
    "position_count": "integer",
    "trade_count": "integer",
    "orders_count": "integer",
    "fills_count": "integer",
    "strategy_version": "text",
    "mode": "text",
    "status": "text",
    "session_status": "text",
    "paper_only": "boolean",
    "broker_enabled": "boolean",
    "real_money_enabled": "boolean",
    "metadata": "jsonb",
    "diagnostics": "jsonb",
    "details": "jsonb",
}

def pg_type(name: str) -> str:
    if name in TYPE_HINTS:
        return TYPE_HINTS[name]
    low = name.lower()
    if low.endswith("_at"):
        return "timestamptz"
    if low.endswith("_date"):
        return "date"
    if low.startswith(("is_", "has_")) or low.endswith(("_enabled", "_valid", "_only")):
        return "boolean"
    if any(t in low for t in ("count", "positions", "trades", "orders", "fills")):
        return "integer"
    if any(t in low for t in (
        "equity", "cash", "pnl", "return", "pct", "drawdown",
        "exposure", "value", "risk", "weight", "score"
    )):
        return "numeric"
    if any(t in low for t in ("metadata", "details", "diagnostics", "payload", "config")):
        return "jsonb"
    return "text"

class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.keys = set()
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
                    for key_node in payload_arg.keys:
                        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                            self.keys.add(key_node.value)

                    if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                        if isinstance(node.args[2].value, str):
                            self.conflict = node.args[2].value

        self.generic_visit(node)

def main():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)

    v = Visitor()
    v.visit(tree)

    if v.matches == 0:
        raise SystemExit(f"Could not locate literal upsert payload for {TARGET}")

    conflict = v.conflict or DEFAULT_CONFLICT
    conflict_keys = [x.strip() for x in conflict.split(",") if x.strip()]

    keys = sorted(v.keys)
    for key in conflict_keys:
        if key not in keys:
            keys.append(key)
    keys = sorted(set(keys))

    cols = []
    for key in keys:
        suffix = " not null" if key in conflict_keys else ""
        cols.append(f'  "{key}" {pg_type(key)}{suffix}')

    sql = f"""-- GPT Quant V9.1 Paper Trading 404 Fix v1
-- Target: public.{TARGET}
-- Generated from CURRENT Paper Trading upsert payload.
-- Safe to run repeatedly.
-- No synthetic session rows are inserted.

begin;

create table if not exists public.{TARGET} (
  id bigserial primary key,
{",\n".join(cols)}
);

"""

    for key in keys:
        sql += (
            f'alter table public.{TARGET} '
            f'add column if not exists "{key}" {pg_type(key)};\n'
        )

    index_cols = ", ".join(f'"{k}"' for k in conflict_keys)
    index_name = f"{TARGET}_" + "_".join(conflict_keys) + "_uidx"

    sql += f"""
create unique index if not exists {index_name}
on public.{TARGET}({index_cols});

alter table public.{TARGET} enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 paper trading 404 fix v1 installed' as result,
  to_regclass('public.{TARGET}') is not null as table_exists,
  '{conflict}' as conflict_key;
"""

    OUT.write_text(sql, encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "source": str(SOURCE),
        "target_table": TARGET,
        "upsert_matches": v.matches,
        "conflict_key": conflict,
        "payload_columns": keys,
        "sql": str(OUT),
        "synthetic_rows_inserted": 0,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()