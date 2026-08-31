$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE377 V1.2 - Targeted Bridge Diagnostics Heredoc Replacement Fix" -ForegroundColor Cyan
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green

$repo = (Get-Location).Path
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase377-production-paper-qualification-evidence-persistence-cross-run-accumulation.yml"
$ymlPath = Join-Path $repo $ymlRel

if (-not (Test-Path $ymlPath)) {
    throw "Missing target workflow: $ymlPath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase377-v12-targeted-heredoc-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $ymlPath (Join-Path $backup (Split-Path $ymlPath -Leaf)) -Force

$raw = Get-Content -LiteralPath $ymlPath -Raw

# Replace only the diagnostics step. Do not inspect or alter heredocs elsewhere in the workflow.
$pattern = '(?ms)^      - name: Show Phase 3\.7\.4 bridge diagnostics\r?\n.*?(?=^      - name: Execute Phase 3\.7\.7)'

$replacement = @'
      - name: Show Phase 3.7.4 bridge diagnostics
        if: always()
        shell: bash
        run: |
          set -euo pipefail
          echo "Resolved: ${{ steps.resolve374.outputs.phase374_evidence_resolved }}"
          if [ -f artifacts/phase377/input/phase374_result.json ]; then
            python -c "import json,pathlib; p=pathlib.Path('artifacts/phase377/input/phase374_result.json'); d=json.loads(p.read_text(encoding='utf-8')); print('daily_validation_state:', d.get('daily_validation_state')); print('trade_activity_observed:', d.get('trade_activity_observed')); print('checks:', json.dumps(d.get('checks', {}), ensure_ascii=False)); print('bridge:', json.dumps(d.get('_phase377_bridge', {}), ensure_ascii=False))"
          else
            echo "No resolved Phase 3.7.4 canonical evidence file is present."
          fi

'@

$patched = [regex]::Replace($raw, $pattern, $replacement, 1)

if ($patched -eq $raw) {
    # If it was already converted by V1.1, keep as-is and continue with targeted validation.
    if ($raw -notmatch '(?ms)^      - name: Show Phase 3\.7\.4 bridge diagnostics\r?\n.*?python -c "import json,pathlib;') {
        throw "Could not locate or validate the Phase 3.7.4 bridge diagnostics step safely."
    }
    $patched = $raw
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ymlPath, $patched, $utf8)

# Targeted validation ONLY inside the diagnostics step.
$verify = Get-Content -LiteralPath $ymlPath -Raw

$diagMatch = [regex]::Match(
    $verify,
    '(?ms)^      - name: Show Phase 3\.7\.4 bridge diagnostics\r?\n.*?(?=^      - name: Execute Phase 3\.7\.7)'
)

if (-not $diagMatch.Success) {
    throw "Targeted validation failed: diagnostics step not found."
}

$diag = $diagMatch.Value

$requiredDiag = @(
    'Show Phase 3.7.4 bridge diagnostics',
    'python -c "import json,pathlib;',
    'daily_validation_state',
    'trade_activity_observed',
    '_phase377_bridge'
)

foreach ($token in $requiredDiag) {
    if ($diag -notmatch [regex]::Escape($token)) {
        throw "Targeted diagnostics verification failed: missing $token"
    }
}

if ($diag -match "python\s+-\s+<<'PY'") {
    throw "Targeted diagnostics verification failed: heredoc remains inside diagnostics step."
}

$requiredWorkflow = @(
    'Resolve latest Phase 3.7.4 canonical evidence',
    'Execute Phase 3.7.7',
    'Publish summary',
    'Upload persistence evidence',
    'Enforce persistence safety result',
    'BROKER_ORDER_SUBMISSION_ENABLED = False',
    'REAL_MONEY_TRADING_ENABLED = False',
    'HISTORICAL_REWRITE_ALLOWED = False'
)

foreach ($token in $requiredWorkflow) {
    if ($verify -notmatch [regex]::Escape($token)) {
        throw "Workflow preservation verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Targeted diagnostics step replacement: PASS" -ForegroundColor Green
Write-Host "Diagnostics heredoc removed from target step: PASS" -ForegroundColor Green
Write-Host "Other workflow heredocs ignored/preserved: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.4 canonical evidence resolver preserved: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.7 execution chain preserved: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary preserved: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE377 V1.2 TARGETED HEREDOC REPLACEMENT FIX DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL change is required." -ForegroundColor Green
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add ".github/workflows/gpt-quant-v92-paper-trading-phase377-production-paper-qualification-evidence-persistence-cross-run-accumulation.yml"'
Write-Host '2. git diff --cached --name-only'
Write-Host '3. git commit -m "Fix Phase 377 V1.2 targeted bridge diagnostics heredoc replacement"'
Write-Host '4. git push origin main'
Write-Host '5. Run a NEW Phase 3.7.7 workflow on main.'
