#requires -Version 5.1
<#
PHASE37171_WATCHDOG_ALERT_RESULT_SEMANTICS_FIX_DEPLOY_V3.ps1

GPT Quant Phase 3.7.17.1 V3
Scheduled Workflow Watchdog Alert Result Semantics Fix

Purpose
-------
Separate "watchdog detected alert(s)" from "watchdog execution failed".

Desired semantics
-----------------
1) WATCHDOG_ALERT_DETECTED + valid Phase 3.7.17 evidence
   => workflow SUCCESS
   => alert evidence preserved
   => email alert preserved

2) WATCHDOG_HEALTHY + valid Phase 3.7.17 evidence
   => workflow SUCCESS

3) Missing/unrecognized watchdog evidence or real execution failure
   => workflow FAILURE (fail-closed)

Safety boundaries
-----------------
- No Supabase mutation
- No qualification counter mutation
- No synthetic qualification
- No runtime state force-enable
- No alert suppression
- No evidence deletion
- No FAIL_CLOSED bypass
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.17.1 V3 Deployment"
Write-Host " Watchdog Alert Result Semantics Fix"
Write-Host "============================================================"
Write-Host ""

$RepoRoot = (Get-Location).Path
$WorkflowRoot = Join-Path $RepoRoot ".github\workflows"
$PythonRel = "automation\v92\paper_trading_phase3717_scheduled_workflow_watchdog_email_alert.py"
$PythonFile = Join-Path $RepoRoot $PythonRel

if (-not (Test-Path -LiteralPath $WorkflowRoot)) {
    throw ".github\workflows not found. Run this script from the GPT repository root."
}

if (-not (Test-Path -LiteralPath $PythonFile)) {
    throw "Required watchdog Python file not found: $PythonRel"
}

$PythonMode = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonMode = "python"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonMode = "py"
}
else {
    throw "Python not found in PATH."
}

Write-Host "[1/7] Locating Phase 3.7.17 workflow..."

$WorkflowCandidates = @()

foreach ($File in Get-ChildItem -LiteralPath $WorkflowRoot -File) {
    if ($File.Extension -notin @(".yml", ".yaml")) {
        continue
    }

    $Raw = Get-Content -LiteralPath $File.FullName -Raw

    if ($Raw -match "paper_trading_phase3717_scheduled_workflow_watchdog_email_alert\.py") {
        $WorkflowCandidates += $File
    }
}

$WorkflowCount = @($WorkflowCandidates).Count

if ($WorkflowCount -eq 0) {
    throw "No workflow references the Phase 3.7.17 watchdog Python file."
}

if ($WorkflowCount -gt 1) {
    Write-Host "Multiple matching workflows found:" -ForegroundColor Yellow
    foreach ($File in $WorkflowCandidates) {
        Write-Host "  $($File.FullName)"
    }
    throw "Ambiguous workflow selection. No changes made."
}

$WorkflowFile = $WorkflowCandidates[0]
$WorkflowRel = $WorkflowFile.FullName.Substring($RepoRoot.Length).TrimStart("\")

Write-Host "  Python   : $PythonRel"
Write-Host "  Workflow : $WorkflowRel"

Write-Host ""
Write-Host "[2/7] Preflight checks..."

if ($PythonMode -eq "py") {
    & py -3 -m py_compile $PythonFile
}
else {
    & python -m py_compile $PythonFile
}

if ($LASTEXITCODE -ne 0) {
    throw "Preflight Python compile failed: $PythonRel"
}

Write-Host "  watchdog Python compile PASS"

$WorkflowRawBefore = Get-Content -LiteralPath $WorkflowFile.FullName -Raw

if ($WorkflowRawBefore -notmatch "Run watchdog") {
    Write-Host "  warning: workflow does not contain exact step name 'Run watchdog'" -ForegroundColor Yellow
}

if ($WorkflowRawBefore -notmatch "(?m)^\s*-\s+name:\s*(Enforce|Enforce Phase 3\.7\.17 result)\s*$") {
    throw "Could not find the expected Enforce step. No changes made."
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase37171-v3-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

$BackupFile = Join-Path $BackupDir $WorkflowFile.Name
Copy-Item -LiteralPath $WorkflowFile.FullName -Destination $BackupFile -Force

Write-Host ""
Write-Host "[3/7] Backup created:"
Write-Host "  $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase37171_v3_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE37171_WATCHDOG_ALERT_RESULT_SEMANTICS_FIX"

if MARKER in text:
    print("[already fixed] marker already present")
    raise SystemExit(0)

lines = text.splitlines(keepends=True)

start = None
indent = None

patterns = [
    r'^(\s*)-\s+name:\s*Enforce\s*$',
    r'^(\s*)-\s+name:\s*Enforce Phase 3\.7\.17 result\s*$',
]

for idx, line in enumerate(lines):
    stripped = line.rstrip("\r\n")
    for pat in patterns:
        m = re.match(pat, stripped)
        if m:
            start = idx
            indent = len(m.group(1))
            break
    if start is not None:
        break

if start is None:
    raise RuntimeError("Enforce step not found")

end = len(lines)

for idx in range(start + 1, len(lines)):
    m = re.match(r'^(\s*)-\s+(?:name:|uses:)', lines[idx])
    if m and len(m.group(1)) == indent:
        end = idx
        break

old_step = "".join(lines[start:end])

if ("exit 1" not in old_step) and ("failure" not in old_step):
    raise RuntimeError("Unexpected Enforce step shape; refusing automatic patch")

i0 = " " * indent
i1 = " " * (indent + 2)
i2 = " " * (indent + 4)

new_step = (
    f"{i0}- name: Enforce Phase 3.7.17 result semantics\n"
    f"{i1}if: always()\n"
    f"{i1}shell: bash\n"
    f"{i1}run: |\n"
    f"{i2}set -euo pipefail\n"
    f"{i2}# {MARKER}\n"
    f"{i2}evidence_dir=\"artifacts/phase3717\"\n"
    f"{i2}\n"
    f"{i2}if [ ! -d \"$evidence_dir\" ]; then\n"
    f"{i2}  echo \"::error::Phase 3.7.17 evidence directory missing.\"\n"
    f"{i2}  exit 1\n"
    f"{i2}fi\n"
    f"{i2}\n"
    f"{i2}if grep -Rqs \"WATCHDOG_ALERT_DETECTED\" \"$evidence_dir\"; then\n"
    f"{i2}  echo \"Phase 3.7.17 watchdog completed successfully and detected alert(s).\"\n"
    f"{i2}  echo \"Alert evidence and email delivery remain preserved.\"\n"
    f"{i2}  exit 0\n"
    f"{i2}fi\n"
    f"{i2}\n"
    f"{i2}if grep -Rqs \"WATCHDOG_HEALTHY\" \"$evidence_dir\"; then\n"
    f"{i2}  echo \"Phase 3.7.17 watchdog completed successfully with no alerts.\"\n"
    f"{i2}  exit 0\n"
    f"{i2}fi\n"
    f"{i2}\n"
    f"{i2}echo \"::error::Unrecognized or missing Phase 3.7.17 watchdog terminal-state evidence.\"\n"
    f"{i2}find \"$evidence_dir\" -maxdepth 2 -type f -print || true\n"
    f"{i2}exit 1\n"
)

patched = "".join(lines[:start]) + new_step + "".join(lines[end:])
path.write_text(patched, encoding="utf-8", newline="\n")

print(f"[patched] {path}")
print("[contract] WATCHDOG_ALERT_DETECTED => exit 0")
print("[contract] WATCHDOG_HEALTHY => exit 0")
print("[contract] missing/unrecognized evidence => exit 1")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Workflow {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.17 workflow..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $WorkflowFile.FullName -Force
    Write-Host "  restored: $WorkflowRel"
}

try {
    Write-Host ""
    Write-Host "[4/7] Applying semantic patch..."

    if ($PythonMode -eq "py") {
        & py -3 $PatchPy $WorkflowFile.FullName
    }
    else {
        & python $PatchPy $WorkflowFile.FullName
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Patch helper failed with exit code $LASTEXITCODE"
    }

    Write-Host ""
    Write-Host "[5/7] Verifying patched workflow..."

    $WorkflowRawAfter = Get-Content -LiteralPath $WorkflowFile.FullName -Raw

    $RequiredMarkers = @(
        "PHASE37171_WATCHDOG_ALERT_RESULT_SEMANTICS_FIX",
        "WATCHDOG_ALERT_DETECTED",
        "WATCHDOG_HEALTHY",
        "Unrecognized or missing Phase 3.7.17 watchdog terminal-state evidence",
        "exit 0",
        "exit 1"
    )

    foreach ($Marker in $RequiredMarkers) {
        if ($WorkflowRawAfter -notmatch [regex]::Escape($Marker)) {
            throw "Verification failed; missing marker: $Marker"
        }
    }

    Write-Host "  WATCHDOG_ALERT_DETECTED => workflow execution SUCCESS"
    Write-Host "  WATCHDOG_HEALTHY        => workflow execution SUCCESS"
    Write-Host "  Missing evidence        => workflow FAILURE"

    Write-Host ""
    Write-Host "[6/7] Regression safety checks..."

    if ($PythonMode -eq "py") {
        & py -3 -m py_compile $PythonFile
    }
    else {
        & python -m py_compile $PythonFile
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Post-patch watchdog Python compile failed."
    }

    Write-Host "  watchdog Python compile PASS"

    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $WorkflowRel

        if ($LASTEXITCODE -ne 0) {
            throw "git diff --check failed."
        }

        Write-Host ""
        Write-Host "Changed workflow:"
        & git status --short -- $WorkflowRel

        Write-Host ""
        Write-Host "Patch diff:"
        $env:GIT_PAGER = "cat"
        & git --no-pager diff -- $WorkflowRel
    }
    else {
        Write-Host "  Git not found; skipping git diff checks." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "[7/7] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.17.1 V3 PATCH APPLIED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "Backup:"
    Write-Host "  $BackupDir"
    Write-Host ""
    Write-Host "Safety boundaries preserved:"
    Write-Host "  Watchdog detection disabled      : NO"
    Write-Host "  Email alerts suppressed          : NO"
    Write-Host "  Alert evidence deleted           : NO"
    Write-Host "  Supabase mutation                : NO"
    Write-Host "  Qualification bypass             : NO"
    Write-Host "  Runtime state force-enable       : NO"
    Write-Host "  Missing evidence behavior        : FAIL-CLOSED"
    Write-Host ""
}
catch {
    Restore-Workflow
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
