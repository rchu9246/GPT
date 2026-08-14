$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.1 Adaptive Risk v4 Diagnostic Hotfix"
Write-Host " Add missing requests dependency"
Write-Host "============================================================"

$root = (Get-Location).Path
$workflowPath = Join-Path $root ".github\workflows\gpt-quant-v91-adaptive-risk-400-fix-v4.yml"

if (-not (Test-Path $workflowPath)) {
    throw "Missing workflow file: $workflowPath"
}

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

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install requests

      - name: Run real Adaptive Risk with full diagnostics
        run: python automation/gpt_quant_v91_adaptive_risk_upsert_diagnostic_v4.py
'@

[System.IO.File]::WriteAllText(
    $workflowPath,
    $workflow,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "Updated:"
Write-Host "  $workflowPath"
Write-Host ""
Write-Host "============================================================"
Write-Host " HOTFIX READY"
Write-Host "============================================================"
Write-Host ""
Write-Host "Next:"
Write-Host "  GitHub Desktop -> Commit -> Push origin"
Write-Host "  Actions -> GPT Quant V9.1 Adaptive Risk 400 Fix v4 - Diagnostic"
Write-Host "  Run workflow"
