$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Get-Location).Path
$Target = Join-Path $Root "automation\v92\paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
$BackupDir = Join-Path $Root (".phase371933-v2-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host "======================================================================"
Write-Host "GPT Quant Phase 3.7.19.3.3 V2"
Write-Host "Environment-Backed Qualification Threshold Contract Compatibility Fix"
Write-Host "VERIFICATION-ONLY / ROLLBACK-SAFE"
Write-Host "======================================================================"

Write-Host "[1/9] Repository safety pre-check..."
if (-not (Test-Path (Join-Path $Root ".git"))) { throw "Not at repository root." }
if (-not (Test-Path $Target)) { throw "Target not found: $Target" }

Write-Host "[2/9] Python launcher..."
if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
else { throw "Python launcher not found." }
Write-Host "  Launcher: $Python"

Write-Host "[3/9] Backup Phase 3.7.5..."
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$Backup = Join-Path $BackupDir (Split-Path $Target -Leaf)
Copy-Item $Target $Backup -Force
$Before = Get-Content $Target -Raw

try {
    Write-Host "[4/9] Verify environment-backed threshold contract..."

    $Checks = @(
        @{ Name="MIN_OBSERVED_CYCLES"; Env="PHASE375_MIN_OBSERVED_CYCLES"; Default="3" },
        @{ Name="MIN_VALID_CYCLES";    Env="PHASE375_MIN_VALID_CYCLES";    Default="3" },
        @{ Name="MAX_BLOCKED_CYCLES";  Env="PHASE375_MAX_BLOCKED_CYCLES";  Default="0" }
    )

    foreach ($c in $Checks) {
        $p = '(?m)^\s*' + [regex]::Escape($c.Name) +
             '\s*=\s*int\s*\(\s*os\.getenv\s*\(\s*["'']' +
             [regex]::Escape($c.Env) + '["'']\s*,\s*["'']' +
             [regex]::Escape($c.Default) + '["'']\s*\)\s*\)\s*$'
        if ($Before -notmatch $p) {
            throw "Threshold contract missing/drifted: $($c.Name) / $($c.Env) / default=$($c.Default)"
        }
        Write-Host ("  PASS {0} <- {1} default={2}" -f $c.Name,$c.Env,$c.Default)
    }

    Write-Host "[5/9] Verify threshold usage semantics..."
    foreach ($p in @(
        'blocked_count\s*>\s*MAX_BLOCKED_CYCLES',
        'observed\s*>=\s*MIN_OBSERVED_CYCLES',
        'valid\s*>=\s*MIN_VALID_CYCLES'
    )) {
        if ($Before -notmatch $p) { throw "Threshold usage drift/missing: $p" }
    }
    Write-Host "  Threshold usage: PASS"

    Write-Host "[6/9] Compile Phase 3.7.5..."
    if ($Python -eq "py") { & py -3 -m py_compile $Target }
    else { & python -m py_compile $Target }
    if ($LASTEXITCODE -ne 0) { throw "Compile failed." }

    Write-Host "[7/9] Verify no Phase 3.7.5 source mutation..."
    $After = Get-Content $Target -Raw
    if ($After -cne $Before) { throw "Unexpected Phase 3.7.5 mutation detected." }
    Write-Host "  Source mutation: NO"

    Write-Host "[8/9] Safety verification..."
    Write-Host "  Phase 3.7.5 qualification logic : NO CHANGE"
    Write-Host "  MIN_OBSERVED_CYCLES             : 3"
    Write-Host "  MIN_VALID_CYCLES                : 3"
    Write-Host "  MAX_BLOCKED_CYCLES              : 0"
    Write-Host "  Supabase mutation               : NO"
    Write-Host "  Qualification counter mutation  : NO"
    Write-Host "  Synthetic qualification         : NO"
    Write-Host "  Historical evidence rewrite     : NO"
    Write-Host "  Broker order enablement         : NO"
    Write-Host "  Real-money enablement           : NO"

    Write-Host "[9/9] SUCCESS"
    Write-Host "======================================================================"
    Write-Host "Phase 3.7.19.3.3 V2 VERIFIED"
    Write-Host "Environment-backed contract : COMPATIBLE"
    Write-Host "Phase 3.7.5 mutation        : NO"
    Write-Host "Rollback-safe               : YES"
    Write-Host "======================================================================"
    Write-Host "IMPORTANT: Do not use git add ."
}
catch {
    Write-Host "ROLLBACK: restoring Phase 3.7.5..." -ForegroundColor Yellow
    if (Test-Path $Backup) { Copy-Item $Backup $Target -Force }
    throw
}
