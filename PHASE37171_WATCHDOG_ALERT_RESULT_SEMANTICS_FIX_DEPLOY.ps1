#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path
$WorkflowRoot = Join-Path $RepoRoot ".github\workflows"
$PythonRel = "automation\v92\paper_trading_phase3717_scheduled_workflow_watchdog_email_alert.py"
$PythonFile = Join-Path $RepoRoot $PythonRel

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.17.1"
Write-Host " Watchdog Alert Result Semantics Fix"
Write-Host "============================================================"

if (-not (Test-Path $WorkflowRoot)) { throw "Run from GPT repository root." }
if (-not (Test-Path $PythonFile)) { throw "Missing $PythonRel" }

$Py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { throw "Python not found." }

Write-Host "[1/6] Locating workflow..."
$hits = Get-ChildItem $WorkflowRoot -File | Where-Object {
    $_.Extension -in ".yml",".yaml" -and
    (Get-Content $_.FullName -Raw) -match "paper_trading_phase3717_scheduled_workflow_watchdog_email_alert\.py"
}
if ($hits.Count -ne 1) {
    $hits | ForEach-Object { Write-Host $_.FullName }
    throw "Expected exactly one Phase 3.7.17 workflow; found $($hits.Count)."
}
$Wf = $hits[0]
$WfRel = $Wf.FullName.Substring($RepoRoot.Length).TrimStart("\")
Write-Host "  $WfRel"

Write-Host "[2/6] Preflight compile..."
if ($Py -eq "py") { & py -3 -m py_compile $PythonFile } else { & python -m py_compile $PythonFile }
if ($LASTEXITCODE -ne 0) { throw "Watchdog Python compile failed." }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase37171-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir $Wf.Name
Copy-Item $Wf.FullName $BackupFile -Force

$PatchPy = Join-Path $env:TEMP "phase37171_$Stamp.py"
$Patch = @'
from pathlib import Path
import re, sys

p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
if "PHASE37171_WATCHDOG_ALERT_RESULT_SEMANTICS_FIX" in t:
    print("[already fixed]")
    raise SystemExit(0)

lines = t.splitlines(keepends=True)
start = None
indent = None

for i, line in enumerate(lines):
    m = re.match(r'^(\s*)-\s+name:\s*(?:Enforce|Enforce Phase 3\.7\.17 result)\s*$', line.rstrip())
    if m:
        start = i
        indent = len(m.group(1))
        break

if start is None:
    raise RuntimeError("Enforce step not found")

end = len(lines)
for i in range(start + 1, len(lines)):
    m = re.match(r'^(\s*)-\s+(?:name:|uses:)', lines[i])
    if m and len(m.group(1)) == indent:
        end = i
        break

old = "".join(lines[start:end])
if "exit 1" not in old and "failure" not in old:
    raise RuntimeError("Unexpected Enforce step shape")

i0 = " " * indent
i1 = " " * (indent + 2)
i2 = " " * (indent + 4)

new = (
f"{i0}- name: Enforce Phase 3.7.17 result semantics\n"
f"{i1}if: always()\n"
f"{i1}shell: bash\n"
f"{i1}run: |\n"
f"{i2}set -euo pipefail\n"
f"{i2}# PHASE37171_WATCHDOG_ALERT_RESULT_SEMANTICS_FIX\n"
f"{i2}evidence_dir=\"artifacts/phase3717\"\n"
f"{i2}if [ ! -d \"$evidence_dir\" ]; then\n"
f"{i2}  echo \"::error::Phase 3.7.17 evidence directory missing.\"\n"
f"{i2}  exit 1\n"
f"{i2}fi\n"
f"{i2}if grep -Rqs \"WATCHDOG_ALERT_DETECTED\" \"$evidence_dir\"; then\n"
f"{i2}  echo \"Watchdog completed successfully and detected alert(s).\"\n"
f"{i2}  echo \"Alert evidence/email remain preserved.\"\n"
f"{i2}  exit 0\n"
f"{i2}fi\n"
f"{i2}if grep -Rqs \"WATCHDOG_HEALTHY\" \"$evidence_dir\"; then\n"
f"{i2}  echo \"Watchdog completed successfully with no alerts.\"\n"
f"{i2}  exit 0\n"
f"{i2}fi\n"
f"{i2}echo \"::error::Unrecognized or missing watchdog terminal-state evidence.\"\n"
f"{i2}find \"$evidence_dir\" -maxdepth 2 -type f -print || true\n"
f"{i2}exit 1\n"
)

p.write_text("".join(lines[:start]) + new + "".join(lines[end:]), encoding="utf-8", newline="\n")
print("[patched]", p)
'@
Set-Content $PatchPy $Patch -Encoding UTF8

function Rollback {
    Write-Host "ROLLBACK: restoring workflow..." -ForegroundColor Yellow
    Copy-Item $BackupFile $Wf.FullName -Force
}

try {
    Write-Host "[3/6] Applying semantics patch..."
    if ($Py -eq "py") { & py -3 $PatchPy $Wf.FullName } else { & python $PatchPy $Wf.FullName }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/6] Verifying..."
    $raw = Get-Content $Wf.FullName -Raw
    foreach ($m in @(
        "PHASE37171_WATCHDOG_ALERT_RESULT_SEMANTICS_FIX",
        "WATCHDOG_ALERT_DETECTED",
        "WATCHDOG_HEALTHY",
        "Unrecognized or missing watchdog terminal-state evidence"
    )) {
        if ($raw -notmatch [regex]::Escape($m)) { throw "Missing verification marker: $m" }
    }

    Write-Host "[5/6] Regression checks..."
    if ($Py -eq "py") { & py -3 -m py_compile $PythonFile } else { & python -m py_compile $PythonFile }
    if ($LASTEXITCODE -ne 0) { throw "Post-patch Python compile failed." }

    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $WfRel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        $env:GIT_PAGER = "cat"
        & git status --short -- $WfRel
        & git --no-pager diff -- $WfRel
    }

    Write-Host "[6/6] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.17.1 PATCH APPLIED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host "Backup: $BackupDir"
    Write-Host ""
    Write-Host "Watchdog alerts preserved       : YES"
    Write-Host "Email alerts preserved          : YES"
    Write-Host "Missing evidence fail-closed    : YES"
    Write-Host "Supabase mutation               : NO"
    Write-Host "Qualification bypass            : NO"
    Write-Host "Runtime state force-enable      : NO"
}
catch {
    Rollback
    throw
}
finally {
    Remove-Item $PatchPy -Force -ErrorAction SilentlyContinue
}
