#!/usr/bin/env python3
"""
GPT Quant V9.1 Adaptive Risk 404 Fix v2 generator.

Targets:
  gpt_quant_v9_risk_portfolio_state

Reads CURRENT:
  automation/gpt_quant_v91_adaptive_risk_manager.py

The generator detects fields accessed from variable `p`
after the portfolio-state fetch and creates an idempotent
Supabase table migration. No synthetic rows are inserted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation" / "gpt_quant_v91_adaptive_risk_manager.py"
OUT = ROOT / "supabase" / "GPT_QUANT_V91_ADAPTIVE_RISK_404_FIX_V2.sql"

TARGET = "gpt_quant_v9_risk_portfolio_state"

TYPE_HINTS = {
    "state_date": "date",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
    "portfolio_value": "numeric",
    "equity": "numeric",
    "cash": "numeric",
    "market_value": "numeric",
    "gross_exposure": "numeric",
    "gross_exposure_pct": "numeric",
    "net_exposure": "numeric",
    "net_exposure_pct": "numeric",
    "risk_budget": "numeric",
    "risk_budget_pct": "numeric",
    "risk_used": "numeric",
    "risk_used_pct": "numeric",
    "drawdown": "numeric",
    "drawdown_pct": "numeric",
    "volatility": "numeric",
    "volatility_pct": "numeric",
    "concentration": "numeric",
    "concentration_pct": "numeric",
    "open_positions": "integer",
    "position_count": "integer",
    "status": "text",
    "risk_status": "text",
    "regime": "text",
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
    if low.startswith(("is_", "has_")) or low.endswith(("_enabled", "_valid")):
        return "boolean"
    if any(t in low for t in (
        "score","pct","ratio","risk","drawdown","exposure",
        "volatility","weight","loss","value","equity","cash",
        "market_value","budget","concentration"
    )):
        return "numeric"
    if any(t in low for t in ("count","days","limit","rank","position")):
        return "integer"
    if any(t in low for t in ("metadata","details","diagnostics","payload","config")):
        return "jsonb"
    return "text"

def infer_fields(text: str) -> list[str]:
    fields = {"state_date"}

    # Current adaptive risk code uses variable p for portfolio state.
    for match in re.finditer(r'\bp\.get\(\s*["\']([^"\']+)["\']', text):
        fields.add(match.group(1))

    for match in re.finditer(r'\bp\[\s*["\']([^"\']+)["\']\s*\]', text):
        fields.add(match.group(1))

    # Preserve fields named in the fetch query.
    for match in re.finditer(r'(?:order=|select=)([A-Za-z_][A-Za-z0-9_]*)', text):
        fields.add(match.group(1))

    return sorted(fields)

def main():
    text = SOURCE.read_text(encoding="utf-8")

    if TARGET not in text:
        raise SystemExit(f"{TARGET} not referenced by current adaptive risk manager")

    fields = infer_fields(text)

    cols = []
    for field in fields:
        suffix = ""
        if field == "state_date":
            suffix = " not null"
        elif field in ("created_at", "updated_at"):
            suffix = " default now()"
        cols.append(f'  "{field}" {pg_type(field)}{suffix}')

    sql = f"""-- GPT Quant V9.1 Adaptive Risk 404 Fix v2
-- Target: public.{TARGET}
-- Generated from CURRENT adaptive-risk reader.
-- No synthetic portfolio-state rows are inserted.
-- Safe to run repeatedly.

begin;

create table if not exists public.{TARGET} (
  id bigserial primary key,
{",\n".join(cols)}
);

"""

    for field in fields:
        sql += (
            f'alter table public.{TARGET} '
            f'add column if not exists "{field}" {pg_type(field)};\n'
        )

    sql += f"""
create index if not exists {TARGET}_state_date_idx
on public.{TARGET}(state_date desc);

alter table public.{TARGET} enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 404 fix v2 installed' as result,
  to_regclass('public.{TARGET}') is not null as table_exists;
"""

    OUT.write_text(sql, encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "source": str(SOURCE),
        "target_table": TARGET,
        "detected_fields": fields,
        "sql": str(OUT),
        "synthetic_rows_inserted": 0,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()