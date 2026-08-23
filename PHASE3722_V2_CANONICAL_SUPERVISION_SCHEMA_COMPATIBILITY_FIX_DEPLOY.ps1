#requires -Version 5.1
<#
PHASE3722_V2_CANONICAL_SUPERVISION_SCHEMA_COMPATIBILITY_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.2 V2 — Canonical Supervision Schema Compatibility Fix

Purpose
-------
Fix Phase 3.7.2.2 runtime-supervision table compatibility.

Observed production schema:
  public.paper_runtime_supervision_state_v92

Previous diagnostic code queried:
  public.paper_runtime_supervision_v92

This patch:
  1) changes the canonical primary table to paper_runtime_supervision_state_v92;
  2) adds a safe fallback reader for older compatibility names;
  3) keeps all diagnostic/recovery safety rules unchanged;
  4) does NOT rewrite historical evidence;
  5) does NOT enable broker/live-money functions.

Target
------
  automation/v92/paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py
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

Section "GPT Quant V9.2 — Phase 3.7.2.2 V2 Canonical Supervision Schema Compatibility Fix"

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

$target = Join-Path $repo "automation\v92\paper_trading_phase3722_observation_fail_closed_root_cause_diagnostic_recovery.py"

if (-not (Test-Path $target)) {
    Fail "Phase 3.7.2.2 Python target not found: $target"
}

$original = Get-Content -LiteralPath $target -Raw
if ([string]::IsNullOrWhiteSpace($original)) {
    Fail "Target Python file is empty."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase3722-v2-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force

Section "Patching canonical supervision reader"

$patched = $original

# 1) Add compatibility helper if it does not already exist.
if (-not $patched.Contains("def latest_compatible(")) {
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

def latest_compatible(
    sb: Supabase,
    candidates: List[tuple[str, str]],
    portfolio_id: str,
) -> tuple[Optional[Dict[str, Any]], Optional[str], List[str]]:
    """
    Read the first compatible canonical table.

    candidates:
        [(table_name, order_column), ...]

    A missing-table PostgREST 404 is treated as a compatibility miss.
    Other errors still fail closed and are re-raised.
    """
    compatibility_notes: List[str] = []

    for table, order_column in candidates:
        try:
            row = latest(sb, table, portfolio_id, order_column)
            compatibility_notes.append(f"SUPERVISION_TABLE_SELECTED:{table}")
            return row, table, compatibility_notes
        except RuntimeError as exc:
            message = str(exc)
            missing_table = (
                "HTTP 404" in message
                or "PGRST205" in message
                or "Could not find the table" in message
            )
            if missing_table:
                compatibility_notes.append(f"SUPERVISION_TABLE_MISSING:{table}")
                continue
            raise

    compatibility_notes.append("SUPERVISION_CANONICAL_TABLE_NOT_FOUND")
    return None, None, compatibility_notes
'@

    if (-not $patched.Contains($needle)) {
        Fail "Could not locate latest() function block for compatibility helper insertion."
    }

    $patched = $patched.Replace($needle, $replacement)
}

# 2) Replace old direct supervision lookup with canonical compatibility lookup.
$oldLookup = @'
    supervision = latest(sb, "paper_runtime_supervision_v92", args.portfolio_id, "supervision_date")
'@

$newLookup = @'
    supervision, supervision_table, supervision_compatibility_notes = latest_compatible(
        sb,
        [
            ("paper_runtime_supervision_state_v92", "supervision_date"),
            ("paper_runtime_supervision_v92", "supervision_date"),
        ],
        args.portfolio_id,
    )
'@

if ($patched.Contains($oldLookup)) {
    $patched = $patched.Replace($oldLookup, $newLookup)
} elseif (-not $patched.Contains('("paper_runtime_supervision_state_v92", "supervision_date")')) {
    Fail "Could not locate the old supervision table lookup."
}

# 3) Add compatibility notes to the diagnostic result after diagnose().
$oldDiagnose = @'
    result = diagnose(supervision, controller, lifecycle, observation, readiness, promotion)
'@

$newDiagnose = @'
    result = diagnose(supervision, controller, lifecycle, observation, readiness, promotion)
    result["supervision_table"] = supervision_table
    result["supervision_compatibility_notes"] = supervision_compatibility_notes
    result["reasons"].extend(supervision_compatibility_notes)
'@

if ($patched.Contains($oldDiagnose) -and -not $patched.Contains('result["supervision_table"]')) {
    $patched = $patched.Replace($oldDiagnose, $newDiagnose)
}

# 4) Persist selected supervision table in evidence document.
$oldEvidence = @'
        "result": result,
        "safety": {
'@

$newEvidence = @'
        "result": result,
        "canonical_sources": {
            "runtime_supervision_table": result.get("supervision_table"),
        },
        "safety": {
'@

if ($patched.Contains($oldEvidence) -and -not $patched.Contains('"canonical_sources": {')) {
    $patched = $patched.Replace($oldEvidence, $newEvidence)
}

# 5) Add summary output showing selected table.
$oldSummary = @'
    print("## Canonical State Snapshot")
    print()
'@

$newSummary = @'
    print("## Canonical State Snapshot")
    print()
    print(f"- Runtime Supervision Table: **{result.get('supervision_table') or 'NOT_FOUND'}**")
'@

if ($patched.Contains($oldSummary) -and -not $patched.Contains("Runtime Supervision Table:")) {
    $patched = $patched.Replace($oldSummary, $newSummary)
}

Write-Utf8NoBom $target $patched
Write-Host "Patched: $target" -ForegroundColor Green

Section "Static validation"

$final = Get-Content -LiteralPath $target -Raw

foreach ($token in @(
    "def latest_compatible(",
    "paper_runtime_supervision_state_v92",
    "paper_runtime_supervision_v92",
    "SUPERVISION_TABLE_SELECTED",
    "SUPERVISION_TABLE_MISSING",
    "SUPERVISION_CANONICAL_TABLE_NOT_FOUND",
    'result["supervision_table"]',
    "Runtime Supervision Table:"
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
    '"live_money_release_authorized": True',
    '"historical_rewrite_allowed": True'
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
    Fail "Patched Phase 3.7.2.2 Python compile failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Canonical supervision primary table: PASS" -ForegroundColor Green
Write-Host "Compatibility fallback reader: PASS" -ForegroundColor Green
Write-Host "No historical rewrite scan: PASS" -ForegroundColor Green
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
        & git commit -m "Fix Phase 3.7.2.2 canonical supervision schema compatibility"
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

Write-Host "Canonical supervision source priority:" -ForegroundColor Cyan
Write-Host "  1) paper_runtime_supervision_state_v92"
Write-Host "  2) paper_runtime_supervision_v92 (legacy compatibility fallback)"
Write-Host ""
Write-Host "No Supabase SQL is required for this V2 patch." -ForegroundColor Yellow
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Commit and Push the modified Phase 3.7.2.2 Python file."
Write-Host "  2) Re-run GitHub Action:"
Write-Host "     GPT Quant Phase 3.7.2.2 - Observation FAIL_CLOSED Root Cause Diagnostic Recovery"
Write-Host "  3) Inspect Recovery State and Runtime Supervision Table in the Summary."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
