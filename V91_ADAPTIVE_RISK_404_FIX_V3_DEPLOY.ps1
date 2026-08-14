$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.1 Optimization Suite"
Write-Host " Adaptive Risk 404 Fix v3"
Write-Host " Output State + Upsert Constraint"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation"
$supabaseDir = Join-Path $root "supabase"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $supabaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$targetScript = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_manager.py"
$generatorPath = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_404_fix_v3.py"
$sqlPath = Join-Path $supabaseDir "GPT_QUANT_V91_ADAPTIVE_RISK_404_FIX_V3.sql"
$validatorPath = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_schema_check_v3.py"
$workflowPath = Join-Path $workflowDir "gpt-quant-v91-adaptive-risk-404-fix-v3.yml"

if (-not (Test-Path $targetScript)) {
    throw "Missing original file: $targetScript"
}

$generator = @'
#!/usr/bin/env python3
"""
GPT Quant V9.1 Adaptive Risk 404 Fix v3 generator.

Targets:
  public.gpt_quant_v91_adaptive_risk_state

Reads CURRENT:
  automation/gpt_quant_v91_adaptive_risk_manager.py

Extracts the literal dict payload used in:
  c.upsert("gpt_quant_v91_adaptive_risk_state", {...}, "state_date")

Then creates:
- table
- all required payload columns
- UNIQUE(state_date) index for PostgREST on_conflict
- RLS enable
- schema reload

No synthetic rows are inserted.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation" / "gpt_quant_v91_adaptive_risk_manager.py"
OUT = ROOT / "supabase" / "GPT_QUANT_V91_ADAPTIVE_RISK_404_FIX_V3.sql"

TARGET = "gpt_quant_v91_adaptive_risk_state"
CONFLICT = "state_date"

TYPE_HINTS = {
    "state_date": "date",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
    "base_risk_budget": "numeric",
    "adaptive_risk_budget": "numeric",
    "risk_budget": "numeric",
    "risk_multiplier": "numeric",
    "risk_score": "numeric",
    "portfolio_risk_score": "numeric",
    "drawdown": "numeric",
    "drawdown_pct": "numeric",
    "volatility": "numeric",
    "volatility_pct": "numeric",
    "gross_exposure": "numeric",
    "gross_exposure_pct": "numeric",
    "net_exposure": "numeric",
    "net_exposure_pct": "numeric",
    "concentration": "numeric",
    "concentration_pct": "numeric",
    "confidence": "numeric",
    "status": "text",
    "risk_status": "text",
    "regime": "text",
    "mode": "text",
    "reason": "text",
    "rationale": "text",
    "metadata": "jsonb",
    "diagnostics": "jsonb",
    "details": "jsonb",
    "inputs": "jsonb",
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
        "market_value","budget","concentration","multiplier","confidence"
    )):
        return "numeric"
    if any(t in low for t in ("count","days","limit","rank","position")):
        return "integer"
    if any(t in low for t in ("metadata","details","diagnostics","payload","config","inputs")):
        return "jsonb"
    return "text"

class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.keys = set()
        self.matches = 0
        self.conflict = None

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
    visitor = Visitor()
    visitor.visit(tree)

    if visitor.matches == 0:
        raise SystemExit(
            f"Could not locate literal upsert payload for {TARGET}"
        )

    conflict = visitor.conflict or CONFLICT
    keys = sorted(visitor.keys)
    if conflict not in keys:
        keys.insert(0, conflict)

    cols = []
    for key in keys:
        suffix = ""
        if key == conflict:
            suffix = " not null"
        elif key in ("created_at", "updated_at"):
            suffix = " default now()"
        cols.append(f'  "{key}" {pg_type(key)}{suffix}')

    sql = f"""-- GPT Quant V9.1 Adaptive Risk 404 Fix v3
-- Target: public.{TARGET}
-- Generated from CURRENT Adaptive Risk upsert payload.
-- Safe to run repeatedly.
-- No synthetic rows are inserted.

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

    sql += f"""
create unique index if not exists {TARGET}_{conflict}_uidx
on public.{TARGET}("{conflict}");

alter table public.{TARGET} enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 404 fix v3 installed' as result,
  to_regclass('public.{TARGET}') is not null as table_exists,
  '{conflict}' as conflict_key;
"""

    OUT.write_text(sql, encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "source": str(SOURCE),
        "target_table": TARGET,
        "upsert_matches": visitor.matches,
        "conflict_key": conflict,
        "payload_columns": keys,
        "sql": str(OUT),
        "synthetic_rows_inserted": 0,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
'@

$validator = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
TABLE = "gpt_quant_v91_adaptive_risk_state"

def api(method, query="", payload=None, prefer=None):
    url = f"{URL}/rest/v1/{TABLE}"
    if query:
        url += "?" + query

    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, headers=headers, data=data, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else None
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

def main():
    status, rows = api(
        "GET",
        urllib.parse.urlencode({
            "select": "state_date",
            "order": "state_date.desc",
            "limit": "1",
        }),
    )

    print(json.dumps({
        "status": "PASS",
        "http_status": status,
        "table": TABLE,
        "reachable": True,
        "rows_returned": len(rows) if isinstance(rows, list) else None,
        "note": "Read-only validation; no synthetic row inserted.",
    }, indent=2))

if __name__ == "__main__":
    main()
'@

$workflow = @'
name: GPT Quant V9.1 Adaptive Risk 404 Fix v3 - Schema Check

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  adaptive-risk-schema-check-v3:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Validate Adaptive Risk output-state schema endpoint
        run: python automation/gpt_quant_v91_adaptive_risk_schema_check_v3.py
'@

[System.IO.File]::WriteAllText($generatorPath, $generator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($validatorPath, $validator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($workflowPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Generating exact v3 SQL from current Adaptive Risk upsert..."
python $generatorPath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to inspect current Adaptive Risk upsert payload."
}

Write-Host ""
Write-Host "Created:"
Write-Host "  $sqlPath"
Write-Host "  $generatorPath"
Write-Host "  $validatorPath"
Write-Host "  $workflowPath"
Write-Host ""
Write-Host "============================================================"
Write-Host " ONE MANUAL SUPABASE STEP"
Write-Host "============================================================"
Write-Host ""
Write-Host "1. Supabase -> SQL Editor -> New query"
Write-Host "2. Open:"
Write-Host "   supabase\GPT_QUANT_V91_ADAPTIVE_RISK_404_FIX_V3.sql"
Write-Host "3. Copy ALL -> Paste -> Run"
Write-Host ""
Write-Host "Expected:"
Write-Host "   table_exists = true"
Write-Host "   conflict_key = state_date"
Write-Host ""
Write-Host "Then:"
Write-Host "   GitHub Desktop -> Commit -> Push origin"
Write-Host "   Actions -> GPT Quant V9.1 Adaptive Risk 404 Fix v3 - Schema Check"
Write-Host "   If green -> rerun GPT Quant V9.1 Optimization Suite"
Write-Host ""
Write-Host "Important:"
Write-Host "   UNIQUE(state_date) is created for PostgREST on_conflict."
Write-Host "   No synthetic Adaptive Risk row is inserted."
