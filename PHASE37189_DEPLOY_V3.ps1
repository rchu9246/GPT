#requires -Version 5.1
<#
PHASE37189_DEPLOY_V3.ps1

GPT Quant Phase 3.7.18.9 V3
Continuous Qualification Canonical Source Fallback Error Semantics Fix

V3 fixes the V2 deployment-package quoting bug and patches select_latest()
without inserting a Python docstring.

Safety:
- no Supabase mutation
- no synthetic incident row
- no qualification counter mutation
- no FAIL_CLOSED bypass
- no activation/runtime force-enable
- backup + automatic rollback on ANY verification/compile failure
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path
$AutomationRoot = Join-Path $RepoRoot "automation\v92"
$RequiredRel = "automation\v92\paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py"

if (-not (Test-Path -LiteralPath $AutomationRoot)) {
    throw "automation\v92 not found. Run from GPT repository root."
}
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot $RequiredRel))) {
    throw "Required target not found: $RequiredRel"
}

$PythonMode = if (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    "py"
} else {
    throw "Python not found in PATH."
}

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.9 V3"
Write-Host " Canonical Source Fallback Error Semantics Fix"
Write-Host "============================================================"

# Discover only files that contain both markers.
$Targets = @()
Get-ChildItem -LiteralPath $AutomationRoot -File -Filter "*.py" | ForEach-Object {
    $raw = Get-Content -LiteralPath $_.FullName -Raw
    if ($raw -match "def select_latest\(" -and $raw -match "CANONICAL_SOURCE_READ_ERROR") {
        $rel = $_.FullName.Substring($RepoRoot.Length).TrimStart("\")
        $Targets += $rel
    }
}
if ($Targets -notcontains $RequiredRel) { $Targets += $RequiredRel }
$Targets = $Targets | Sort-Object -Unique

Write-Host ""
Write-Host "[1/7] Eligible targets:"
$Targets | ForEach-Object { Write-Host "  $_" }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase37189-v3-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

function Backup-Targets {
    foreach ($Rel in $Targets) {
        $src = Join-Path $RepoRoot $Rel
        $safe = ($Rel -replace '[\\/:*?"<>|]', '_')
        Copy-Item -LiteralPath $src -Destination (Join-Path $BackupDir $safe) -Force
    }
}

function Restore-Targets {
    Write-Host ""
    Write-Host "ROLLBACK: restoring V3 backups..." -ForegroundColor Yellow
    foreach ($Rel in $Targets) {
        $safe = ($Rel -replace '[\\/:*?"<>|]', '_')
        $src = Join-Path $BackupDir $safe
        $dst = Join-Path $RepoRoot $Rel
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination $dst -Force
            Write-Host "  restored: $Rel"
        }
    }
}

Write-Host ""
Write-Host "[2/7] Creating backups..."
Backup-Targets

$PatchPy = Join-Path $env:TEMP "phase37189_v3_patch_$Stamp.py"

# No embedded Python triple-quoted string is used here.
$PatchCode = @'
from pathlib import Path
import sys

targets = [Path(p) for p in sys.argv[1:]]

NEW_LINES = [
    "def select_latest(\n",
    "    sb: Supabase,\n",
    "    table: str,\n",
    "    portfolio_id: str,\n",
    "    order_candidates: Tuple[str, ...],\n",
    ") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:\n",
    "    # Canonical fallback semantics: zero rows from a successful query is\n",
    "    # a valid read, not a source-read failure. Only fail if every query fails.\n",
    "    last_error: Optional[Exception] = None\n",
    "    successful_read = False\n",
    "    filters = [\n",
    "        \"portfolio_id=eq.\" + urllib.parse.quote(portfolio_id, safe=\"\"),\n",
    "        \"\",\n",
    "    ]\n",
    "    for filt in filters:\n",
    "        for col in order_candidates:\n",
    "            q = \"select=*\"\n",
    "            if filt:\n",
    "                q += \"&\" + filt\n",
    "            q += f\"&order={col}.desc&limit=1\"\n",
    "            try:\n",
    "                rows = sb.select(table, q)\n",
    "                successful_read = True\n",
    "                if rows:\n",
    "                    return rows[0], None\n",
    "            except Exception as exc:\n",
    "                last_error = exc\n",
    "    if successful_read:\n",
    "        return None, None\n",
    "    return None, str(last_error) if last_error else None\n",
    "\n",
    "\n",
]

def patch(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    start = next((i for i,l in enumerate(lines) if l.startswith("def select_latest(")), None)
    if start is None:
        raise RuntimeError(f"{path}: select_latest() not found")

    end = next((i for i in range(start+1, len(lines)) if lines[i].startswith("def ")), None)
    if end is None:
        raise RuntimeError(f"{path}: function boundary not found")

    original = "".join(lines[start:end])

    # V3 can repair both the original implementation and the broken V2 form.
    if "successful_read = False" in original and "if successful_read:" in original:
        # If it already compiles, keep it. V2-broken files will fail pre-check before V3.
        pass

    new_text = "".join(lines[:start]) + "".join(NEW_LINES) + "".join(lines[end:])
    path.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"[patched] {path}")

for t in targets:
    patch(t)
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

try {
    Write-Host ""
    Write-Host "[3/7] Applying V3 patch..."
    $FullTargets = @($Targets | ForEach-Object { Join-Path $RepoRoot $_ })
    if ($PythonMode -eq "py") {
        & py -3 $PatchPy @FullTargets
    } else {
        & python $PatchPy @FullTargets
    }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed: $LASTEXITCODE" }

    Write-Host ""
    Write-Host "[4/7] Semantic verification..."
    foreach ($Rel in $Targets) {
        $raw = Get-Content -LiteralPath (Join-Path $RepoRoot $Rel) -Raw
        if ($raw -notmatch "successful_read = False") {
            throw "successful_read marker missing: $Rel"
        }
        if ($raw -notmatch "if successful_read:\s*\r?\n\s*return None, None") {
            throw "zero-row semantics missing: $Rel"
        }
        Write-Host "  verified: $Rel"
    }

    Write-Host ""
    Write-Host "[5/7] Python compile check..."
    foreach ($Rel in $Targets) {
        $full = Join-Path $RepoRoot $Rel
        if ($PythonMode -eq "py") {
            & py -3 -m py_compile $full
        } else {
            & python -m py_compile $full
        }
        if ($LASTEXITCODE -ne 0) { throw "py_compile failed: $Rel" }
        Write-Host "  compile PASS: $Rel"
    }

    Write-Host ""
    Write-Host "[6/7] Git diff safety check..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- @Targets
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed" }
        & git status --short -- @Targets
        & git diff -- @Targets
    }

    Write-Host ""
    Write-Host "[7/7] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.18.9 V3 PATCH APPLIED AND COMPILE-VERIFIED"
    Write-Host "============================================================"
    Write-Host "Backup: $BackupDir"
    Write-Host ""
    Write-Host "Do NOT manually clear FAIL_CLOSED or REVOKED."
}
catch {
    Restore-Targets
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
