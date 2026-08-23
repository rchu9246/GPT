#requires -Version 5.1
<#
PHASE37261_V2_RECONSTRUCTION_AUDIT_SCHEMA_COMPATIBILITY_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.6.1 V2 — Reconstruction Audit Schema Compatibility Fix

Observed failure
----------------
Phase 3.7.2.6.1 completed its main reconstruction path but failed while writing
the audit row because PostgREST could not find:

  public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92

and suggested the deployed table:

  public.paper_post_recovery_activation_master_cycle_reconstruction_audit

This patch:
  1) adds compatibility fallback for the audit table;
  2) keeps the existing _v92 name as primary;
  3) uses the non-_v92 name as fallback;
  4) leaves reconstruction logic unchanged;
  5) preserves paper-only / fail-closed safety guarantees;
  6) requires no historical rewrite.

Target
------
  automation/v92/paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py
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
    Write-Host "PATCH FAILED: $Text" -ForegroundColor Red
    exit 1
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

Section "GPT Quant V9.2 — Phase 3.7.2.6.1 V2 Audit Schema Compatibility Fix"

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

$target = Join-Path $repo "automation\v92\paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"

if (-not (Test-Path $target)) {
    Fail "Phase 3.7.2.6.1 Python target not found: $target"
}

$original = Get-Content -LiteralPath $target -Raw
if ([string]::IsNullOrWhiteSpace($original)) {
    Fail "Target Python file is empty."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase37261-v2-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force

Section "Patching reconstruction audit compatibility"

$patched = $original

# Add helper after latest() if not already present.
if (-not $patched.Contains("def insert_compatible_audit(")) {
    $needle = @'
def latest(sb: Supabase, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None
'@

    $replacement = @'
def latest(sb: Supabase, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def insert_compatible_audit(
    sb: Supabase,
    candidates: List[str],
    payload: Dict[str, Any],
) -> str:
    """
    Insert an immutable-style audit row into the first compatible table.

    A PostgREST missing-table error is treated as a schema compatibility miss.
    Any other error remains fail-closed.
    """
    compatibility_errors: List[str] = []

    for table in candidates:
        try:
            sb.request(
                "POST",
                table,
                payload=payload,
                prefer="return=minimal",
            )
            return table
        except RuntimeError as exc:
            message = str(exc)
            missing_table = (
                "HTTP 404" in message
                or "PGRST205" in message
                or "Could not find the table" in message
            )
            if missing_table:
                compatibility_errors.append(f"AUDIT_TABLE_MISSING:{table}")
                continue
            raise

    raise RuntimeError(
        "No compatible reconstruction audit table found: "
        + ", ".join(compatibility_errors)
    )
'@

    if (-not $patched.Contains($needle)) {
        Fail "Could not locate latest() function block for audit compatibility helper insertion."
    }

    $patched = $patched.Replace($needle, $replacement)
}

# Replace direct audit write with compatibility fallback.
$oldAuditWrite = @'
    sb.request(
        "POST",
        "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
        payload=dict(audit, created_at=datetime.now(timezone.utc).isoformat()),
        prefer="return=minimal",
    )
'@

$newAuditWrite = @'
    audit_table_used = insert_compatible_audit(
        sb,
        [
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
            "paper_post_recovery_activation_master_cycle_reconstruction_audit",
        ],
        dict(audit, created_at=datetime.now(timezone.utc).isoformat()),
    )
'@

if ($patched.Contains($oldAuditWrite)) {
    $patched = $patched.Replace($oldAuditWrite, $newAuditWrite)
} elseif (-not $patched.Contains("audit_table_used = insert_compatible_audit(")) {
    Fail "Could not locate direct reconstruction audit write."
}

# Add summary line showing which audit table was used.
$oldSummary = @'
    print("- Historical evidence rewrite: **DISABLED**")
    print()
    print("## Next")
'@

$newSummary = @'
    print("- Historical evidence rewrite: **DISABLED**")
    print(f"- Audit Table Used: **{audit_table_used}**")
    print()
    print("## Next")
'@

if ($patched.Contains($oldSummary) -and -not $patched.Contains("Audit Table Used:")) {
    $patched = $patched.Replace($oldSummary, $newSummary)
}

Write-Utf8NoBom $target $patched
Write-Host "Patched: $target" -ForegroundColor Green

Section "Static validation"

$final = Get-Content -LiteralPath $target -Raw

foreach ($token in @(
    "def insert_compatible_audit(",
    "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
    "paper_post_recovery_activation_master_cycle_reconstruction_audit",
    "AUDIT_TABLE_MISSING",
    "Audit Table Used:"
)) {
    if (-not $final.Contains($token)) {
        Fail "Required compatibility token missing: $token"
    }
}

foreach ($forbidden in @(
    '"broker_api_used": True',
    '"broker_credentials_used": True',
    '"broker_order_submission_enabled": True',
    '"real_money_trading_enabled": True',
    '"live_money_release_authorized": True'
)) {
    if ($final.Contains($forbidden)) {
        Fail "Forbidden capability detected after patch: $forbidden"
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
    & py -3 -m py_compile $target
} else {
    & python -m py_compile $target
}

if ($LASTEXITCODE -ne 0) {
    Fail "Patched Phase 3.7.2.6.1 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Reconstruction audit compatibility helper: PASS" -ForegroundColor Green
Write-Host "Primary _v92 audit table path: PASS" -ForegroundColor Green
Write-Host "Fallback non-_v92 audit table path: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary scan: PASS" -ForegroundColor Green

Section "Git status"
& git status --short

if ($AutoGit) {
    Section "Optional AutoGit"

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    & git add -- $target
    if ($LASTEXITCODE -ne 0) {
        Fail "git add failed"
    }

    $pending = (& git diff --cached --name-only)
    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged V2 changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Fix Phase 3.7.2.6.1 reconstruction audit schema compatibility"
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

Write-Host "Audit table compatibility order:" -ForegroundColor Cyan
Write-Host "  1) paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
Write-Host "  2) paper_post_recovery_activation_master_cycle_reconstruction_audit"
Write-Host ""
Write-Host "No Supabase SQL is required for this V2 compatibility patch." -ForegroundColor Yellow
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Commit and Push the modified Phase 3.7.2.6.1 Python file."
Write-Host "  2) Re-run GitHub Action:"
Write-Host "     GPT Quant Phase 3.7.2.6.1 - Post Recovery Activation Master Cycle Canonical State Reconstruction."
Write-Host "  3) Confirm Reconstruction State = PASS."
Write-Host "  4) Confirm Audit Table Used is shown in Summary."
Write-Host "  5) Then re-run Phase 3.7.2.6."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
