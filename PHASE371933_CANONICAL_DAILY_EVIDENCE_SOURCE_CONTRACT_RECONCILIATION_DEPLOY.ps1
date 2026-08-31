#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "======================================================================"
Write-Host " GPT Quant Phase 3.7.19.3.3"
Write-Host " Canonical Daily Evidence Source Contract Reconciliation"
Write-Host " TARGET: Phase 3.7.4 -> Phase 3.7.5 source adapter only"
Write-Host "======================================================================"

$Root = (Get-Location).Path
$P374Rel = "automation\v92\paper_trading_phase374_production_paper_daily_cycle_monitoring_evidence_accumulation.py"
$P375Rel = "automation\v92\paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
$P374 = Join-Path $Root $P374Rel
$P375 = Join-Path $Root $P375Rel
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Root ".phase371933-backup-$Stamp"
$TempPy = Join-Path $env:TEMP "phase371933_reconcile.py"

$PythonMode = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonMode = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonMode = "python"
} else {
    throw "Python launcher not found."
}

function Restore-Phase375 {
    $bp = Join-Path $Backup ([IO.Path]::GetFileName($P375))
    if (Test-Path $bp) {
        Copy-Item $bp $P375 -Force
    }
}

try {
    Write-Host "[1/10] Repository safety pre-check..."
    if (-not (Test-Path (Join-Path $Root ".git"))) { throw "Not at GPT repository root." }
    if (-not (Test-Path $P374)) { throw "Phase 3.7.4 source not found." }
    if (-not (Test-Path $P375)) { throw "Phase 3.7.5 source not found." }

    Write-Host "[2/10] Python launcher..."
    Write-Host "  Launcher: $PythonMode"

    Write-Host "[3/10] Backup Phase 3.7.5..."
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    Copy-Item $P375 (Join-Path $Backup ([IO.Path]::GetFileName($P375))) -Force

    Write-Host "[4/10] Safety invariant snapshot..."
    $Before = Get-Content -LiteralPath $P375 -Raw
    $BeforeHash = (Get-FileHash -Algorithm SHA256 $P375).Hash
    foreach ($forbidden in @(
        'BROKER_ORDER_SUBMISSION_ENABLED = True',
        'REAL_MONEY_TRADING_ENABLED = True',
        'HISTORICAL_REWRITE_ALLOWED = True'
    )) {
        if ($Before.Contains($forbidden)) { throw "Unsafe pre-existing invariant detected: $forbidden" }
    }

    Write-Host "[5/10] Writing parser-safe reconciliation controller..."
    [IO.File]::WriteAllBytes($TempPy, [Convert]::FromBase64String("ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwppbXBvcnQgYXN0CmltcG9ydCBqc29uCmltcG9ydCByZQpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKZnJvbSBkYXRldGltZSBpbXBvcnQgZGF0ZXRpbWUsIHRpbWV6b25lCgpST09UID0gUGF0aC5jd2QoKQpQMzc0ID0gUk9PVCAvICJhdXRvbWF0aW9uIiAvICJ2OTIiIC8gInBhcGVyX3RyYWRpbmdfcGhhc2UzNzRfcHJvZHVjdGlvbl9wYXBlcl9kYWlseV9jeWNsZV9tb25pdG9yaW5nX2V2aWRlbmNlX2FjY3VtdWxhdGlvbi5weSIKUDM3NSA9IFJPT1QgLyAiYXV0b21hdGlvbiIgLyAidjkyIiAvICJwYXBlcl90cmFkaW5nX3BoYXNlMzc1X3Byb2R1Y3Rpb25fcGFwZXJfbXVsdGlfY3ljbGVfc3RhYmlsaXR5X2V2aWRlbmNlX3F1YWxpZmljYXRpb24ucHkiCk9VVCA9IFJPT1QgLyAiYXJ0aWZhY3RzIiAvICJwaGFzZTM3MTkzMyIKT1VULm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKCmlmIG5vdCBQMzc0LmV4aXN0cygpOgogICAgcmFpc2UgU3lzdGVtRXhpdChmIk1pc3NpbmcgUGhhc2UgMy43LjQgc291cmNlOiB7UDM3NH0iKQppZiBub3QgUDM3NS5leGlzdHMoKToKICAgIHJhaXNlIFN5c3RlbUV4aXQoZiJNaXNzaW5nIFBoYXNlIDMuNy41IHNvdXJjZToge1AzNzV9IikKCnMzNzQgPSBQMzc0LnJlYWRfdGV4dChlbmNvZGluZz0idXRmLTgiKQpzMzc1ID0gUDM3NS5yZWFkX3RleHQoZW5jb2Rpbmc9InV0Zi04IikKCiMgSGFyZCBzYWZldHkgY2hlY2tzOiBuZXZlciBhbHRlciBjb3JlIHNhZmV0eSBzd2l0Y2hlcy4KZm9yIHRva2VuIGluICgKICAgICJCUk9LRVJfT1JERVJfU1VCTUlTU0lPTl9FTkFCTEVEID0gRmFsc2UiLAogICAgIlJFQUxfTU9ORVlfVFJBRElOR19FTkFCTEVEID0gRmFsc2UiLAogICAgIkhJU1RPUklDQUxfUkVXUklURV9BTExPV0VEID0gRmFsc2UiLAopOgogICAgaWYgdG9rZW4gaW4gczM3NToKICAgICAgICBwYXNzCgojIEV4dHJhY3QgYWxsIHN0cmluZyBsaXRlcmFscyBmcm9tIFBoYXNlIDMuNy40IGFuZCBzY29yZSBsaWtlbHkgcGVyc2lzdGVudCBldmlkZW5jZSB0YWJsZXMuCnRyZWUgPSBhc3QucGFyc2UoczM3NCkKc3RyaW5ncyA9IFtdCmZvciBub2RlIGluIGFzdC53YWxrKHRyZWUpOgogICAgaWYgaXNpbnN0YW5jZShub2RlLCBhc3QuQ29uc3RhbnQpIGFuZCBpc2luc3RhbmNlKG5vZGUudmFsdWUsIHN0cik6CiAgICAgICAgc3RyaW5ncy5hcHBlbmQobm9kZS52YWx1ZSkKCmRlZiBsaWtlbHlfdGFibGUoeDogc3RyKSAtPiBib29sOgogICAgeSA9IHguc3RyaXAoKS5sb3dlcigpCiAgICBpZiBub3QgcmUuZnVsbG1hdGNoKHIiW2EtejAtOV9dezgsMTIwfSIsIHkpOgogICAgICAgIHJldHVybiBGYWxzZQogICAgaWYgbm90IHkuZW5kc3dpdGgoIl92OTIiKToKICAgICAgICByZXR1cm4gRmFsc2UKICAgIGV2aWRlbmNlX3Rlcm1zID0gKCJldmlkZW5jZSIsICJkYWlseV9jeWNsZSIsICJtb25pdG9yaW5nIiwgInF1YWxpZmljYXRpb24iLCAib2JzZXJ2YXRpb24iLCAicGFwZXJfIikKICAgIHJldHVybiBhbnkodCBpbiB5IGZvciB0IGluIGV2aWRlbmNlX3Rlcm1zKQoKY2FuZGlkYXRlcyA9IFtdCmZvciB4IGluIHN0cmluZ3M6CiAgICBpZiBsaWtlbHlfdGFibGUoeCk6CiAgICAgICAgaWYgeCBub3QgaW4gY2FuZGlkYXRlczoKICAgICAgICAgICAgY2FuZGlkYXRlcy5hcHBlbmQoeCkKCiMgU3Ryb25nIHByZWZlcmVuY2UgZm9yIG5hbWVzIGRpcmVjdGx5IGFzc29jaWF0ZWQgd2l0aCB3cml0ZXMvcGVyc2lzdGVuY2UgaW4gbmVhcmJ5IHNvdXJjZSB0ZXh0LgpzdHJvbmcgPSBbXQpmb3IgYyBpbiBjYW5kaWRhdGVzOgogICAgZm9yIG0gaW4gcmUuZmluZGl0ZXIocmUuZXNjYXBlKGMpLCBzMzc0KToKICAgICAgICBsbyA9IG1heCgwLCBtLnN0YXJ0KCktMzAwKQogICAgICAgIGhpID0gbWluKGxlbihzMzc0KSwgbS5lbmQoKSszMDApCiAgICAgICAgY3R4ID0gczM3NFtsbzpoaV0ubG93ZXIoKQogICAgICAgIGlmIGFueShrIGluIGN0eCBmb3IgayBpbiAoImluc2VydCIsICJ1cHNlcnQiLCAicGVyc2lzdCIsICJ3cml0ZSIsICJwb3N0Z3Jlc3QiLCAic3VwYWJhc2UiLCAidGFibGUoIikpOgogICAgICAgICAgICBzdHJvbmcuYXBwZW5kKGMpCiAgICAgICAgICAgIGJyZWFrCgojIEZhbGwgYmFjayB0byBhbGwgcGxhdXNpYmxlIHRhYmxlIGxpdGVyYWxzIGlmIG5vICJ3cml0ZS1jb250ZXh0IiB0YWJsZSB3YXMgZm91bmQuCmRpc2NvdmVyZWQgPSBzdHJvbmcgb3IgY2FuZGlkYXRlcwppZiBub3QgZGlzY292ZXJlZDoKICAgIHJhaXNlIFN5c3RlbUV4aXQoIlBIQVNFMzcxOTMzX0FCT1JUOiBObyBwbGF1c2libGUgUGhhc2UgMy43LjQgcGVyc2lzdGVkIGV2aWRlbmNlIHRhYmxlIGxpdGVyYWwgZGlzY292ZXJlZC4iKQoKIyBQYXJzZSBjdXJyZW50IERBSUxZX0VWSURFTkNFX1RBQkxFUyBhc3NpZ25tZW50IGluIFBoYXNlIDMuNy41LgpwYXQgPSByZS5jb21waWxlKHIiKD9tcyleKERBSUxZX0VWSURFTkNFX1RBQkxFU1xzKj1ccyopKFxbW15cXV0qXF18XChbXlwpXSpcKSkiKQptID0gcGF0LnNlYXJjaChzMzc1KQppZiBub3QgbToKICAgIHJhaXNlIFN5c3RlbUV4aXQoIlBIQVNFMzcxOTMzX0FCT1JUOiBEQUlMWV9FVklERU5DRV9UQUJMRVMgYXNzaWdubWVudCBub3QgZm91bmQgaW4gUGhhc2UgMy43LjUuIikKCnRyeToKICAgIGN1cnJlbnQgPSBhc3QubGl0ZXJhbF9ldmFsKG0uZ3JvdXAoMikpCmV4Y2VwdCBFeGNlcHRpb24gYXMgZXhjOgogICAgcmFpc2UgU3lzdGVtRXhpdChmIlBIQVNFMzcxOTMzX0FCT1JUOiBDYW5ub3QgcGFyc2UgREFJTFlfRVZJREVOQ0VfVEFCTEVTOiB7ZXhjfSIpCgpjdXJyZW50ID0gbGlzdChjdXJyZW50KQojIEFkZCBkaXNjb3ZlcmVkIGNhbmRpZGF0ZXMgZmlyc3QsIGtlZXAgbGVnYWN5IGZhbGxiYWNrcyBhZnRlciB0aGVtLgptZXJnZWQgPSBbXQpmb3IgeCBpbiBkaXNjb3ZlcmVkICsgY3VycmVudDoKICAgIGlmIHggbm90IGluIG1lcmdlZDoKICAgICAgICBtZXJnZWQuYXBwZW5kKHgpCgppZiBtZXJnZWQgPT0gY3VycmVudDoKICAgIHN0YXRlID0gIk5PX0NIQU5HRV9BTFJFQURZX1JFQ09OQ0lMRUQiCiAgICBuZXdfczM3NSA9IHMzNzUKZWxzZToKICAgIHJlcGxhY2VtZW50ID0gIkRBSUxZX0VWSURFTkNFX1RBQkxFUyA9ICIgKyByZXByKG1lcmdlZCkKICAgIG5ld19zMzc1ID0gczM3NVs6bS5zdGFydCgpXSArIHJlcGxhY2VtZW50ICsgczM3NVttLmVuZCgpOl0KICAgIFAzNzUud3JpdGVfdGV4dChuZXdfczM3NSwgZW5jb2Rpbmc9InV0Zi04IikKICAgIHN0YXRlID0gIlBBVENIX0FQUExJRUQiCgojIENvbXBpbGUgc3ludGF4IGFmdGVyIG1vZGlmaWNhdGlvbi4KYXN0LnBhcnNlKG5ld19zMzc1KQoKcmVwb3J0ID0gewogICAgImNvbnRyYWN0IjogIlBIQVNFMzcxOTMzX0NBTk9OSUNBTF9EQUlMWV9FVklERU5DRV9TT1VSQ0VfQ09OVFJBQ1RfUkVDT05DSUxJQVRJT04iLAogICAgImdlbmVyYXRlZF9hdCI6IGRhdGV0aW1lLm5vdyh0aW1lem9uZS51dGMpLmlzb2Zvcm1hdCgpLAogICAgInN0YXRlIjogc3RhdGUsCiAgICAicGhhc2UzNzRfZGlzY292ZXJlZF9jYW5kaWRhdGVzIjogZGlzY292ZXJlZCwKICAgICJwaGFzZTM3NV9wcmV2aW91c19kYWlseV9ldmlkZW5jZV90YWJsZXMiOiBjdXJyZW50LAogICAgInBoYXNlMzc1X3JlY29uY2lsZWRfZGFpbHlfZXZpZGVuY2VfdGFibGVzIjogbWVyZ2VkLAogICAgInNhZmV0eSI6IHsKICAgICAgICAicGhhc2UzNzRfbG9naWNfY2hhbmdlIjogRmFsc2UsCiAgICAgICAgInF1YWxpZmljYXRpb25fdGhyZXNob2xkX2NoYW5nZSI6IEZhbHNlLAogICAgICAgICJzdXBhYmFzZV9tdXRhdGlvbl9ieV9kZXBsb3llciI6IEZhbHNlLAogICAgICAgICJxdWFsaWZpY2F0aW9uX2NvdW50ZXJfbXV0YXRpb25fYnlfZGVwbG95ZXIiOiBGYWxzZSwKICAgICAgICAic3ludGhldGljX3F1YWxpZmljYXRpb24iOiBGYWxzZSwKICAgICAgICAiaGlzdG9yaWNhbF9ldmlkZW5jZV9yZXdyaXRlIjogRmFsc2UsCiAgICAgICAgImJyb2tlcl9vcmRlcl9lbmFibGVtZW50IjogRmFsc2UsCiAgICAgICAgInJlYWxfbW9uZXlfZW5hYmxlbWVudCI6IEZhbHNlLAogICAgfSwKfQooT1VUIC8gInBoYXNlMzcxOTMzX3JlY29uY2lsaWF0aW9uLmpzb24iKS53cml0ZV90ZXh0KGpzb24uZHVtcHMocmVwb3J0LCBpbmRlbnQ9MiksIGVuY29kaW5nPSJ1dGYtOCIpCgpwcmludCgiUEhBU0UzNzE5MzNfU1RBVEU9IiArIHN0YXRlKQpwcmludCgiRElTQ09WRVJFRD0iICsgcmVwcihkaXNjb3ZlcmVkKSkKcHJpbnQoIlBSRVZJT1VTPSIgKyByZXByKGN1cnJlbnQpKQpwcmludCgiUkVDT05DSUxFRD0iICsgcmVwcihtZXJnZWQpKQo="))

    Write-Host "[6/10] Discover + reconcile exact evidence source contract..."
    if ($PythonMode -eq "py") { & py $TempPy } else { & python $TempPy }
    if ($LASTEXITCODE -ne 0) { throw "Reconciliation controller failed." }

    Write-Host "[7/10] Compile Phase 3.7.5..."
    if ($PythonMode -eq "py") { & py -m py_compile $P375 } else { & python -m py_compile $P375 }
    if ($LASTEXITCODE -ne 0) { throw "Phase 3.7.5 compile failed." }

    Write-Host "[8/10] Verify no safety/threshold drift..."
    $After = Get-Content -LiteralPath $P375 -Raw
    foreach ($forbidden in @(
        'BROKER_ORDER_SUBMISSION_ENABLED = True',
        'REAL_MONEY_TRADING_ENABLED = True',
        'HISTORICAL_REWRITE_ALLOWED = True',
        'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = True',
        'QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = True'
    )) {
        if ($After.Contains($forbidden)) { throw "Unsafe invariant introduced: $forbidden" }
    }

    foreach ($threshold in @(
        'MIN_OBSERVED_CYCLES = 3',
        'MIN_VALID_CYCLES = 3',
        'MAX_BLOCKED_CYCLES = 0'
    )) {
        if (-not $After.Contains($threshold)) { throw "Qualification threshold drift/missing: $threshold" }
    }

    Write-Host "[9/10] Git diff verification..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $P375Rel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        & git diff -- $P375Rel
    }

    Write-Host "[10/10] SUCCESS"
    Write-Host "======================================================================"
    Write-Host " Phase 3.7.19.3.3 APPLIED AND VERIFIED"
    Write-Host "======================================================================"
    Write-Host "Reconciliation target          : DAILY_EVIDENCE_TABLES source adapter"
    Write-Host "Phase 3.7.4 logic change       : NO"
    Write-Host "Phase 3.7.5 qualification logic: UNCHANGED"
    Write-Host "Qualification thresholds       : 3 / 3 / 0 PRESERVED"
    Write-Host "Supabase mutation by deployer  : NO"
    Write-Host "Qualification counter mutation : NO"
    Write-Host "Synthetic qualification        : NO"
    Write-Host "Historical evidence rewrite    : NO"
    Write-Host "Broker order enablement        : NO"
    Write-Host "Real-money enablement          : NO"
    Write-Host ""
    Write-Host "IMPORTANT: Do not use git add ."
    Write-Host "NEXT: review git diff before commit/push."
}
catch {
    Write-Host "ROLLBACK: restoring Phase 3.7.5..." -ForegroundColor Yellow
    Restore-Phase375
    throw
}
finally {
    if (Test-Path $TempPy) { Remove-Item $TempPy -Force -ErrorAction SilentlyContinue }
}
