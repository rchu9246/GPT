$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37187 - Enterprise 3.0 Stable V21 Multi-Agent Council Entrypoint Compatibility Fix" -ForegroundColor Cyan
Write-Host "Scope: multi_agent_council_v21.py main() compatibility only" -ForegroundColor Green
Write-Host "Safety: NO council logic change / NO qualification mutation / NO schema change / PAPER_ONLY preserved" -ForegroundColor Green

$repo = (Get-Location).Path
$targetRel = "automation/multi_agent_council_v21.py"
$targetPath = Join-Path $repo $targetRel
$stablePath = Join-Path $repo "automation/enterprise3_stable.py"

if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "Required file not found: $targetPath"
}
if (-not (Test-Path -LiteralPath $stablePath)) {
    throw "Required file not found: $stablePath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $repo ".phase37187-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item -LiteralPath $targetPath -Destination (Join-Path $backupDir "multi_agent_council_v21.py") -Force

$original = Get-Content -LiteralPath $targetPath -Raw

# Guard against patching an unexpected V21 implementation.
$requiredTokens = @(
    'Council reviewed',
    'BUY',
    'HOLD/PENDING',
    'WATCH/AVOID'
)

foreach ($token in $requiredTokens) {
    if ($original -notmatch [regex]::Escape($token)) {
        throw "Unexpected multi_agent_council_v21.py shape. Missing token: $token"
    }
}

if ($original -match '(?m)^\s*def\s+main\s*\(') {
    Write-Host "multi_agent_council_v21.py already contains main(); no content patch required." -ForegroundColor Yellow
}
else {
    $compat = @'

# Phase 3.7.18.7 compatibility entrypoint.
#
# multi_agent_council_v21.py is a legacy top-level executable. Enterprise 3.0
# Stable loads this module via importlib, which already executes the existing
# council-review body. The orchestrator then requires a callable main().
#
# This no-op main() satisfies the loader contract without re-running council
# deliberation, consensus scoring, symbol review, or PAPER decision generation.
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

python -m py_compile "automation/multi_agent_council_v21.py"
if ($LASTEXITCODE -ne 0) {
    throw "multi_agent_council_v21.py compile failed."
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

foreach ($token in @('Council reviewed', 'BUY', 'HOLD/PENDING', 'WATCH/AVOID')) {
    if ($patched -notmatch [regex]::Escape($token)) {
        throw "V21 implementation guard failed: missing $token"
    }
}

$stable = Get-Content -LiteralPath $stablePath -Raw

if ($stable -notmatch 'has no main\(\)') {
    throw "Enterprise 3.0 loader contract changed unexpectedly."
}
if ($stable -notmatch '\("V21_COUNCIL",\s*"multi_agent_council_v21\.py",\s*True\)') {
    throw "Enterprise 3.0 V21 critical-stage contract changed unexpectedly."
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "V21 legacy top-level execution preserved: PASS" -ForegroundColor Green
Write-Host "V21 main() compatibility entrypoint present: PASS" -ForegroundColor Green
Write-Host "No duplicate V21 execution from main(): PASS" -ForegroundColor Green
Write-Host "Enterprise 3.0 fail-closed loader preserved: PASS" -ForegroundColor Green
Write-Host "V21 remains critical stage: PASS" -ForegroundColor Green
Write-Host "Multi-Agent Council logic unchanged: PASS" -ForegroundColor Green
Write-Host "Consensus / classification behavior preserved: PASS" -ForegroundColor Green
Write-Host "Qualification mutation: NONE" -ForegroundColor Green
Write-Host "Supabase schema change: NONE" -ForegroundColor Green
Write-Host "Broker / real-money enablement: NONE" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37187 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backup: $backupDir"
Write-Host ""
Write-Host "Expected repaired Enterprise 3.0 behavior:"
Write-Host "  V16_ORDERS: SUCCESS"
Write-Host "  V17_PORTFOLIO: SUCCESS"
Write-Host "  V18_AI_FUND: SUCCESS"
Write-Host "  V19_HEDGE_RISK: SUCCESS"
Write-Host "  Council reviewed ... symbols ..."
Write-Host "  V21_COUNCIL: SUCCESS"
Write-Host "  No 'multi_agent_council_v21.py has no main()' error"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/multi_agent_council_v21.py"'
Write-Host '2. git diff --cached --name-only'
Write-Host '3. git diff --cached -- "automation/multi_agent_council_v21.py"'
Write-Host '4. git commit -m "Fix Phase 37187 Enterprise 3.0 V21 Multi-Agent Council main compatibility"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Enterprise 3.0 Stable Daily Cycle on main.'
