#requires -Version 5.1
<#
GPT Quant V9.2
Phase 3.7.2.6.1 V5.1
V3 Workflow Contract -> V5 Compatibility Fix

Purpose
-------
The V5 verifier compiles successfully, but the GitHub Actions workflow still
validates the old V3 source-code contract before execution.

Observed failure:
  Compile Phase 3.7.2.6.1 V3 verifier : PASS
  Validate V3 contract                 : FAIL
  Verify PostgREST schema visibility   : NOT REACHED

This patch updates the existing V3 verification workflow contract checks so
they accept the V5 deterministic canonical resolver.

It does NOT:
- modify Supabase schema
- modify historical evidence
- enable broker order submission
- enable real-money trading
- change runtime supervision state

Target workflow
---------------
.github/workflows/gpt-quant-v92-paper-trading-phase37261-v3-reconstruction-audit-schema-recovery.yml
#>

param(
    [switch]$AutoGit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 112) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 112) -ForegroundColor DarkCyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "PHASE37261_V51_FATAL: $Text" -ForegroundColor Red
    exit 1
}

function WriteUtf8([string]$Path, [string]$Text) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

Section "GPT Quant V9.2 — Phase 3.7.2.6.1 V5.1 Workflow Contract Compatibility Fix"

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

$workflow = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase37261-v3-reconstruction-audit-schema-recovery.yml"
$verifier = Join-Path $repo "automation\v92\paper_trading_phase37261_v3_reconstruction_audit_schema_recovery_verify.py"

if (-not (Test-Path $workflow)) {
    Fail "Workflow not found: $workflow"
}
if (-not (Test-Path $verifier)) {
    Fail "Verifier not found: $verifier"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase37261-v51-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $workflow (Join-Path $backup ([IO.Path]::GetFileName($workflow))) -Force

Section "1/3 — Rewrite V3 contract validation for V5 verifier"

$yml = Get-Content -LiteralPath $workflow -Raw

$oldPattern = '(?ms)      - name: Validate V3 contract\s+shell: bash\s+run: \|\s+.*?(?=      - name: Verify PostgREST schema visibility)'

$newBlock = @'
      - name: Validate V3/V5 contract compatibility
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          VERIFY_FILE="automation/v92/paper_trading_phase37261_v3_reconstruction_audit_schema_recovery_verify.py"

          grep -q 'PHASE37261_V5_POSTGREST_CANONICAL_AUDIT_TABLE_RESOLUTION_FIX' "$VERIFY_FILE"
          grep -q 'CANONICAL_AUDIT_TABLE' "$VERIFY_FILE"
          grep -q 'paper_post_recovery_activation_master_cycle_reconstruction_audit_v92' "$VERIFY_FILE"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED = False' "$VERIFY_FILE"
          grep -q 'REAL_MONEY_TRADING_ENABLED = False' "$VERIFY_FILE"
          grep -q 'HISTORICAL_REWRITE_ALLOWED = False' "$VERIFY_FILE"
          grep -q 'Canonical Resolver: \*\*LOCKED_TO_V92\*\*' "$VERIFY_FILE"

          if grep -q 'TABLE = "paper_post_recovery_activation_master_cycle_reconstruction_audit"' "$VERIFY_FILE"; then
            echo "Legacy non-_v92 active verifier table assignment detected."
            exit 1
          fi

          echo "Phase 3.7.2.6.1 V3 workflow / V5 verifier contract compatibility: PASS"

'@

if ($yml -notmatch $oldPattern) {
    Fail "Could not locate existing 'Validate V3 contract' workflow block."
}

$yml = [regex]::Replace($yml, $oldPattern, $newBlock)

WriteUtf8 $workflow $yml
Write-Host "Workflow patched: $workflow" -ForegroundColor Green

Section "2/3 — Static validation"

$final = Get-Content -LiteralPath $workflow -Raw

foreach ($token in @(
    "Validate V3/V5 contract compatibility",
    "PHASE37261_V5_POSTGREST_CANONICAL_AUDIT_TABLE_RESOLUTION_FIX",
    "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "Canonical Resolver:"
)) {
    if (-not $final.Contains($token)) {
        Fail "Required workflow compatibility token missing: $token"
    }
}

if ($final.Contains("      - name: Validate V3 contract")) {
    Fail "Old Validate V3 contract step still remains."
}

$verifyText = Get-Content -LiteralPath $verifier -Raw

foreach ($token in @(
    "PHASE37261_V5_POSTGREST_CANONICAL_AUDIT_TABLE_RESOLUTION_FIX",
    "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False"
)) {
    if (-not $verifyText.Contains($token)) {
        Fail "Current verifier does not satisfy the new workflow contract: $token"
    }
}

Write-Host "V3 workflow contract block replacement: PASS" -ForegroundColor Green
Write-Host "V5 verifier contract alignment: PASS" -ForegroundColor Green
Write-Host "Canonical _v92 table assertion: PASS" -ForegroundColor Green
Write-Host "Paper-only safety assertions: PASS" -ForegroundColor Green

Section "3/3 — Git status"

& git status --short

if ($AutoGit) {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires branch main. Current branch: $branch"
    }

    & git add -- $workflow
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed."
    }

    $staged = (& git diff --cached --name-only)
    if (-not [string]::IsNullOrWhiteSpace(($staged -join "`n"))) {
        & git commit -m "Fix Phase 37261 V3 workflow contract for V5 verifier"
        if ($LASTEXITCODE -ne 0) {
            Fail "git commit failed."
        }

        & git push origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git push failed."
        }

        Write-Host "Commit + Push: PASS" -ForegroundColor Green
    } else {
        Write-Host "No staged workflow changes." -ForegroundColor Yellow
    }
}

Section "PHASE37261 V5.1 PATCH COMPLETE"

Write-Host "No Supabase SQL is required." -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Commit and Push the modified workflow."
Write-Host "  2) Re-run:"
Write-Host "     GPT Quant Phase 3.7.2.6.1 V3 - Reconstruction Audit Schema Recovery Verify"
Write-Host "  3) Expected steps:"
Write-Host "     Compile: PASS"
Write-Host "     Validate V3/V5 contract compatibility: PASS"
Write-Host "     Verify PostgREST schema visibility: EXECUTED"
Write-Host "  4) Confirm:"
Write-Host "     PostgREST Schema Visibility: PASS"
Write-Host "     Canonical Resolver: LOCKED_TO_V92"
Write-Host ""
Write-Host "Backup: $backup" -ForegroundColor DarkGray
