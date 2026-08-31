#requires -Version 5.1
<#
Phase 3.7.18.9
Continuous Qualification Canonical Source Fallback Error Semantics Fix

Purpose
-------
Fix false CANONICAL_SOURCE_READ_ERROR caused by stale fallback exceptions in
select_latest() when at least one canonical-source query succeeds but returns
zero rows.

Safety boundaries
-----------------
- Does NOT modify Supabase schema or data.
- Does NOT fabricate incident rows.
- Does NOT change qualification thresholds/counters.
- Does NOT bypass FAIL_CLOSED.
- Does NOT force Activation / Runtime Supervision state.
- Only changes select_latest() fallback error semantics in the two canonical
  continuous-qualification engines listed below.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.9 Deployment"
Write-Host " Continuous Qualification Canonical Source Fallback Fix"
Write-Host "============================================================"
Write-Host ""

$RepoRoot = (Get-Location).Path

$Targets = @(
    "automation\v92\paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py",
    "automation\v92\paper_trading_phase3655_autonomous_promotion_control_continuous_qualification_engine.py"
)

foreach ($Rel in $Targets) {
    $Full = Join-Path $RepoRoot $Rel
    if (-not (Test-Path -LiteralPath $Full)) {
        throw "Required target file not found: $Rel`nRun this script from the GPT repository root."
    }
}

$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
}
else {
    throw "Python was not found in PATH."
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase37189-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

Write-Host "[1/5] Backing up target files..."
foreach ($Rel in $Targets) {
    $Src = Join-Path $RepoRoot $Rel
    $Dst = Join-Path $BackupDir ([IO.Path]::GetFileName($Rel))
    Copy-Item -LiteralPath $Src -Destination $Dst -Force
    Write-Host "  backup: $Rel"
}

$PatchPy = Join-Path $env:TEMP "phase37189_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import sys

targets = [Path(p) for p in sys.argv[1:]]

replacement_lines = [
    'def select_latest(\n',
    '    sb: Supabase,\n',
    '    table: str,\n',
    '    portfolio_id: str,\n',
    '    order_candidates: Tuple[str, ...],\n',
    ') -> Tuple[Optional[Dict[str, Any]], Optional[str]]:\n',
    '    """\n',
    '    Read the latest canonical row with compatibility fallbacks.\n',
    '\n',
    '    A successful query that returns zero rows is still a successful read.\n',
    '    Candidate-column compatibility errors are tolerated while fallbacks remain.\n',
    '    A source-read error is returned only when every attempted query fails.\n',
    '    """\n',
    '    last_error: Optional[Exception] = None\n',
    '    successful_read = False\n',
    '\n',
    '    filters = [\n',
    '        "portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe=""),\n',
    '        "",\n',
    '    ]\n',
    '\n',
    '    for filt in filters:\n',
    '        for col in order_candidates:\n',
    '            q = "select=*"\n',
    '            if filt:\n',
    '                q += "&" + filt\n',
    '            q += f"&order={col}.desc&limit=1"\n',
    '\n',
    '            try:\n',
    '                rows = sb.select(table, q)\n',
    '                successful_read = True\n',
    '                if rows:\n',
    '                    return rows[0], None\n',
    '            except Exception as exc:\n',
    '                last_error = exc\n',
    '\n',
    '    if successful_read:\n',
    '        return None, None\n',
    '\n',
    '    return None, str(last_error) if last_error else None\n',
    '\n',
    '\n',
]
replacement = ''.join(replacement_lines)

def replace_function(text: str, path: Path) -> str:
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
        raise RuntimeError(f"{path}: could not locate function boundary after select_latest()")

    original = "".join(lines[start:end])

    required_fragments = [
        "last_error",
        "filters =",
        "for filt in filters:",
        "for col in order_candidates:",
        "rows = sb.select(table, q)",
        "return None, str(last_error) if last_error else None",
    ]
    missing = [frag for frag in required_fragments if frag not in original]
    if missing:
        raise RuntimeError(
            f"{path}: select_latest() shape is unexpected; missing: {missing}. No patch applied."
        )

    if "successful_read = False" in original and "if successful_read:" in original:
        print(f"[already fixed] {path}")
        return text

    new_text = "".join(lines[:start]) + replacement + "".join(lines[end:])
    print(f"[patched] {path}")
    return new_text

for path in targets:
    text = path.read_text(encoding="utf-8")
    new_text = replace_function(text, path)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8", newline="\n")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

Write-Host "[2/5] Applying semantic fix..."
$TargetFullPaths = $Targets | ForEach-Object { Join-Path $RepoRoot $_ }

try {
    if ($PythonCmd -eq "py") {
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
        $Src = Join-Path $BackupDir ([IO.Path]::GetFileName($Rel))
        Copy-Item -LiteralPath $Src -Destination $Dst -Force
    }
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}

Write-Host "[3/5] Verifying patched semantics..."
foreach ($Rel in $Targets) {
    $Full = Join-Path $RepoRoot $Rel
    $Raw = Get-Content -LiteralPath $Full -Raw
    if ($Raw -notmatch "successful_read = False") {
        throw "Verification failed: successful_read marker missing in $Rel"
    }
    if ($Raw -notmatch "if successful_read:\s*\r?\n\s*return None, None") {
        throw "Verification failed: successful-read zero-row semantics missing in $Rel"
    }
    Write-Host "  verified: $Rel"
}

Write-Host "[4/5] Python compile check..."
foreach ($Rel in $Targets) {
    $Full = Join-Path $RepoRoot $Rel
    if ($PythonCmd -eq "py") {
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

Write-Host "[5/5] Git diff safety check..."
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
Write-Host "============================================================"
Write-Host " Phase 3.7.18.9 PATCH APPLIED AND COMPILE-VERIFIED"
Write-Host "============================================================"
Write-Host ""
Write-Host "Backup directory:"
Write-Host "  $BackupDir"
Write-Host ""
Write-Host "Safety semantics preserved:"
Write-Host "  Supabase mutation             : NO"
Write-Host "  Synthetic incident row        : NO"
Write-Host "  Qualification bypass          : NO"
Write-Host "  FAIL_CLOSED bypass            : NO"
Write-Host "  Activation force-enable       : NO"
Write-Host "  Runtime supervision override  : NO"
Write-Host ""
Write-Host "Next commands after reviewing the diff:"
Write-Host '  git add automation/v92/paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py automation/v92/paper_trading_phase3655_autonomous_promotion_control_continuous_qualification_engine.py'
Write-Host '  git commit -m "Phase 3.7.18.9 canonical source fallback error semantics fix"'
Write-Host '  git push origin main'
Write-Host ""
Write-Host "After push, verify the next qualification run before changing canonical state."
Write-Host "Do not manually clear FAIL_CLOSED/REVOKED."
Write-Host ""
