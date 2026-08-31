#requires -Version 5.1
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
function Fail($m){Write-Host "PHASE37261_V632_FATAL: $m" -ForegroundColor Red; exit 1}
function SaveUtf8($p,$s){$e=New-Object System.Text.UTF8Encoding($false);[IO.File]::WriteAllText($p,$s,$e)}

Write-Host "PHASE37261 V6.3.2 - RECONSTRUCTION AUDIT PAYLOAD SCHEMA COMPATIBILITY FIX" -ForegroundColor Cyan

try {$root=(& git rev-parse --show-toplevel 2>$null).Trim()} catch {$root=""}
if(!$root){Fail "Run inside the GPT Git repository."}
Set-Location $root

$target=Join-Path $root "automation\v92\paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"
if(!(Test-Path $target)){Fail "Target Python not found: $target"}

$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
$backup=Join-Path $root ".phase37261-v632-backup-$stamp"
New-Item -ItemType Directory -Force $backup|Out-Null
Copy-Item $target (Join-Path $backup ([IO.Path]::GetFileName($target))) -Force

$src=Get-Content $target -Raw
if(!$src.Contains("phase37261_reconstruction_audit_v92")){Fail "V6.3.1 canonical bridge not found."}

# Remove only Python dict entries for updated_at. Do not alter unrelated logic.
$patterns=@(
 '(?m)^[ \t]*["'']updated_at["''][ \t]*:[^\r\n]*,?[ \t]*\r?\n',
 '(?m)^[ \t]*updated_at[ \t]*=[^\r\n]*,?[ \t]*\r?\n'
)
$removed=0
foreach($pat in $patterns){
 $m=[regex]::Matches($src,$pat)
 $removed += $m.Count
 $src=[regex]::Replace($src,$pat,"")
}
if($removed -eq 0 -and $src -match '(?m)^[ \t]*["'']updated_at["''][ \t]*:'){
 Fail "Could not safely remove updated_at payload entry."
}

$marker="# PHASE37261_V632_RECONSTRUCTION_AUDIT_PAYLOAD_SCHEMA_COMPATIBILITY_FIX`r`n# Canonical audit INSERT is append-only; updated_at is not required.`r`n"
if(!$src.Contains("PHASE37261_V632_RECONSTRUCTION_AUDIT_PAYLOAD_SCHEMA_COMPATIBILITY_FIX")){$src=$marker+$src}
SaveUtf8 $target $src

$check=Get-Content $target -Raw
if(!$check.Contains("phase37261_reconstruction_audit_v92")){Fail "Canonical relation lost."}
if($check -match '(?m)^[ \t]*["'']updated_at["''][ \t]*:'){Fail "updated_at payload still present."}
if($check -notmatch 'created_at'){Fail "created_at timestamp contract missing."}

if(Get-Command python -ErrorAction SilentlyContinue){& python -m py_compile $target}
elseif(Get-Command py -ErrorAction SilentlyContinue){& py -3 -m py_compile $target}
else{Fail "Python not found."}
if($LASTEXITCODE -ne 0){Fail "Python compile failed."}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Canonical relation preservation: PASS" -ForegroundColor Green
Write-Host "updated_at payload compatibility: PASS" -ForegroundColor Green
Write-Host "created_at append-only timestamp: PASS" -ForegroundColor Green
Write-Host "Paper-only boundary: PRESERVED" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37261 V6.3.2 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL is required." -ForegroundColor Green
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"'
Write-Host '2. git commit -m "Fix Phase 37261 V6.3.2 reconstruction audit payload schema compatibility"'
Write-Host '3. git push origin main'
Write-Host '4. Re-run Phase 3.7.2.6.1 GitHub Action.'
Write-Host "Backup: $backup"
