$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.1 Optimization Suite"
Write-Host " Adaptive Risk 400 Fix v4"
Write-Host " Payload/Schema Alignment + Full Diagnostics"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation"
$supabaseDir = Join-Path $root "supabase"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $supabaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$targetScript = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_manager.py"
$generatorPath = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_400_fix_v4.py"
$sqlPath = Join-Path $supabaseDir "GPT_QUANT_V91_ADAPTIVE_RISK_400_FIX_V4.sql"
$diagnosticPath = Join-Path $automationDir "gpt_quant_v91_adaptive_risk_upsert_diagnostic_v4.py"
$workflowPath = Join-Path $workflowDir "gpt-quant-v91-adaptive-risk-400-fix-v4.yml"

if (-not (Test-Path $targetScript)) {
    throw "Missing original file: $targetScript"
}

$backupPath = "$targetScript.pre400fixv4.bak"
if (-not (Test-Path $backupPath)) {
    Copy-Item $targetScript $backupPath
}

$generator = @'
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
'@

$diagnostic = @'
#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "automation" / "gpt_quant_v91_adaptive_risk_manager.py"

def main():
    env = os.environ.copy()

    proc = subprocess.run(
        [
            sys.executable,
            str(TARGET),
            "--base-risk-budget",
            env.get("V91_BASE_RISK_BUDGET", "0.60"),
        ],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    print("=== ADAPTIVE RISK STDOUT ===")
    print(proc.stdout or "")
    print("=== ADAPTIVE RISK STDERR ===")
    print(proc.stderr or "")

    if proc.returncode != 0:
        print("=== V4 RESULT: FAILED ===")
        print("Copy the complete error above; v4 preserves the real Supabase response.")
        return proc.returncode

    print("=== V4 RESULT: PASS ===")
    print("Real Adaptive Risk execution completed successfully.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'@

$workflow = @'
name: GPT Quant V9.1 Adaptive Risk 400 Fix v4 - Diagnostic

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  adaptive-risk-v4-diagnostic:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      V91_BASE_RISK_BUDGET: "0.60"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Upgrade pip
        run: python -m pip install --upgrade pip

      - name: Run real Adaptive Risk with full diagnostics
        run: python automation/gpt_quant_v91_adaptive_risk_upsert_diagnostic_v4.py
'@

[System.IO.File]::WriteAllText($generatorPath, $generator, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($diagnosticPath, $diagnostic, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($workflowPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Generating exact v4 SQL from current Adaptive Risk upsert..."
python $generatorPath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to inspect current Adaptive Risk payload."
}

Write-Host ""
Write-Host "Created:"
Write-Host "  $sqlPath"
Write-Host "  $generatorPath"
Write-Host "  $diagnosticPath"
Write-Host "  $workflowPath"
Write-Host ""
Write-Host "============================================================"
Write-Host " ONE MANUAL SUPABASE STEP"
Write-Host "============================================================"
Write-Host ""
Write-Host "1. Supabase -> SQL Editor -> New query"
Write-Host "2. Open:"
Write-Host "   supabase\GPT_QUANT_V91_ADAPTIVE_RISK_400_FIX_V4.sql"
Write-Host "3. Copy ALL -> Paste -> Run"
Write-Host ""
Write-Host "Expected:"
Write-Host "   table_exists = true"
Write-Host "   conflict_key = state_date"
Write-Host ""
Write-Host "Then:"
Write-Host "   GitHub Desktop -> Commit -> Push origin"
Write-Host "   Actions -> GPT Quant V9.1 Adaptive Risk 400 Fix v4 - Diagnostic"
Write-Host ""
Write-Host "If green:"
Write-Host "   Rerun GPT Quant V9.1 Optimization Suite"
Write-Host ""
Write-Host "If red:"
Write-Host "   Open failed step and send the FULL error body."
Write-Host "   v4 is designed to expose the real PostgREST/Supabase error."
