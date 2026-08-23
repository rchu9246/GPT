#requires -Version 5.1
<#
PHASE37261_V4_CANONICAL_AUDIT_TABLE_NAME_COMPATIBILITY_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.6.1 V4 — Canonical Audit Table Name Compatibility Fix

Purpose
-------
Unify all Phase 3.7.2.6.1 audit-table references on the canonical V9.2 table:

  public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92

Observed issue
--------------
The V3 verification path queried the non-canonical name:

  public.paper_post_recovery_activation_master_cycle_reconstruction_audit

while Supabase/PostgREST indicated the canonical table is:

  public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92

This V4 patch:
  1) forces the V3 verification script to use the canonical _v92 table;
  2) forces the Phase 3.7.2.6.1 reconstruction audit write to prefer _v92;
  3) removes the non-_v92 fallback from the active compatibility path;
  4) keeps all historical evidence untouched;
  5) keeps paper-only safety boundaries unchanged;
  6) requires NO Supabase SQL.

Targets
-------
  automation/v92/paper_trading_phase37261_v3_reconstruction_audit_schema_recovery_verify.py
  automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py
#>

param(
    [switch]$AutoGit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "PATCH FAILED: $Text" -ForegroundColor Red
    exit 1
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

Section "GPT Quant V9.2 — Phase 3.7.2.6.1 V4 Canonical Audit Table Name Compatibility Fix"

$repo = $null
try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = $null
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this patch from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$verifyTarget = Join-Path $repo "automation\v92\paper_trading_phase37261_v3_reconstruction_audit_schema_recovery_verify.py"
$reconTarget  = Join-Path $repo "automation\v92\paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"

foreach ($target in @($verifyTarget, $reconTarget)) {
    if (-not (Test-Path $target)) {
        Fail "Required target not found: $target"
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase37261-v4-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
Copy-Item $verifyTarget (Join-Path $backupRoot ([IO.Path]::GetFileName($verifyTarget))) -Force
Copy-Item $reconTarget  (Join-Path $backupRoot ([IO.Path]::GetFileName($reconTarget))) -Force

Section "Patching V3 verifier to canonical _v92 audit table"

$verify = Get-Content -LiteralPath $verifyTarget -Raw

# Normalize TABLE assignment to canonical name.
$verify = $verify -replace 'TABLE\s*=\s*"paper_post_recovery_activation_master_cycle_reconstruction_audit"', 'TABLE = "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"'

if (-not $verify.Contains('TABLE = "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"')) {
    Fail "Could not normalize V3 verifier TABLE constant."
}

Write-Utf8NoBom $verifyTarget $verify
Write-Host "Patched: $verifyTarget" -ForegroundColor Green

Section "Patching Phase 3.7.2.6.1 reconstruction audit write"

$recon = Get-Content -LiteralPath $reconTarget -Raw

# If compatibility helper exists, force canonical-only list.
$canonicalList = @'
        [
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
        ],
'@

$legacyTwoList = @'
        [
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
            "paper_post_recovery_activation_master_cycle_reconstruction_audit",
        ],
'@

if ($recon.Contains($legacyTwoList)) {
    $recon = $recon.Replace($legacyTwoList, $canonicalList)
}

# Also normalize any direct non-v92 literal.
$recon = $recon.Replace(
    '"paper_post_recovery_activation_master_cycle_reconstruction_audit"',
    '"paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"'
)

# Add a canonical audit marker to the summary if not already present.
if (-not $recon.Contains("Canonical Audit Table:")) {
    $needle = @'
    print("- Historical evidence rewrite: **DISABLED**")
'@
    $replacement = @'
    print("- Historical evidence rewrite: **DISABLED**")
    print("- Canonical Audit Table: **paper_post_recovery_activation_master_cycle_reconstruction_audit_v92**")
'@
    if ($recon.Contains($needle)) {
        $recon = $recon.Replace($needle, $replacement)
    }
}

Write-Utf8NoBom $reconTarget $recon
Write-Host "Patched: $reconTarget" -ForegroundColor Green

Section "Static validation"

$verifyFinal = Get-Content -LiteralPath $verifyTarget -Raw
$reconFinal  = Get-Content -LiteralPath $reconTarget -Raw
$combined = $verifyFinal + "`n" + $reconFinal

foreach ($token in @(
    'TABLE = "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"',
    "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Required canonical audit token missing: $token"
    }
}

# Ensure verifier no longer points at the legacy table name.
$legacyVerifierPattern = 'TABLE\s*=\s*"paper_post_recovery_activation_master_cycle_reconstruction_audit"'
if ($verifyFinal -match $legacyVerifierPattern) {
    Fail "Legacy non-_v92 verifier table assignment is still present."
}

# Ensure active compatibility candidate list no longer contains legacy table.
if ($reconFinal.Contains(@'
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
            "paper_post_recovery_activation_master_cycle_reconstruction_audit",
'@)) {
    Fail "Legacy non-_v92 audit fallback is still active."
}

foreach ($forbidden in @(
    '"broker_api_used": True',
    '"broker_credentials_used": True',
    '"broker_order_submission_enabled": True',
    '"real_money_trading_enabled": True',
    '"live_money_release_authorized": True'
)) {
    if ($combined.Contains($forbidden)) {
        Fail "Forbidden capability detected: $forbidden"
    }
}

$pythonExe = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} else {
    Fail "Python not found in PATH."
}

if ($pythonExe -eq "py") {
    & py -3 -m py_compile $verifyTarget
    if ($LASTEXITCODE -ne 0) { Fail "V3 verifier compile failed." }
    & py -3 -m py_compile $reconTarget
} else {
    & python -m py_compile $verifyTarget
    if ($LASTEXITCODE -ne 0) { Fail "V3 verifier compile failed." }
    & python -m py_compile $reconTarget
}

if ($LASTEXITCODE -ne 0) {
    Fail "Phase 3.7.2.6.1 reconstruction compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "V3 verifier canonical _v92 table normalization: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.2.6.1 canonical audit write normalization: PASS" -ForegroundColor Green
Write-Host "Legacy non-_v92 active fallback removal: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary scan: PASS" -ForegroundColor Green

Section "Git status"
& git status --short

if ($AutoGit) {
    Section "Optional AutoGit"

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    & git add -- $verifyTarget $reconTarget
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed"
    }

    $pending = (& git diff --cached --name-only)
    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged V4 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Fix Phase 3.7.2.6.1 canonical audit table naming"
        if ($LASTEXITCODE -ne 0) {
            Fail "git commit failed"
        }

        & git push origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git push origin main failed"
        }

        Write-Host "AutoGit commit + push: PASS" -ForegroundColor Green
    }
}

Section "PATCH COMPLETE"

Write-Host "Canonical audit table:" -ForegroundColor Cyan
Write-Host "  paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
Write-Host ""
Write-Host "No Supabase SQL is required for this V4 patch." -ForegroundColor Yellow
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Commit and Push the two modified Python files."
Write-Host "  2) Re-run:"
Write-Host "     GPT Quant Phase 3.7.2.6.1 V3 - Reconstruction Audit Schema Recovery Verify"
Write-Host "  3) Confirm PostgREST Schema Visibility = PASS."
Write-Host "  4) Re-run:"
Write-Host "     GPT Quant Phase 3.7.2.6.1 - Post Recovery Activation Master Cycle Canonical State Reconstruction"
Write-Host "  5) If Reconstruction State = PASS, re-run Phase 3.7.2.6."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
