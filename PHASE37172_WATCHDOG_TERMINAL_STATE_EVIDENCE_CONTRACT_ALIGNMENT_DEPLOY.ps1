#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path
$WorkflowRel = ".github\workflows\gpt-quant-v92-paper-trading-phase3717-scheduled-workflow-watchdog-email-alert.yml"
$WorkflowFile = Join-Path $RepoRoot $WorkflowRel
$PythonRel = "automation\v92\paper_trading_phase3717_scheduled_workflow_watchdog_email_alert.py"
$PythonFile = Join-Path $RepoRoot $PythonRel

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.17.2"
Write-Host " Watchdog Terminal-State Evidence Contract Alignment"
Write-Host "============================================================"

if (-not (Test-Path -LiteralPath $WorkflowFile)) { throw "Missing workflow: $WorkflowRel" }
if (-not (Test-Path -LiteralPath $PythonFile)) { throw "Missing Python: $PythonRel" }

$Py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { throw "Python not found." }

Write-Host "[1/6] Preflight compile..."
if ($Py -eq "py") { & py -3 -m py_compile $PythonFile } else { & python -m py_compile $PythonFile }
if ($LASTEXITCODE -ne 0) { throw "Preflight compile failed." }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase37172-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($WorkflowFile))
Copy-Item -LiteralPath $WorkflowFile -Destination $BackupFile -Force

Write-Host "[2/6] Backup: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase37172_$Stamp.py"

$Patch = @'
from pathlib import Path
import re, sys

p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")

marker = "PHASE37172_WATCHDOG_TERMINAL_STATE_EVIDENCE_CONTRACT_ALIGNMENT"
if marker in t:
    print("[already fixed]")
    raise SystemExit(0)

lines = t.splitlines(keepends=True)
start = None
indent = None

for i, line in enumerate(lines):
    m = re.match(r'^(\s*)-\s+name:\s*Enforce Phase 3\.7\.17 result semantics\s*$', line.rstrip("\r\n"))
    if m:
        start = i
        indent = len(m.group(1))
        break

if start is None:
    raise RuntimeError("Phase 3.7.17 result-semantics step not found")

end = len(lines)
for i in range(start + 1, len(lines)):
    m = re.match(r'^(\s*)-\s+(?:name:|uses:)', lines[i])
    if m and len(m.group(1)) == indent:
        end = i
        break

i0 = " " * indent
i1 = " " * (indent + 2)
i2 = " " * (indent + 4)

new = [
    f"{i0}- name: Enforce Phase 3.7.17 terminal-state evidence contract\n",
    f"{i1}if: always()\n",
    f"{i1}shell: bash\n",
    f"{i1}run: |\n",
    f"{i2}set -euo pipefail\n",
    f"{i2}# {marker}\n",
    f"{i2}result_json=\"artifacts/phase3717/phase3717_result.json\"\n",
    "\n",
    f"{i2}if [ ! -f \"$result_json\" ]; then\n",
    f"{i2}  echo \"::error::Phase 3.7.17 canonical result JSON is missing.\"\n",
    f"{i2}  exit 1\n",
    f"{i2}fi\n",
    "\n",
    f"{i2}state=$(python -c \"import json,sys; print(str(json.load(open(sys.argv[1], encoding='utf-8')).get('state','')))\" \"$result_json\")\n",
    "\n",
    f"{i2}if [ -z \"$state\" ]; then\n",
    f"{i2}  echo \"::error::Phase 3.7.17 result JSON is missing state.\"\n",
    f"{i2}  exit 1\n",
    f"{i2}fi\n",
    "\n",
    f"{i2}case \"$state\" in\n",
    f"{i2}  WATCHDOG_ALL_SCHEDULED_WORKFLOWS_HEALTHY)\n",
    f"{i2}    echo \"Phase 3.7.17 watchdog terminal state: $state\"\n",
    f"{i2}    exit 0\n",
    f"{i2}    ;;\n",
    f"{i2}  WATCHDOG_ALERT_DETECTED)\n",
    f"{i2}    echo \"Phase 3.7.17 watchdog terminal state: $state\"\n",
    f"{i2}    echo \"Alert evidence/email remain preserved.\"\n",
    f"{i2}    exit 0\n",
    f"{i2}    ;;\n",
    f"{i2}  *)\n",
    f"{i2}    echo \"::error::Unrecognized Phase 3.7.17 watchdog terminal state: $state\"\n",
    f"{i2}    exit 1\n",
    f"{i2}    ;;\n",
    f"{i2}esac\n",
]

patched = "".join(lines[:start]) + "".join(new) + "".join(lines[end:])
clean = "\n".join(x.rstrip(" \t") for x in patched.splitlines()) + "\n"
p.write_text(clean, encoding="utf-8", newline="\n")
print("[patched]", p)
'@

Set-Content -LiteralPath $PatchPy -Value $Patch -Encoding UTF8

function Rollback {
    Write-Host "ROLLBACK: restoring workflow..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $WorkflowFile -Force
}

try {
    Write-Host "[3/6] Applying patch..."
    if ($Py -eq "py") { & py -3 $PatchPy $WorkflowFile } else { & python $PatchPy $WorkflowFile }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/6] Verifying markers..."
    $Raw = Get-Content -LiteralPath $WorkflowFile -Raw
    foreach ($m in @(
        "PHASE37172_WATCHDOG_TERMINAL_STATE_EVIDENCE_CONTRACT_ALIGNMENT",
        "phase3717_result.json",
        "WATCHDOG_ALL_SCHEDULED_WORKFLOWS_HEALTHY",
        "WATCHDOG_ALERT_DETECTED",
        "Unrecognized Phase 3.7.17 watchdog terminal state"
    )) {
        if ($Raw -notmatch [regex]::Escape($m)) { throw "Missing marker: $m" }
    }

    Write-Host "[5/6] Regression checks..."
    if ($Py -eq "py") { & py -3 -m py_compile $PythonFile } else { & python -m py_compile $PythonFile }
    if ($LASTEXITCODE -ne 0) { throw "Post-patch compile failed." }

    $Trailing = Select-String -LiteralPath $WorkflowFile -Pattern "[ `t]+$"
    if ($Trailing) { throw "Trailing whitespace detected." }

    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $WorkflowRel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        $env:GIT_PAGER = "cat"
        & git status --short -- $WorkflowRel
        & git --no-pager diff -- $WorkflowRel
    }

    Write-Host "[6/6] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.17.2 PATCH APPLIED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host "Backup: $BackupDir"
    Write-Host ""
    Write-Host "HEALTHY state accepted            : YES"
    Write-Host "ALERT_DETECTED accepted           : YES"
    Write-Host "Missing/unknown state fail-closed : YES"
    Write-Host "Supabase mutation                 : NO"
    Write-Host "Qualification bypass              : NO"
}
catch {
    Rollback
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
