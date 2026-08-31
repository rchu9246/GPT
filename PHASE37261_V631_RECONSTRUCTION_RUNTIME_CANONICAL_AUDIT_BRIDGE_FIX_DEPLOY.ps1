#requires -Version 5.1
<#
GPT Quant V9.2
Phase 3.7.2.6.1 V6.3.1
Reconstruction Runtime Canonical Audit Bridge Fix

Purpose
-------
Phase 3.7.2.6.1 reconstruction still fails because its runtime audit resolver
does not recognize the short canonical PostgREST relation introduced by V6.3:

  phase37261_reconstruction_audit_v92

This patch updates the reconstruction runtime resolver so it prefers the V6.3
short canonical relation and only uses legacy names as compatibility fallbacks.

Safety
------
- Paper-only
- No broker API
- No broker credentials
- No broker order submission
- No real-money trading
- No live-money release
- No historical evidence rewrite
- Fail-closed behavior preserved
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
    Write-Host "PHASE37261_V631_FATAL: $Text" -ForegroundColor Red
    exit 1
}

function WriteUtf8([string]$Path, [string]$Text) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

Section "GPT Quant V9.2 — Phase 3.7.2.6.1 V6.3.1 Runtime Canonical Audit Bridge Fix"

try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = ""
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this deployment from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$target = Join-Path $repo "automation\v92\paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"

if (-not (Test-Path $target)) {
    Fail "Target reconstruction script not found: $target"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $repo ".phase37261-v631-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item $target (Join-Path $backupDir ([IO.Path]::GetFileName($target))) -Force

Section "1/3 — Patch runtime audit resolver"

$text = Get-Content -LiteralPath $target -Raw

$shortCanonical = '"phase37261_reconstruction_audit_v92"'
$longCanonical  = '"paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"'
$legacyLong     = '"paper_post_recovery_activation_master_cycle_reconstruction_audit"'

# Add short canonical relation ahead of known existing long-name candidates.
if (-not $text.Contains($shortCanonical)) {
    if ($text.Contains($longCanonical)) {
        $text = $text.Replace(
            $longCanonical,
            $shortCanonical + "," + [Environment]::NewLine + "            " + $longCanonical
        )
    } else {
        Fail "Could not find existing canonical audit candidate in runtime script."
    }
}

# Add an explicit runtime marker if absent.
if (-not $text.Contains("PHASE37261_V631_RECONSTRUCTION_RUNTIME_CANONICAL_AUDIT_BRIDGE_FIX")) {
    $marker = @'
# PHASE37261_V631_RECONSTRUCTION_RUNTIME_CANONICAL_AUDIT_BRIDGE_FIX
# Preferred audit relation: phase37261_reconstruction_audit_v92
'@
    $text = $marker + [Environment]::NewLine + $text
}

WriteUtf8 $target $text
Write-Host "Patched: $target" -ForegroundColor Green

Section "2/3 — Static validation"

$final = Get-Content -LiteralPath $target -Raw

foreach ($token in @(
    "PHASE37261_V631_RECONSTRUCTION_RUNTIME_CANONICAL_AUDIT_BRIDGE_FIX",
    "phase37261_reconstruction_audit_v92"
)) {
    if (-not $final.Contains($token)) {
        Fail "Required V6.3.1 token missing: $token"
    }
}

# Short canonical relation must appear before the long canonical relation.
$shortPos = $final.IndexOf("phase37261_reconstruction_audit_v92")
$longPos  = $final.IndexOf("paper_post_recovery_activation_master_cycle_reconstruction_audit_v92")

if ($shortPos -lt 0 -or $longPos -lt 0 -or $shortPos -gt $longPos) {
    Fail "Short canonical relation is not preferred ahead of the long canonical relation."
}

foreach ($forbidden in @(
    '"broker_api_used": True',
    '"broker_credentials_used": True',
    '"broker_order_submission_enabled": True',
    '"real_money_trading_enabled": True',
    '"live_money_release_authorized": True',
    'HISTORICAL_REWRITE_ALLOWED = True'
)) {
    if ($final.Contains($forbidden)) {
        Fail "Forbidden capability detected: $forbidden"
    }
}

$python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} else {
    Fail "Python not found in PATH."
}

if ($python -eq "py") {
    & py -3 -m py_compile $target
} else {
    & python -m py_compile $target
}

if ($LASTEXITCODE -ne 0) {
    Fail "Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Short canonical audit relation bridge: PASS" -ForegroundColor Green
Write-Host "Canonical resolver precedence: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary: PASS" -ForegroundColor Green
Write-Host "Historical rewrite prohibition: PRESERVED" -ForegroundColor Green

Section "3/3 — Git status"

& git status --short

if ($AutoGit) {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires branch main. Current branch: $branch"
    }

    & git add -- $target
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed."
    }

    $staged = (& git diff --cached --name-only)
    if (-not [string]::IsNullOrWhiteSpace(($staged -join "`n"))) {
        & git commit -m "Fix Phase 37261 V6.3.1 runtime canonical audit bridge"
        if ($LASTEXITCODE -ne 0) {
            Fail "git commit failed."
        }

        & git push origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git push failed."
        }

        Write-Host "Commit + Push: PASS" -ForegroundColor Green
    }
}

Section "PHASE37261 V6.3.1 PATCH COMPLETE"

Write-Host "Preferred runtime audit relation:" -ForegroundColor Cyan
Write-Host "  phase37261_reconstruction_audit_v92"
Write-Host ""
Write-Host "No Supabase SQL is required for V6.3.1." -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Commit + Push the modified reconstruction Python file."
Write-Host "  2) Re-run:"
Write-Host "     GPT Quant Phase 3.7.2.6.1 - Post Recovery Activation Master Cycle Canonical State Reconstruction"
Write-Host "  3) Expected: audit resolver uses phase37261_reconstruction_audit_v92."
Write-Host "  4) If Phase 3.7.2.6.1 passes, then run Phase 3.7.2.6."
Write-Host ""
Write-Host "Backup: $backupDir" -ForegroundColor DarkGray
