$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.1 Optimization Suite"
Write-Host " Confidence Calibration 404 Fix"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation"
$supabaseDir = Join-Path $root "supabase"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $supabaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$targetScript = Join-Path $automationDir "gpt_quant_v91_confidence_calibration.py"
$fixScript = Join-Path $automationDir "gpt_quant_v91_confidence_calibration_404_fix.py"
$sqlPath = Join-Path $supabaseDir "GPT_QUANT_V91_CONFIDENCE_CALIBRATION_404_FIX.sql"
$validatorPath = Join-Path $automationDir "gpt_quant_v91_confidence_calibration_schema_check.py"
$workflowPath = Join-Path $workflowDir "gpt-quant-v91-confidence-calibration-404-fix.yml"

if (-not (Test-Path $targetScript)) {
    throw "Missing original file: $targetScript"
}

# Keep an untouched backup once.
$backupPath = "$targetScript.pre404fix.bak"
if (-not (Test-Path $backupPath)) {
    Copy-Item $targetScript $backupPath
}

$fixPython = @'
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
TABLE = "gpt_quant_v91_confidence_calibration"

def request(method, query="", payload=None, prefer=None):
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
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

def main():
    status, rows = request(
        "GET",
        urllib.parse.urlencode({
            "select": "ranking_id",
            "limit": "1",
        })
    )
    print(json.dumps({
        "status": "PASS",
        "http_status": status,
        "table": TABLE,
        "reachable": True,
        "sample_rows": len(rows) if isinstance(rows, list) else None,
    }, indent=2))

if __name__ == "__main__":
    main()
'@

$workflow = @'
name: GPT Quant V9.1 Confidence Calibration 404 Fix - Schema Check

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  confidence-calibration-schema-check:
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

      - name: Validate schema endpoint
        run: python automation/gpt_quant_v91_confidence_calibration_schema_check.py
'@

[System.IO.File]::WriteAllText($fixScript, $fixPython, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($validatorPath, $validator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($workflowPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Step 1/2 - Generate exact SQL from current V9.1 Python payload..."
python $fixScript
if ($LASTEXITCODE -ne 0) {
    throw "Failed to inspect current confidence calibration script."
}

Write-Host ""
Write-Host "Created:"
Write-Host "  $sqlPath"
Write-Host "  $fixScript"
Write-Host "  $validatorPath"
Write-Host "  $workflowPath"
Write-Host ""
Write-Host "============================================================"
Write-Host " IMPORTANT - ONE MANUAL SUPABASE STEP REQUIRED"
Write-Host "============================================================"
Write-Host ""
Write-Host "Open Supabase -> SQL Editor -> New query"
Write-Host "Copy ALL contents of:"
Write-Host "  supabase\GPT_QUANT_V91_CONFIDENCE_CALIBRATION_404_FIX.sql"
Write-Host "Paste -> Run"
Write-Host ""
Write-Host "Expected final result:"
Write-Host "  table_exists = true"
Write-Host ""
Write-Host "Then:"
Write-Host "  GitHub Desktop -> Commit -> Push origin"
Write-Host "  GitHub Actions -> Confidence Calibration 404 Fix - Schema Check -> Run"
Write-Host "  If green, rerun: GPT Quant V9.1 Optimization Suite"
Write-Host ""
Write-Host "Root cause fixed:"
Write-Host "  /rest/v1/gpt_quant_v91_confidence_calibration 404"
Write-Host "  on_conflict=ranking_id now has a matching unique index"
