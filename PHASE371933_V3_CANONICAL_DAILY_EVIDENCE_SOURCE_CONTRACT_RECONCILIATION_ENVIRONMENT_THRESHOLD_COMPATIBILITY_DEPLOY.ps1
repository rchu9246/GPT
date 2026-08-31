#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "======================================================================"
Write-Host " GPT Quant Phase 3.7.19.3.3 V3"
Write-Host " Canonical Daily Evidence Source Contract Reconciliation"
Write-Host " + Environment-Backed Threshold Compatibility"
Write-Host "======================================================================"

$Root = (Get-Location).Path
$P374Rel = "automation\v92\paper_trading_phase374_production_paper_daily_cycle_monitoring_evidence_accumulation.py"
$P375Rel = "automation\v92\paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
$P374 = Join-Path $Root $P374Rel
$P375 = Join-Path $Root $P375Rel
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $Root ".phase371933-v3-backup-$Stamp"
$Backup = Join-Path $BackupDir ([IO.Path]::GetFileName($P375))
$TempPy = Join-Path $env:TEMP "phase371933_v3_reconcile.py"

if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonMode = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonMode = "python"
} else {
    throw "Python launcher not found."
}

function Restore-Phase375 {
    if (Test-Path $Backup) {
        Copy-Item $Backup $P375 -Force
    }
}

try {
    Write-Host "[1/11] Repository pre-check..."
    if (-not (Test-Path (Join-Path $Root ".git"))) { throw "Not at GPT repository root." }
    if (-not (Test-Path $P374)) { throw "Phase 3.7.4 source not found." }
    if (-not (Test-Path $P375)) { throw "Phase 3.7.5 source not found." }

    Write-Host "[2/11] Python launcher..."
    Write-Host "  Launcher: $PythonMode"

    Write-Host "[3/11] Backup Phase 3.7.5..."
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    Copy-Item $P375 $Backup -Force

    Write-Host "[4/11] Capture baseline safety + threshold contract..."
    $Before = Get-Content -LiteralPath $P375 -Raw

    foreach ($forbidden in @(
        'BROKER_ORDER_SUBMISSION_ENABLED = True',
        'REAL_MONEY_TRADING_ENABLED = True',
        'HISTORICAL_REWRITE_ALLOWED = True',
        'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = True',
        'QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = True'
    )) {
        if ($Before.Contains($forbidden)) {
            throw "Unsafe pre-existing invariant detected: $forbidden"
        }
    }

    $ThresholdChecks = @(
        @{ Name="MIN_OBSERVED_CYCLES"; Env="PHASE375_MIN_OBSERVED_CYCLES"; Default="3" },
        @{ Name="MIN_VALID_CYCLES"; Env="PHASE375_MIN_VALID_CYCLES"; Default="3" },
        @{ Name="MAX_BLOCKED_CYCLES"; Env="PHASE375_MAX_BLOCKED_CYCLES"; Default="0" }
    )

    foreach ($c in $ThresholdChecks) {
        $pattern = '(?m)^\s*' + [regex]::Escape($c.Name) +
                   '\s*=\s*int\s*\(\s*os\.getenv\s*\(\s*["'']' +
                   [regex]::Escape($c.Env) + '["'']\s*,\s*["'']' +
                   [regex]::Escape($c.Default) + '["'']\s*\)\s*\)\s*$'
        if ($Before -notmatch $pattern) {
            throw "Environment-backed threshold contract missing/drifted: $($c.Name)"
        }
        Write-Host ("  PASS 0 <- 1 default=2" -f $c.Name,$c.Env,$c.Default)
    }

    Write-Host "[5/11] Write parser-safe reconciliation controller..."
    [IO.File]::WriteAllBytes($TempPy, [Convert]::FromBase64String("ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwppbXBvcnQgYXN0CmltcG9ydCBqc29uCmltcG9ydCByZQpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKZnJvbSBkYXRldGltZSBpbXBvcnQgZGF0ZXRpbWUsIHRpbWV6b25lCgpST09UID0gUGF0aC5jd2QoKQpQMzc0ID0gUk9PVCAvICJhdXRvbWF0aW9uIiAvICJ2OTIiIC8gInBhcGVyX3RyYWRpbmdfcGhhc2UzNzRfcHJvZHVjdGlvbl9wYXBlcl9kYWlseV9jeWNsZV9tb25pdG9yaW5nX2V2aWRlbmNlX2FjY3VtdWxhdGlvbi5weSIKUDM3NSA9IFJPT1QgLyAiYXV0b21hdGlvbiIgLyAidjkyIiAvICJwYXBlcl90cmFkaW5nX3BoYXNlMzc1X3Byb2R1Y3Rpb25fcGFwZXJfbXVsdGlfY3ljbGVfc3RhYmlsaXR5X2V2aWRlbmNlX3F1YWxpZmljYXRpb24ucHkiCk9VVCA9IFJPT1QgLyAiYXJ0aWZhY3RzIiAvICJwaGFzZTM3MTkzM192MyIKT1VULm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKCmlmIG5vdCBQMzc0LmV4aXN0cygpOgogICAgcmFpc2UgU3lzdGVtRXhpdChmIk1pc3NpbmcgUGhhc2UgMy43LjQgc291cmNlOiB7UDM3NH0iKQppZiBub3QgUDM3NS5leGlzdHMoKToKICAgIHJhaXNlIFN5c3RlbUV4aXQoZiJNaXNzaW5nIFBoYXNlIDMuNy41IHNvdXJjZToge1AzNzV9IikKCnMzNzQgPSBQMzc0LnJlYWRfdGV4dChlbmNvZGluZz0idXRmLTgiKQpzMzc1ID0gUDM3NS5yZWFkX3RleHQoZW5jb2Rpbmc9InV0Zi04IikKCiMgRGlzY292ZXIgbGlrZWx5IHBlcnNpc3RlZCBldmlkZW5jZSB0YWJsZXMgZnJvbSBQaGFzZSAzLjcuNC4KdHJlZSA9IGFzdC5wYXJzZShzMzc0KQpzdHJpbmdzID0gW10KZm9yIG5vZGUgaW4gYXN0LndhbGsodHJlZSk6CiAgICBpZiBpc2luc3RhbmNlKG5vZGUsIGFzdC5Db25zdGFudCkgYW5kIGlzaW5zdGFuY2Uobm9kZS52YWx1ZSwgc3RyKToKICAgICAgICBzdHJpbmdzLmFwcGVuZChub2RlLnZhbHVlKQoKZGVmIGxpa2VseV90YWJsZSh4OiBzdHIpIC0+IGJvb2w6CiAgICB5ID0geC5zdHJpcCgpLmxvd2VyKCkKICAgIGlmIG5vdCByZS5mdWxsbWF0Y2gociJbYS16MC05X117OCwxMjB9IiwgeSk6CiAgICAgICAgcmV0dXJuIEZhbHNlCiAgICBpZiBub3QgeS5lbmRzd2l0aCgiX3Y5MiIpOgogICAgICAgIHJldHVybiBGYWxzZQogICAgcmV0dXJuIGFueSh0ZXJtIGluIHkgZm9yIHRlcm0gaW4gKAogICAgICAgICJkYWlseV9jeWNsZSIsCiAgICAgICAgImV2aWRlbmNlIiwKICAgICAgICAibW9uaXRvcmluZyIsCiAgICAgICAgInF1YWxpZmljYXRpb24iLAogICAgICAgICJydW50aW1lX3N1cGVydmlzaW9uIiwKICAgICAgICAicG9zdF9yZWNvdmVyeSIsCiAgICApKQoKY2FuZGlkYXRlcyA9IFtdCmZvciB4IGluIHN0cmluZ3M6CiAgICBpZiBsaWtlbHlfdGFibGUoeCkgYW5kIHggbm90IGluIGNhbmRpZGF0ZXM6CiAgICAgICAgY2FuZGlkYXRlcy5hcHBlbmQoeCkKCnN0cm9uZyA9IFtdCmZvciBjIGluIGNhbmRpZGF0ZXM6CiAgICBmb3IgbSBpbiByZS5maW5kaXRlcihyZS5lc2NhcGUoYyksIHMzNzQpOgogICAgICAgIGN0eCA9IHMzNzRbbWF4KDAsIG0uc3RhcnQoKS0zNTApOm1pbihsZW4oczM3NCksIG0uZW5kKCkrMzUwKV0ubG93ZXIoKQogICAgICAgIGlmIGFueShrIGluIGN0eCBmb3IgayBpbiAoImluc2VydCIsICJ1cHNlcnQiLCAicGVyc2lzdCIsICJ3cml0ZSIsICJwb3N0Z3Jlc3QiLCAic3VwYWJhc2UiLCAidGFibGUoIikpOgogICAgICAgICAgICBpZiBjIG5vdCBpbiBzdHJvbmc6CiAgICAgICAgICAgICAgICBzdHJvbmcuYXBwZW5kKGMpCiAgICAgICAgICAgIGJyZWFrCgpkaXNjb3ZlcmVkID0gc3Ryb25nIG9yIGNhbmRpZGF0ZXMKaWYgbm90IGRpc2NvdmVyZWQ6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCJQSEFTRTM3MTkzM19WM19BQk9SVDogbm8gcGxhdXNpYmxlIFBoYXNlIDMuNy40IHBlcnNpc3RlZCBldmlkZW5jZSB0YWJsZSBkaXNjb3ZlcmVkLiIpCgojIEtlZXAgb25seSBldmlkZW5jZS1vcmllbnRlZCBjYW5kaWRhdGVzIGFoZWFkIG9mIGxlZ2FjeSBmYWxsYmFja3MuCnByaW9yaXR5ID0gW10KZm9yIGMgaW4gZGlzY292ZXJlZDoKICAgIGxjID0gYy5sb3dlcigpCiAgICBpZiAiZXZpZGVuY2UiIGluIGxjIG9yICJkYWlseV9jeWNsZSIgaW4gbGMgb3IgIm1vbml0b3JpbmciIGluIGxjOgogICAgICAgIHByaW9yaXR5LmFwcGVuZChjKQoKaWYgbm90IHByaW9yaXR5OgogICAgcHJpb3JpdHkgPSBkaXNjb3ZlcmVkCgpwYXQgPSByZS5jb21waWxlKHIiKD9tcyleKERBSUxZX0VWSURFTkNFX1RBQkxFU1xzKj1ccyopKFxbW15cXV0qXF18XChbXlwpXSpcKSkiKQptID0gcGF0LnNlYXJjaChzMzc1KQppZiBub3QgbToKICAgIHJhaXNlIFN5c3RlbUV4aXQoIlBIQVNFMzcxOTMzX1YzX0FCT1JUOiBEQUlMWV9FVklERU5DRV9UQUJMRVMgYXNzaWdubWVudCBub3QgZm91bmQuIikKCnRyeToKICAgIGN1cnJlbnQgPSBsaXN0KGFzdC5saXRlcmFsX2V2YWwobS5ncm91cCgyKSkpCmV4Y2VwdCBFeGNlcHRpb24gYXMgZXhjOgogICAgcmFpc2UgU3lzdGVtRXhpdChmIlBIQVNFMzcxOTMzX1YzX0FCT1JUOiBjYW5ub3QgcGFyc2UgREFJTFlfRVZJREVOQ0VfVEFCTEVTOiB7ZXhjfSIpCgptZXJnZWQgPSBbXQpmb3IgeCBpbiBwcmlvcml0eSArIGN1cnJlbnQ6CiAgICBpZiB4IG5vdCBpbiBtZXJnZWQ6CiAgICAgICAgbWVyZ2VkLmFwcGVuZCh4KQoKaWYgbWVyZ2VkID09IGN1cnJlbnQ6CiAgICBzdGF0ZSA9ICJOT19DSEFOR0VfQUxSRUFEWV9SRUNPTkNJTEVEIgogICAgbmV3X3MzNzUgPSBzMzc1CmVsc2U6CiAgICByZXBsYWNlbWVudCA9ICJEQUlMWV9FVklERU5DRV9UQUJMRVMgPSAiICsgcmVwcihtZXJnZWQpCiAgICBuZXdfczM3NSA9IHMzNzVbOm0uc3RhcnQoKV0gKyByZXBsYWNlbWVudCArIHMzNzVbbS5lbmQoKTpdCiAgICBQMzc1LndyaXRlX3RleHQobmV3X3MzNzUsIGVuY29kaW5nPSJ1dGYtOCIpCiAgICBzdGF0ZSA9ICJQQVRDSF9BUFBMSUVEIgoKIyBTeW50YXggdmVyaWZpY2F0aW9uLgphc3QucGFyc2UobmV3X3MzNzUpCgpyZXBvcnQgPSB7CiAgICAiY29udHJhY3QiOiAiUEhBU0UzNzE5MzNfVjNfQ0FOT05JQ0FMX0RBSUxZX0VWSURFTkNFX1NPVVJDRV9DT05UUkFDVF9SRUNPTkNJTElBVElPTiIsCiAgICAiZ2VuZXJhdGVkX2F0IjogZGF0ZXRpbWUubm93KHRpbWV6b25lLnV0YykuaXNvZm9ybWF0KCksCiAgICAic3RhdGUiOiBzdGF0ZSwKICAgICJkaXNjb3ZlcmVkX2NhbmRpZGF0ZXMiOiBkaXNjb3ZlcmVkLAogICAgInByaW9yaXR5X2NhbmRpZGF0ZXMiOiBwcmlvcml0eSwKICAgICJwcmV2aW91c19kYWlseV9ldmlkZW5jZV90YWJsZXMiOiBjdXJyZW50LAogICAgInJlY29uY2lsZWRfZGFpbHlfZXZpZGVuY2VfdGFibGVzIjogbWVyZ2VkLAogICAgInNhZmV0eSI6IHsKICAgICAgICAicGhhc2UzNzRfbG9naWNfY2hhbmdlIjogRmFsc2UsCiAgICAgICAgInBoYXNlMzc1X3F1YWxpZmljYXRpb25fbG9naWNfY2hhbmdlIjogRmFsc2UsCiAgICAgICAgInF1YWxpZmljYXRpb25fdGhyZXNob2xkX2NoYW5nZSI6IEZhbHNlLAogICAgICAgICJzdXBhYmFzZV9tdXRhdGlvbl9ieV9kZXBsb3llciI6IEZhbHNlLAogICAgICAgICJxdWFsaWZpY2F0aW9uX2NvdW50ZXJfbXV0YXRpb24iOiBGYWxzZSwKICAgICAgICAic3ludGhldGljX3F1YWxpZmljYXRpb24iOiBGYWxzZSwKICAgICAgICAiaGlzdG9yaWNhbF9ldmlkZW5jZV9yZXdyaXRlIjogRmFsc2UsCiAgICAgICAgImJyb2tlcl9vcmRlcl9lbmFibGVtZW50IjogRmFsc2UsCiAgICAgICAgInJlYWxfbW9uZXlfZW5hYmxlbWVudCI6IEZhbHNlLAogICAgfSwKfQooT1VUIC8gInBoYXNlMzcxOTMzX3YzX3JlY29uY2lsaWF0aW9uLmpzb24iKS53cml0ZV90ZXh0KAogICAganNvbi5kdW1wcyhyZXBvcnQsIGluZGVudD0yLCBlbnN1cmVfYXNjaWk9RmFsc2UpLAogICAgZW5jb2Rpbmc9InV0Zi04IiwKKQoKcHJpbnQoIlBIQVNFMzcxOTMzX1YzX1NUQVRFPSIgKyBzdGF0ZSkKcHJpbnQoIkRJU0NPVkVSRUQ9IiArIHJlcHIoZGlzY292ZXJlZCkpCnByaW50KCJQUklPUklUWT0iICsgcmVwcihwcmlvcml0eSkpCnByaW50KCJQUkVWSU9VUz0iICsgcmVwcihjdXJyZW50KSkKcHJpbnQoIlJFQ09OQ0lMRUQ9IiArIHJlcHIobWVyZ2VkKSkK"))

    Write-Host "[6/11] Discover + reconcile canonical daily evidence source..."
    if ($PythonMode -eq "py") { & py -3 $TempPy } else { & python $TempPy }
    if ($LASTEXITCODE -ne 0) { throw "Reconciliation controller failed." }

    Write-Host "[7/11] Compile Phase 3.7.5..."
    if ($PythonMode -eq "py") { & py -3 -m py_compile $P375 } else { & python -m py_compile $P375 }
    if ($LASTEXITCODE -ne 0) { throw "Phase 3.7.5 compile failed." }

    Write-Host "[8/11] Verify threshold contract after reconciliation..."
    $After = Get-Content -LiteralPath $P375 -Raw
    foreach ($c in $ThresholdChecks) {
        $pattern = '(?m)^\s*' + [regex]::Escape($c.Name) +
                   '\s*=\s*int\s*\(\s*os\.getenv\s*\(\s*["'']' +
                   [regex]::Escape($c.Env) + '["'']\s*,\s*["'']' +
                   [regex]::Escape($c.Default) + '["'']\s*\)\s*\)\s*$'
        if ($After -notmatch $pattern) {
            throw "Threshold contract drift introduced: $($c.Name)"
        }
    }

    foreach ($usage in @(
        'blocked_count\s*>\s*MAX_BLOCKED_CYCLES',
        'observed\s*>=\s*MIN_OBSERVED_CYCLES',
        'valid\s*>=\s*MIN_VALID_CYCLES'
    )) {
        if ($After -notmatch $usage) {
            throw "Threshold usage drift/missing: $usage"
        }
    }

    Write-Host "[9/11] Verify safety invariants after reconciliation..."
    foreach ($forbidden in @(
        'BROKER_ORDER_SUBMISSION_ENABLED = True',
        'REAL_MONEY_TRADING_ENABLED = True',
        'HISTORICAL_REWRITE_ALLOWED = True',
        'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = True',
        'QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = True'
    )) {
        if ($After.Contains($forbidden)) {
            throw "Unsafe invariant introduced: $forbidden"
        }
    }

    Write-Host "[10/11] Git diff verification..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $P375Rel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        & git diff -- $P375Rel
    }

    Write-Host "[11/11] SUCCESS"
    Write-Host "======================================================================"
    Write-Host " Phase 3.7.19.3.3 V3 APPLIED AND VERIFIED"
    Write-Host "======================================================================"
    Write-Host "Reconciliation target          : DAILY_EVIDENCE_TABLES"
    Write-Host "Environment threshold contract : COMPATIBLE"
    Write-Host "MIN_OBSERVED_CYCLES            : 3 default preserved"
    Write-Host "MIN_VALID_CYCLES               : 3 default preserved"
    Write-Host "MAX_BLOCKED_CYCLES             : 0 default preserved"
    Write-Host "Phase 3.7.4 logic change       : NO"
    Write-Host "Phase 3.7.5 qualification logic: UNCHANGED"
    Write-Host "Supabase mutation by deployer  : NO"
    Write-Host "Qualification counter mutation : NO"
    Write-Host "Synthetic qualification        : NO"
    Write-Host "Historical evidence rewrite    : NO"
    Write-Host "Broker order enablement        : NO"
    Write-Host "Real-money enablement          : NO"
    Write-Host ""
    Write-Host "IMPORTANT: Do not use git add ."
    Write-Host "NEXT: review DISCOVERED / PRIORITY / RECONCILED and git diff before commit."
}
catch {
    Write-Host "ROLLBACK: restoring Phase 3.7.5..." -ForegroundColor Yellow
    Restore-Phase375
    throw
}
finally {
    if (Test-Path $TempPy) {
        Remove-Item $TempPy -Force -ErrorAction SilentlyContinue
    }
}
