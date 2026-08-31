#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.10 Deployment"
Write-Host " Canonical 3of3 Promotion Readiness State Synchronization Fix"
Write-Host "============================================================"
Write-Host ""

$RepoRoot = (Get-Location).Path
$TargetRel = "automation\v92\paper_trading_phase3718_scheduled_automation_end_to_end_observation_natural_qualification_progress_monitoring.py"
$Target = Join-Path $RepoRoot $TargetRel

if (-not (Test-Path -LiteralPath $Target)) {
    throw "Required Phase 3.7.18 target not found: $TargetRel"
}

$PythonMode = if (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    "py"
} else {
    throw "Python not found in PATH."
}

Write-Host "[1/7] Preflight compile..."
if ($PythonMode -eq "py") { & py -3 -m py_compile $Target } else { & python -m py_compile $Target }
if ($LASTEXITCODE -ne 0) { throw "Preflight py_compile failed." }
Write-Host "  Phase 3.7.18 Python compile PASS"

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase371810-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force

Write-Host "[2/7] Backup created:"
Write-Host "  $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371810_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
MARKER = "PHASE371810_CANONICAL_3OF3_PROMOTION_READINESS_STATE_SYNCHRONIZATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

old1 = '    promotion_ready = truthy(readiness.get("promotion_ready", False))\n    readiness_consistent = True\n'
new1 = (
    '    # PHASE371810_CANONICAL_3OF3_PROMOTION_READINESS_STATE_SYNCHRONIZATION_FIX\n'
    '    # Preserve the persisted readiness signal while deriving a read-only\n'
    '    # canonical readiness signal from already-proven 3/3 evidence.\n'
    '    persisted_promotion_ready = truthy(readiness.get("promotion_ready", False))\n'
    '    readiness_consistent = True\n'
)

old2 = '    workflow_failures = [watchdog] if watchdog_blocking else []\n    blockers = []\n'
new2 = (
    '    workflow_failures = [watchdog] if watchdog_blocking else []\n'
    '\n'
    '    canonical_promotion_ready = (\n'
    '        canonical_3of3\n'
    '        and readiness_consistent\n'
    '        and broker_locked\n'
    '        and real_money_locked\n'
    '        and historical_locked\n'
    '        and not workflow_failures\n'
    '    )\n'
    '    promotion_ready = persisted_promotion_ready or canonical_promotion_ready\n'
    '\n'
    '    blockers = []\n'
)

old3 = '            "promotion_ready": promotion_ready,\n            "readiness_consistent": readiness_consistent,\n'
new3 = (
    '            "promotion_ready": promotion_ready,\n'
    '            "persisted_promotion_ready": persisted_promotion_ready,\n'
    '            "canonical_promotion_ready": canonical_promotion_ready,\n'
    '            "readiness_consistent": readiness_consistent,\n'
)

old4 = '        f"- Promotion Ready: **{\'YES\' if promotion_ready else \'NO\'}**",\n        "",\n        "## End-to-End Workflow Chain",\n'
new4 = (
    '        f"- Promotion Ready: **{\'YES\' if promotion_ready else \'NO\'}**",\n'
    '        f"- Persisted Promotion Ready: **{\'YES\' if persisted_promotion_ready else \'NO\'}**",\n'
    '        f"- Canonical Promotion Ready: **{\'YES\' if canonical_promotion_ready else \'NO\'}**",\n'
    '        "",\n'
    '        "## End-to-End Workflow Chain",\n'
)

pairs = [
    (old1, new1, "persisted readiness"),
    (old2, new2, "canonical readiness"),
    (old3, new3, "result checks"),
    (old4, new4, "summary"),
]

for old, new, label in pairs:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact block, found {count}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8", newline="\n")
print("[patched]", path)
print("[contract] canonical 3/3 + healthy chain + safety locks => canonical promotion ready")
print("[contract] persisted readiness preserved")
print("[contract] no Supabase mutation")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host "ROLLBACK: restoring original Phase 3.7.18 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[3/7] Applying synchronization patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying contract markers..."
    $After = Get-Content -LiteralPath $Target -Raw
    foreach ($Marker in @(
        "PHASE371810_CANONICAL_3OF3_PROMOTION_READINESS_STATE_SYNCHRONIZATION_FIX",
        "persisted_promotion_ready = truthy",
        "canonical_promotion_ready = (",
        "promotion_ready = persisted_promotion_ready or canonical_promotion_ready",
        '"persisted_promotion_ready": persisted_promotion_ready',
        '"canonical_promotion_ready": canonical_promotion_ready',
        "Persisted Promotion Ready:",
        "Canonical Promotion Ready:"
    )) {
        if ($After -notmatch [regex]::Escape($Marker)) { throw "Missing marker: $Marker" }
    }

    Write-Host "[5/7] Compile + whitespace checks..."
    if ($PythonMode -eq "py") { & py -3 -m py_compile $Target } else { & python -m py_compile $Target }
    if ($LASTEXITCODE -ne 0) { throw "Post-patch py_compile failed." }

    $Trailing = Select-String -LiteralPath $Target -Pattern "[ `t]+$"
    if ($Trailing) { throw "Trailing whitespace detected." }

    Write-Host "  py_compile PASS"
    Write-Host "  trailing whitespace NONE"

    Write-Host "[6/7] Git safety check..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $TargetRel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        Write-Host "  git diff --check PASS"
        $env:GIT_PAGER = "cat"
        & git status --short -- $TargetRel
        & git --no-pager diff -- $TargetRel
    }

    Write-Host "[7/7] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.18.10 PATCH APPLIED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host "Backup: $BackupDir"
    Write-Host ""
    Write-Host "Observation only                 : YES"
    Write-Host "Supabase mutation                : NO"
    Write-Host "Qualification counter mutation   : NO"
    Write-Host "Synthetic qualification          : NO"
    Write-Host "Production schedule mutation     : NO"
    Write-Host "Broker order enablement          : NO"
    Write-Host "Real-money enablement            : NO"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
