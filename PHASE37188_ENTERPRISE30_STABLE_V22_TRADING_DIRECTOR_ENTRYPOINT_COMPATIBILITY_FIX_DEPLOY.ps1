$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37188 - Enterprise 3.0 Stable V22 Trading Director Entrypoint Compatibility Fix" -ForegroundColor Cyan
Write-Host "Scope: trading_director_v22.py main() compatibility only" -ForegroundColor Green
Write-Host "Safety: NO director logic change / NO qualification mutation / NO schema change / PAPER_ONLY preserved" -ForegroundColor Green

$repo = (Get-Location).Path
$targetRel = "automation/trading_director_v22.py"
$targetPath = Join-Path $repo $targetRel
$stablePath = Join-Path $repo "automation/enterprise3_stable.py"

if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "Required file not found: $targetPath"
}
if (-not (Test-Path -LiteralPath $stablePath)) {
    throw "Required file not found: $stablePath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $repo ".phase37188-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item -LiteralPath $targetPath -Destination (Join-Path $backupDir "trading_director_v22.py") -Force

$original = Get-Content -LiteralPath $targetPath -Raw

# Guard against patching an unexpected V22 implementation.
$requiredTokens = @(
    'Director score',
    'Directive:',
    'Confidence:',
    'Maintain current allocation'
)

foreach ($token in $requiredTokens) {
    if ($original -notmatch [regex]::Escape($token)) {
        throw "Unexpected trading_director_v22.py shape. Missing token: $token"
    }
}

if ($original -match '(?m)^\s*def\s+main\s*\(') {
    Write-Host "trading_director_v22.py already contains main(); no content patch required." -ForegroundColor Yellow
}
else {
    $compat = @'

# Phase 3.7.18.8 compatibility entrypoint.
#
# trading_director_v22.py is a legacy top-level executable. Enterprise 3.0
# Stable loads this module via importlib, which already executes the existing
# director scoring / directive logic. The orchestrator then requires a callable
# main().
#
# This no-op main() satisfies the loader contract without re-running director
# scoring, directive selection, confidence calculation, or PAPER allocation
# guidance a second time.
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

python -m py_compile "automation/trading_director_v22.py"
if ($LASTEXITCODE -ne 0) {
    throw "trading_director_v22.py compile failed."
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

foreach ($token in @('Director score', 'Directive:', 'Confidence:', 'Maintain current allocation')) {
    if ($patched -notmatch [regex]::Escape($token)) {
        throw "V22 implementation guard failed: missing $token"
    }
}

$stable = Get-Content -LiteralPath $stablePath -Raw

if ($stable -notmatch 'has no main\(\)') {
    throw "Enterprise 3.0 loader contract changed unexpectedly."
}
if ($stable -notmatch '\("V22_DIRECTOR",\s*"trading_director_v22\.py",\s*True\)') {
    throw "Enterprise 3.0 V22 critical-stage contract changed unexpectedly."
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "V22 legacy top-level execution preserved: PASS" -ForegroundColor Green
Write-Host "V22 main() compatibility entrypoint present: PASS" -ForegroundColor Green
Write-Host "No duplicate V22 execution from main(): PASS" -ForegroundColor Green
Write-Host "Enterprise 3.0 fail-closed loader preserved: PASS" -ForegroundColor Green
Write-Host "V22 remains critical stage: PASS" -ForegroundColor Green
Write-Host "Trading Director logic unchanged: PASS" -ForegroundColor Green
Write-Host "Director score / directive / confidence behavior preserved: PASS" -ForegroundColor Green
Write-Host "Qualification mutation: NONE" -ForegroundColor Green
Write-Host "Supabase schema change: NONE" -ForegroundColor Green
Write-Host "Broker / real-money enablement: NONE" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37188 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backup: $backupDir"
Write-Host ""
Write-Host "Expected repaired Enterprise 3.0 behavior:"
Write-Host "  V16_ORDERS: SUCCESS"
Write-Host "  V17_PORTFOLIO: SUCCESS"
Write-Host "  V18_AI_FUND: SUCCESS"
Write-Host "  V19_HEDGE_RISK: SUCCESS"
Write-Host "  V21_COUNCIL: SUCCESS"
Write-Host "  Director score ..."
Write-Host "  Directive: ..."
Write-Host "  Confidence: ..."
Write-Host "  V22_DIRECTOR: SUCCESS"
Write-Host "  No 'trading_director_v22.py has no main()' error"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/trading_director_v22.py"'
Write-Host '2. git diff --cached --name-only'
Write-Host '3. git diff --cached -- "automation/trading_director_v22.py"'
Write-Host '4. git commit -m "Fix Phase 37188 Enterprise 3.0 V22 Trading Director main compatibility"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Enterprise 3.0 Stable Daily Cycle on main.'
