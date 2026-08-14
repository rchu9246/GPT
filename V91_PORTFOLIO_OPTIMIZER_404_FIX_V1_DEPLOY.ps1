$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.1 Optimization Suite"
Write-Host " Portfolio Optimizer 404 Fix v1"
Write-Host " Missing gpt_quant_v91_portfolio_allocations"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation"
$supabaseDir = Join-Path $root "supabase"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $supabaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$targetScript = Join-Path $automationDir "gpt_quant_v91_portfolio_optimizer.py"
$generatorPath = Join-Path $automationDir "gpt_quant_v91_portfolio_optimizer_404_fix_v1.py"
$sqlPath = Join-Path $supabaseDir "GPT_QUANT_V91_PORTFOLIO_OPTIMIZER_404_FIX_V1.sql"
$validatorPath = Join-Path $automationDir "gpt_quant_v91_portfolio_optimizer_schema_check_v1.py"
$workflowPath = Join-Path $workflowDir "gpt-quant-v91-portfolio-optimizer-404-fix-v1.yml"

if (-not (Test-Path $targetScript)) {
    throw "Missing original file: $targetScript"
}

$backupPath = "$targetScript.pre404fixv1.bak"
if (-not (Test-Path $backupPath)) {
    Copy-Item $targetScript $backupPath
}

$generator = @'
#!/usr/bin/env python3
"""
GPT Quant V9.1 Portfolio Optimizer 404 Fix v1.

Targets:
  public.gpt_quant_v91_portfolio_allocations

Reads CURRENT:
  automation/gpt_quant_v91_portfolio_optimizer.py

Extracts the literal dict payload used in:
  c.upsert("gpt_quant_v91_portfolio_allocations", {...}, "...")

Then creates:
- table
- exact payload columns
- UNIQUE conflict index, including composite keys
- RLS enable
- PostgREST schema reload

No synthetic allocation rows are inserted.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation" / "gpt_quant_v91_portfolio_optimizer.py"
OUT = ROOT / "supabase" / "GPT_QUANT_V91_PORTFOLIO_OPTIMIZER_404_FIX_V1.sql"

TARGET = "gpt_quant_v91_portfolio_allocations"
DEFAULT_CONFLICT = "allocation_date,ranking_id"

TYPE_HINTS = {
    "allocation_date": "date",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
    "ranking_id": "text",
    "symbol": "text",
    "stock_id": "text",
    "strategy_version": "text",
    "weight": "numeric",
    "target_weight": "numeric",
    "allocation_weight": "numeric",
    "recommended_weight": "numeric",
    "raw_weight": "numeric",
    "normalized_weight": "numeric",
    "max_single_weight": "numeric",
    "score": "numeric",
    "total_score": "numeric",
    "confidence": "numeric",
    "expected_return": "numeric",
    "expected_return_pct": "numeric",
    "risk_score": "numeric",
    "rank": "integer",
    "rank_position": "integer",
    "position_count": "integer",
    "max_positions": "integer",
    "status": "text",
    "method": "text",
    "reason": "text",
    "rationale": "text",
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
    if any(t in low for t in ("count", "rank", "position", "limit")):
        return "integer"
    if any(t in low for t in (
        "weight", "score", "confidence", "return", "risk",
        "pct", "ratio", "exposure", "allocation"
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

    sql = f"""-- GPT Quant V9.1 Portfolio Optimizer 404 Fix v1
-- Target: public.{TARGET}
-- Generated from CURRENT Portfolio Optimizer upsert payload.
-- Safe to run repeatedly.
-- No synthetic allocation rows are inserted.

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
  'GPT Quant V9.1 portfolio optimizer 404 fix v1 installed' as result,
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
'@

$validator = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
TABLE = "gpt_quant_v91_portfolio_allocations"

def main():
    query = urllib.parse.urlencode({
        "select": "allocation_date,ranking_id",
        "order": "allocation_date.desc",
        "limit": "1",
    })

    url = f"{URL}/rest/v1/{TABLE}?{query}"

    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
    }

    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            rows = json.loads(raw) if raw else []

            print(json.dumps({
                "status": "PASS",
                "http_status": response.status,
                "table": TABLE,
                "reachable": True,
                "rows_returned": len(rows) if isinstance(rows, list) else None,
                "note": "0 rows is acceptable; schema/API reachability only.",
            }, indent=2))

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

if __name__ == "__main__":
    main()
'@

$workflow = @'
name: GPT Quant V9.1 Portfolio Optimizer 404 Fix v1 - Schema Check

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  portfolio-optimizer-schema-check-v1:
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

      - name: Validate Portfolio Optimizer allocation schema endpoint
        run: python automation/gpt_quant_v91_portfolio_optimizer_schema_check_v1.py
'@

[System.IO.File]::WriteAllText($generatorPath, $generator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($validatorPath, $validator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($workflowPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Generating Portfolio Optimizer SQL from current upsert payload..."
python $generatorPath

if ($LASTEXITCODE -ne 0) {
    throw "Failed to inspect current Portfolio Optimizer payload."
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
Write-Host "   supabase\GPT_QUANT_V91_PORTFOLIO_OPTIMIZER_404_FIX_V1.sql"
Write-Host "3. Copy ALL -> Paste -> Run"
Write-Host ""
Write-Host "Expected:"
Write-Host "   table_exists = true"
Write-Host "   conflict_key = allocation_date,ranking_id"
Write-Host ""
Write-Host "Then:"
Write-Host "   GitHub Desktop -> Commit -> Push origin"
Write-Host "   Actions -> GPT Quant V9.1 Portfolio Optimizer 404 Fix v1 - Schema Check"
Write-Host ""
Write-Host "If green:"
Write-Host "   Rerun GPT Quant V9.1 Optimization Suite"
Write-Host ""
Write-Host "Important:"
Write-Host "   UNIQUE(allocation_date, ranking_id) is created."
Write-Host "   No synthetic portfolio allocation rows are inserted."
