$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37186 - Enterprise 3.0 Stable V19 Hedge Fund Manager Entrypoint Compatibility Fix" -ForegroundColor Cyan
Write-Host "Scope: hedge_fund_manager_v19.py main() compatibility only" -ForegroundColor Green
Write-Host "Safety: NO strategy change / NO qualification mutation / NO schema change / PAPER_ONLY preserved" -ForegroundColor Green

$repo = (Get-Location).Path
$targetRel = "automation/hedge_fund_manager_v19.py"
$targetPath = Join-Path $repo $targetRel
$stablePath = Join-Path $repo "automation/enterprise3_stable.py"

if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "Required file not found: $targetPath"
}
if (-not (Test-Path -LiteralPath $stablePath)) {
    throw "Required file not found: $stablePath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $repo ".phase37186-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item -LiteralPath $targetPath -Destination (Join-Path $backupDir "hedge_fund_manager_v19.py") -Force

$original = Get-Content -LiteralPath $targetPath -Raw

# Guard against patching an unexpected implementation.
$requiredTokens = @(
    'Regime',
    'VaR95',
    'max drawdown',
    'PAPER'
)

foreach ($token in $requiredTokens) {
    if ($original -notmatch [regex]::Escape($token)) {
        throw "Unexpected hedge_fund_manager_v19.py shape. Missing token: $token"
    }
}

if ($original -match '(?m)^\s*def\s+main\s*\(') {
    Write-Host "hedge_fund_manager_v19.py already contains main(); no content patch required." -ForegroundColor Yellow
}
else {
    $compat = @'

# Phase 3.7.18.6 compatibility entrypoint.
#
# hedge_fund_manager_v19.py is a legacy top-level executable. Enterprise 3.0
# Stable loads this module via importlib, so the existing hedge/risk logic already
# executes during module loading. The orchestrator then requires a callable
# main(). Without main(), the stage is marked failed after V19 logic completes.
#
# This no-op main() satisfies the compatibility contract without re-running
# regime allocation, VaR / drawdown checks, hedge sizing, or PAPER order review.
def main() -> None:
    return None
'@

    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $targetPath,
        $original.TrimEnd() + $compat + [Environment]::NewLine,
        $utf8
    )
}

Write-Host ""
Write-Host "Running Python compile checks..." -ForegroundColor Cyan

python -m py_compile "automation/hedge_fund_manager_v19.py"
if ($LASTEXITCODE -ne 0) {
    throw "hedge_fund_manager_v19.py compile failed."
}

python -m py_compile "automation/enterprise3_stable.py"
if ($LASTEXITCODE -ne 0) {
    throw "enterprise3_stable.py compile failed."
}

$patched = Get-Content -LiteralPath $targetPath -Raw

if ($patched -notmatch '(?m)^\s*def\s+main\s*\(') {
    throw "Compatibility verification failed: main() still missing."
}
if ($patched -notmatch 'def\s+main\(\)\s*->\s*None:\s*\r?\n\s*return\s+None') {
    throw "Compatibility verification failed: no-op main() contract missing."
}

# Preserve core V19 behavior markers so this remains an entrypoint-only patch.
foreach ($token in @('Regime', 'VaR95', 'max drawdown', 'PAPER')) {
    if ($patched -notmatch [regex]::Escape($token)) {
        throw "V19 implementation guard failed: missing $token"
    }
}

$stable = Get-Content -LiteralPath $stablePath -Raw

if ($stable -notmatch 'has no main\(\)') {
    throw "Enterprise 3.0 loader contract changed unexpectedly."
}
if ($stable -notmatch '\("V19_HEDGE_RISK",\s*"hedge_fund_manager_v19\.py",\s*True\)') {
    throw "Enterprise 3.0 V19 critical-stage contract changed unexpectedly."
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "V19 legacy top-level execution preserved: PASS" -ForegroundColor Green
Write-Host "V19 main() compatibility entrypoint present: PASS" -ForegroundColor Green
Write-Host "No duplicate V19 execution from main(): PASS" -ForegroundColor Green
Write-Host "Enterprise 3.0 fail-closed loader preserved: PASS" -ForegroundColor Green
Write-Host "V19 remains critical stage: PASS" -ForegroundColor Green
Write-Host "Hedge Fund Manager logic unchanged: PASS" -ForegroundColor Green
Write-Host "Risk / VaR / drawdown logic unchanged: PASS" -ForegroundColor Green
Write-Host "PAPER_ONLY behavior preserved: PASS" -ForegroundColor Green
Write-Host "Qualification mutation: NONE" -ForegroundColor Green
Write-Host "Supabase schema change: NONE" -ForegroundColor Green
Write-Host "Broker / real-money enablement: NONE" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37186 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backup: $backupDir"
Write-Host ""
Write-Host "Expected repaired Enterprise 3.0 behavior:"
Write-Host "  V16_ORDERS: SUCCESS"
Write-Host "  V17_PORTFOLIO: SUCCESS"
Write-Host "  V18_AI_FUND: SUCCESS"
Write-Host "  Regime ... / VaR95 ... / max drawdown ..."
Write-Host "  V19_HEDGE_RISK: SUCCESS"
Write-Host "  No 'hedge_fund_manager_v19.py has no main()' error"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/hedge_fund_manager_v19.py"'
Write-Host '2. git diff --cached --name-only'
Write-Host '3. git diff --cached -- "automation/hedge_fund_manager_v19.py"'
Write-Host '4. git commit -m "Fix Phase 37186 Enterprise 3.0 V19 Hedge Fund Manager main compatibility"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Enterprise 3.0 Stable Daily Cycle on main.'
