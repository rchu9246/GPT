#requires -Version 5.1
<#
PHASE37189_DEPLOY_V2.ps1

GPT Quant Phase 3.7.18.9 V2
Continuous Qualification Canonical Source Fallback Error Semantics Fix

What this fixes
---------------
A stale fallback exception inside select_latest() can survive even when a later
query successfully reads the canonical source but returns zero rows. That can
produce a false CANONICAL_SOURCE_READ_ERROR and force FAIL_CLOSED.

V2 behavior
-----------
- Required target:
  automation\v92\paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py
- Optional targets are auto-discovered only if they:
  * are under automation\v92
  * contain BOTH "def select_latest(" and "CANONICAL_SOURCE_READ_ERROR"
  * still use the old stale-error implementation
- Missing historical Phase 3655 files DO NOT abort deployment.
- Makes backups before editing.
- Does NOT modify Supabase.
- Does NOT create synthetic incident rows.
- Does NOT bypass FAIL_CLOSED.
- Does NOT force Activation or Runtime Supervision state.
- Runs py_compile and git diff --check after patching.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.9 V2 Deployment"
Write-Host " Canonical Source Fallback Error Semantics Fix"
Write-Host "============================================================"
Write-Host ""

$RepoRoot = (Get-Location).Path
$AutomationRoot = Join-Path $RepoRoot "automation\v92"

if (-not (Test-Path -LiteralPath $AutomationRoot)) {
    throw "automation\v92 not found. Run this script from the GPT repository root."
}

$RequiredRel = "automation\v92\paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py"
$RequiredFull = Join-Path $RepoRoot $RequiredRel

if (-not (Test-Path -LiteralPath $RequiredFull)) {
    throw "Required target file not found: $RequiredRel"
}

# Resolve Python
$PythonMode = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonMode = "python"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonMode = "py"
}
else {
    throw "Python was not found in PATH."
}

Write-Host "[1/7] Discovering eligible targets..."

$CandidateFiles = Get-ChildItem -LiteralPath $AutomationRoot -File -Filter "*.py"
$Targets = New-Object System.Collections.Generic.List[string]

foreach ($File in $CandidateFiles) {
    $Raw = Get-Content -LiteralPath $File.FullName -Raw

    if ($Raw -match "def select_latest\(" -and
        $Raw -match "CANONICAL_SOURCE_READ_ERROR" -and
        $Raw -match "return None,\s*str\(last_error\)\s*if\s*last_error\s*else\s*None") {

        $Rel = $File.FullName.Substring($RepoRoot.Length).TrimStart("\")
        $Targets.Add($Rel)
    }
}

if (-not ($Targets -contains $RequiredRel)) {
    $Targets.Add($RequiredRel)
}

$Targets = $Targets | Sort-Object -Unique

Write-Host "Eligible target files:"
foreach ($Rel in $Targets) {
    Write-Host "  $Rel"
}

# Backup
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase37189-v2-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

Write-Host ""
Write-Host "[2/7] Backing up target files..."

foreach ($Rel in $Targets) {
    $Src = Join-Path $RepoRoot $Rel
    $SafeName = ($Rel -replace "[\\/:*?""<>|]", "_")
    $Dst = Join-Path $BackupDir $SafeName
    Copy-Item -LiteralPath $Src -Destination $Dst -Force
    Write-Host "  backup: $Rel"
}

# Create Python patch helper
$PatchPy = Join-Path $env:TEMP "phase37189_v2_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import sys

targets = [Path(p) for p in sys.argv[1:]]

NEW_FUNCTION = """def select_latest(
    sb: Supabase,
    table: str,
    portfolio_id: str,
    order_candidates: Tuple[str, ...],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    \\"\\"\\"
    Read the latest canonical row with compatibility fallbacks.

    Semantics:
    - Successful query + rows: return latest row, no error.
    - Successful query + zero rows: this is a valid read, not a source error.
    - Candidate compatibility errors may occur while fallbacks continue.
    - Return a source-read error only if every attempted query fails.
    \\"\\"\\"
    last_error: Optional[Exception] = None
    successful_read = False

    filters = [
        "portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe=""),
        "",
    ]

    for filt in filters:
        for col in order_candidates:
            q = "select=*"
            if filt:
                q += "&" + filt
            q += f"&order={col}.desc&limit=1"

            try:
                rows = sb.select(table, q)
                successful_read = True
                if rows:
                    return rows[0], None
            except Exception as exc:
                last_error = exc

    if successful_read:
        return None, None

    return None, str(last_error) if last_error else None


"""

def patch_select_latest(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    start = None
    for i, line in enumerate(lines):
        if line.startswith("def select_latest("):
            start = i
            break

    if start is None:
        raise RuntimeError(f"{path}: select_latest() not found")

    end = None
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("def "):
            end = i
            break

    if end is None:
        raise RuntimeError(f"{path}: could not locate end of select_latest()")

    original = "".join(lines[start:end])

    if "successful_read = False" in original and "if successful_read:" in original:
        print(f"[already fixed] {path}")
        return False

    required = [
        "last_error",
        "filters =",
        "for filt in filters:",
        "for col in order_candidates:",
        "rows = sb.select(table, q)",
        "return None, str(last_error) if last_error else None",
    ]

    missing = [frag for frag in required if frag not in original]
    if missing:
        raise RuntimeError(
            f"{path}: unexpected select_latest() implementation; missing {missing}"
        )

    new_text = "".join(lines[:start]) + NEW_FUNCTION + "".join(lines[end:])
    path.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"[patched] {path}")
    return True

changed = 0
for target in targets:
    if patch_select_latest(target):
        changed += 1

print(f"[summary] changed={changed} targets={len(targets)}")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

Write-Host ""
Write-Host "[3/7] Applying patch..."

$TargetFullPaths = @()
foreach ($Rel in $Targets) {
    $TargetFullPaths += (Join-Path $RepoRoot $Rel)
}

try {
    if ($PythonMode -eq "py") {
        & py -3 $PatchPy @TargetFullPaths
    }
    else {
        & python $PatchPy @TargetFullPaths
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Patch helper failed with exit code $LASTEXITCODE"
    }
}
catch {
    Write-Host ""
    Write-Host "Patch failed. Restoring backups..." -ForegroundColor Yellow

    foreach ($Rel in $Targets) {
        $Dst = Join-Path $RepoRoot $Rel
        $SafeName = ($Rel -replace "[\\/:*?""<>|]", "_")
        $Src = Join-Path $BackupDir $SafeName
        if (Test-Path -LiteralPath $Src) {
            Copy-Item -LiteralPath $Src -Destination $Dst -Force
        }
    }

    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "[4/7] Verifying patch semantics..."

foreach ($Rel in $Targets) {
    $Full = Join-Path $RepoRoot $Rel
    $Raw = Get-Content -LiteralPath $Full -Raw

    if ($Raw -notmatch "successful_read = False") {
        throw "Verification failed: successful_read marker missing in $Rel"
    }

    if ($Raw -notmatch "if successful_read:\s*\r?\n\s*return None, None") {
        throw "Verification failed: zero-row successful-read semantics missing in $Rel"
    }

    Write-Host "  verified: $Rel"
}

Write-Host ""
Write-Host "[5/7] Python compile check..."

foreach ($Rel in $Targets) {
    $Full = Join-Path $RepoRoot $Rel

    if ($PythonMode -eq "py") {
        & py -3 -m py_compile $Full
    }
    else {
        & python -m py_compile $Full
    }

    if ($LASTEXITCODE -ne 0) {
        throw "py_compile failed: $Rel"
    }

    Write-Host "  compile PASS: $Rel"
}

Write-Host ""
Write-Host "[6/7] Git safety checks..."

if (Get-Command git -ErrorAction SilentlyContinue) {
    & git diff --check -- @Targets
    if ($LASTEXITCODE -ne 0) {
        throw "git diff --check failed."
    }

    Write-Host ""
    Write-Host "Changed files:"
    & git status --short -- @Targets

    Write-Host ""
    Write-Host "Patch diff:"
    & git diff -- @Targets
}
else {
    Write-Host "Git not found; skipping git diff checks." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[7/7] Deployment summary"
Write-Host "============================================================"
Write-Host " Phase 3.7.18.9 V2 PATCH APPLIED AND COMPILE-VERIFIED"
Write-Host "============================================================"
Write-Host ""
Write-Host "Backup directory:"
Write-Host "  $BackupDir"
Write-Host ""
Write-Host "Safety boundaries preserved:"
Write-Host "  Supabase schema/data mutation  : NO"
Write-Host "  Synthetic incident insertion   : NO"
Write-Host "  Qualification counter mutation : NO"
Write-Host "  FAIL_CLOSED bypass             : NO"
Write-Host "  Activation force-enable        : NO"
Write-Host "  Runtime supervision override   : NO"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Review the git diff shown above."
Write-Host "  2. If correct, commit and push the changed Python files."
Write-Host "  3. Re-run/observe qualification workflow."
Write-Host "  4. Confirm CANONICAL_SOURCE_READ_ERROR disappears naturally."
Write-Host "  5. Do NOT manually clear FAIL_CLOSED or REVOKED."
Write-Host ""
