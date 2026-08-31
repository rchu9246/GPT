$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE377 V1.1 - Bridge Diagnostics Heredoc Shell Fix" -ForegroundColor Cyan
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green

$repo = (Get-Location).Path
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase377-production-paper-qualification-evidence-persistence-cross-run-accumulation.yml"
$ymlPath = Join-Path $repo $ymlRel

if (-not (Test-Path $ymlPath)) {
    throw "Missing target workflow: $ymlPath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase377-v11-diagnostics-shell-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $ymlPath (Join-Path $backup (Split-Path $ymlPath -Leaf)) -Force

$raw = Get-Content -LiteralPath $ymlPath -Raw

$old = @'
      - name: Show Phase 3.7.4 bridge diagnostics
        if: always()
        shell: bash
        run: |
          echo "Resolved: ${{ steps.resolve374.outputs.phase374_evidence_resolved }}"
          if [ -f artifacts/phase377/input/phase374_result.json ]; then
            python - <<'PY'
            import json
            from pathlib import Path
            p=Path("artifacts/phase377/input/phase374_result.json")
            d=json.loads(p.read_text(encoding="utf-8"))
            print("daily_validation_state:", d.get("daily_validation_state"))
            print("trade_activity_observed:", d.get("trade_activity_observed"))
            print("checks:", json.dumps(d.get("checks", {}), ensure_ascii=False))
            print("bridge:", json.dumps(d.get("_phase377_bridge", {}), ensure_ascii=False))
            PY
          fi
'@

$new = @'
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

if ($raw.Contains($old)) {
    $patched = $raw.Replace($old, $new)
} else {
    # Fallback regex replacement if whitespace or line endings differ.
    $pattern = '(?ms)^      - name: Show Phase 3\.7\.4 bridge diagnostics\r?\n.*?(?=^      - name: Execute Phase 3\.7\.7)'
    $replacement = $new + "`r`n"
    $patched = [regex]::Replace($raw, $pattern, $replacement, 1)
    if ($patched -eq $raw) {
        throw "Could not locate diagnostics step safely. No changes written."
    }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ymlPath, $patched, $utf8)

$verify = Get-Content -LiteralPath $ymlPath -Raw
$required = @(
    'Show Phase 3.7.4 bridge diagnostics',
    'python -c "import json,pathlib;',
    'daily_validation_state',
    'trade_activity_observed',
    '_phase377_bridge',
    'Execute Phase 3.7.7',
    'BROKER_ORDER_SUBMISSION_ENABLED = False',
    'REAL_MONEY_TRADING_ENABLED = False',
    'HISTORICAL_REWRITE_ALLOWED = False'
)

foreach ($token in $required) {
    if ($verify -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

if ($verify -match "python\s+-\s+<<'PY'") {
    throw "Verification failed: heredoc is still present."
}

Write-Host ""
Write-Host "Diagnostics heredoc removal: PASS" -ForegroundColor Green
Write-Host "GitHub Actions shell-safe diagnostics: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.4 canonical evidence diagnostics preserved: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.7 execution chain preserved: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary preserved: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE377 V1.1 BRIDGE DIAGNOSTICS HEREDOC SHELL FIX DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL change is required." -ForegroundColor Green
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add ".github/workflows/gpt-quant-v92-paper-trading-phase377-production-paper-qualification-evidence-persistence-cross-run-accumulation.yml"'
Write-Host '2. git diff --cached --name-only'
Write-Host '3. git commit -m "Fix Phase 377 V1.1 bridge diagnostics heredoc shell syntax"'
Write-Host '4. git push origin main'
Write-Host '5. Run a NEW Phase 3.7.7 workflow on main.'
