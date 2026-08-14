$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.1 Optimization Suite"
Write-Host " Adaptive Risk 404 Fix"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation"
$supabaseDir = Join-Path $root "supabase"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $supabaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$targetScript = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_manager.py"
$generatorPath = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_404_fix.py"
$sqlPath = Join-Path $supabaseDir "GPT_QUANT_V91_ADAPTIVE_RISK_404_FIX.sql"
$validatorPath = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_schema_check.py"
$workflowPath = Join-Path $workflowDir "gpt-quant-v91-adaptive-risk-404-fix.yml"

if (-not (Test-Path $targetScript)) {
    throw "Missing original file: $targetScript"
}

$backupPath = "$targetScript.pre404fix.bak"
if (-not (Test-Path $backupPath)) {
    Copy-Item $targetScript $backupPath
}

$generator = @'
#!/usr/bin/env python3
"""
GPT Quant V9.1 Adaptive Risk 404 Fix generator.

Reads the CURRENT repository's:
  automation/gpt_quant_v91_adaptive_risk_manager.py

It detects fields read from variable `s` after:
  c.get("gpt_quant_v9_risk_summaries", ...)

Then creates an idempotent Supabase migration for the missing table.
No fake risk row is inserted.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation" / "gpt_quant_v91_adaptive_risk_manager.py"
OUT = ROOT / "supabase" / "GPT_QUANT_V91_ADAPTIVE_RISK_404_FIX.sql"
TARGET = "gpt_quant_v9_risk_summaries"

TYPE_HINTS = {
    "risk_date": "date",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
    "risk_score": "numeric",
    "max_drawdown": "numeric",
    "max_drawdown_pct": "numeric",
    "var_95": "numeric",
    "var_95_pct": "numeric",
    "expected_shortfall": "numeric",
    "expected_shortfall_pct": "numeric",
    "gross_exposure": "numeric",
    "gross_exposure_pct": "numeric",
    "net_exposure": "numeric",
    "net_exposure_pct": "numeric",
    "concentration": "numeric",
    "concentration_pct": "numeric",
    "liquidity_score": "numeric",
    "daily_loss_pct": "numeric",
    "volatility": "numeric",
    "volatility_pct": "numeric",
    "risk_status": "text",
    "status": "text",
    "breaches": "jsonb",
    "diagnostics": "jsonb",
    "metadata": "jsonb",
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
    if any(t in low for t in ("score","pct","ratio","risk","drawdown","exposure","volatility","weight","loss","var","shortfall","liquidity")):
        return "numeric"
    if any(t in low for t in ("count","days","limit","rank","position")):
        return "integer"
    if any(t in low for t in ("breaches","metadata","details","diagnostics","payload","config")):
        return "jsonb"
    return "text"

def infer_fields(text: str) -> list[str]:
    fields = {"risk_date"}

    # Most V9.1 code reads the latest row into variable `s`.
    for match in re.finditer(r'\bs\.get\(\s*["\']([^"\']+)["\']', text):
        fields.add(match.group(1))

    # Direct dict indexing fallback: s["field"] / s['field']
    for match in re.finditer(r'\bs\[\s*["\']([^"\']+)["\']\s*\]', text):
        fields.add(match.group(1))

    # If the source query orders/filters by a field, preserve it.
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
        if field == "risk_date":
            suffix = " not null"
        elif field in ("created_at", "updated_at"):
            suffix = " default now()"
        cols.append(f'  "{field}" {pg_type(field)}{suffix}')

    sql = f"""-- GPT Quant V9.1 Adaptive Risk 404 Fix
-- Generated from CURRENT adaptive-risk reader.
-- No synthetic/fake risk data is inserted.
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
create index if not exists {TARGET}_risk_date_idx
on public.{TARGET}(risk_date desc);

alter table public.{TARGET} enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anon write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 404 fix installed' as result,
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
TABLE = "gpt_quant_v9_risk_summaries"

def request():
    query = urllib.parse.urlencode({
        "select": "risk_date",
        "order": "risk_date.desc",
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
                "note": "0 rows is acceptable; this check verifies schema/API reachability only.",
            }, indent=2))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

if __name__ == "__main__":
    request()
'@

$workflow = @'
name: GPT Quant V9.1 Adaptive Risk 404 Fix - Schema Check

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  adaptive-risk-schema-check:
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

      - name: Validate Adaptive Risk schema endpoint
        run: python automation/gpt_quant_v91_adaptive_risk_schema_check.py
'@

[System.IO.File]::WriteAllText($generatorPath, $generator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($validatorPath, $validator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($workflowPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Generating exact Adaptive Risk SQL from current source..."
python $generatorPath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to inspect current adaptive risk manager."
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
Write-Host "1. Open Supabase -> SQL Editor -> New query"
Write-Host "2. Copy ALL contents of:"
Write-Host "   supabase\GPT_QUANT_V91_ADAPTIVE_RISK_404_FIX.sql"
Write-Host "3. Paste -> Run"
Write-Host ""
Write-Host "Expected:"
Write-Host "   table_exists = true"
Write-Host ""
Write-Host "Then:"
Write-Host "   GitHub Desktop -> Commit -> Push origin"
Write-Host "   Actions -> GPT Quant V9.1 Adaptive Risk 404 Fix - Schema Check"
Write-Host "   If green -> rerun GPT Quant V9.1 Optimization Suite"
Write-Host ""
Write-Host "Important:"
Write-Host "   No synthetic risk rows are inserted."
Write-Host "   This fix only restores the missing PostgREST table/schema."
