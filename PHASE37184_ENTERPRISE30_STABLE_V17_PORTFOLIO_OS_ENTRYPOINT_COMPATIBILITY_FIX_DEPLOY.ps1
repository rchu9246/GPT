$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37184 - Enterprise 3.0 Stable V17 Portfolio OS Entrypoint Compatibility Fix" -ForegroundColor Cyan
Write-Host "Scope: portfolio_os_v17.py main() compatibility only" -ForegroundColor Green
Write-Host "Safety: NO strategy change / NO qualification mutation / NO schema change / PAPER_ONLY preserved" -ForegroundColor Green

$repo = (Get-Location).Path
$targetRel = "automation/portfolio_os_v17.py"
$targetPath = Join-Path $repo $targetRel

if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "Required file not found: $targetPath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $repo ".phase37184-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item -LiteralPath $targetPath -Destination (Join-Path $backupDir "portfolio_os_v17.py") -Force

$original = Get-Content -LiteralPath $targetPath -Raw

# Guard against patching an unexpected implementation.
$requiredTokens = @(
    'V17 Portfolio OS complete:',
    'portfolio_decisions_v17',
    'paper_equity_snapshots_v13',
    'Portfolio OS supports PAPER mode only'
)

foreach ($token in $requiredTokens) {
    if ($original -notmatch [regex]::Escape($token)) {
        throw "Unexpected portfolio_os_v17.py shape. Missing token: $token"
    }
}

if ($original -match '(?m)^\s*def\s+main\s*\(') {
    Write-Host "portfolio_os_v17.py already contains main(); no content patch required." -ForegroundColor Yellow
}
else {
    $compat = @'

# Phase 3.7.18.4 compatibility entrypoint.
#
# portfolio_os_v17.py is a legacy top-level executable. Enterprise 3.0 Stable
# loads the module via importlib, which executes its existing V17 portfolio body,
# and then requires a callable main(). Without main(), the stage is marked failed
# after the portfolio work already completed.
#
# This compatibility main() is intentionally a no-op. It satisfies the
# orchestrator contract without re-running portfolio decisions, position updates,
# equity snapshots, or proposed PAPER orders a second time.
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

python -m py_compile "automation/portfolio_os_v17.py"
if ($LASTEXITCODE -ne 0) {
    throw "portfolio_os_v17.py compile failed."
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

# Confirm the V17 paper-only safety guard still exists.
if ($patched -notmatch 'Portfolio OS supports PAPER mode only') {
    throw "PAPER_ONLY safety guard missing after patch."
}

# Confirm major V17 write targets remain present and unchanged in intent.
foreach ($token in @('portfolio_decisions_v17', 'paper_equity_snapshots_v13', 'trade_orders_v13')) {
    if ($patched -notmatch [regex]::Escape($token)) {
        throw "V17 implementation guard failed: missing $token"
    }
}

$stablePath = Join-Path $repo "automation/enterprise3_stable.py"
if (-not (Test-Path -LiteralPath $stablePath)) {
    throw "Required file not found: $stablePath"
}

$stable = Get-Content -LiteralPath $stablePath -Raw

if ($stable -notmatch 'has no main\(\)') {
    throw "Enterprise 3.0 loader contract changed unexpectedly."
}

if ($stable -notmatch '\("V17_PORTFOLIO",\s*"portfolio_os_v17\.py",\s*True\)') {
    throw "Enterprise 3.0 V17 critical-stage contract changed unexpectedly."
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "V17 legacy top-level execution preserved: PASS" -ForegroundColor Green
Write-Host "V17 main() compatibility entrypoint present: PASS" -ForegroundColor Green
Write-Host "No duplicate V17 execution from main(): PASS" -ForegroundColor Green
Write-Host "Enterprise 3.0 fail-closed loader preserved: PASS" -ForegroundColor Green
Write-Host "V17 remains critical stage: PASS" -ForegroundColor Green
Write-Host "Portfolio decision logic unchanged: PASS" -ForegroundColor Green
Write-Host "PAPER_ONLY guard preserved: PASS" -ForegroundColor Green
Write-Host "Qualification mutation: NONE" -ForegroundColor Green
Write-Host "Supabase schema change: NONE" -ForegroundColor Green
Write-Host "Broker / real-money enablement: NONE" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37184 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backup: $backupDir"
Write-Host ""
Write-Host "Expected repaired Enterprise 3.0 behavior:"
Write-Host "  V16_ORDERS: SUCCESS"
Write-Host "  V17 Portfolio OS complete: positions=... decisions=... equity=..."
Write-Host "  V17_PORTFOLIO: SUCCESS"
Write-Host "  No 'portfolio_os_v17.py has no main()' error"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/portfolio_os_v17.py"'
Write-Host '2. git diff --cached --name-only'
Write-Host '3. git diff --cached -- "automation/portfolio_os_v17.py"'
Write-Host '4. git commit -m "Fix Phase 37184 Enterprise 3.0 V17 Portfolio OS main compatibility"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Enterprise 3.0 Stable Daily Cycle on main.'
