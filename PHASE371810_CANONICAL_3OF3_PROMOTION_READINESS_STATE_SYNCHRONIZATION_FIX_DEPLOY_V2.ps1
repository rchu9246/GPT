#requires -Version 5.1
<#
PHASE371810_CANONICAL_3OF3_PROMOTION_READINESS_STATE_SYNCHRONIZATION_FIX_DEPLOY_V2.ps1

GPT Quant Phase 3.7.18.10 V2
Canonical 3of3 Promotion Readiness State Synchronization Fix

V2 strategy
-----------
Use structural/anchor-based insertion instead of brittle exact multi-line replacement.

Safety
------
- Backup before modification
- Automatic rollback on patch/verification failure
- Python compile verification
- Trailing-whitespace check
- git diff --check
- No Supabase writes
- No qualification counter mutation
- No synthetic qualification
- No production schedule mutation
- No broker order enablement
- No real-money enablement
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.10 V2 Deployment"
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
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    "py"
}
else {
    throw "Python not found in PATH."
}

Write-Host "[1/7] Preflight compile..."
if ($PythonMode -eq "py") {
    & py -3 -m py_compile $Target
}
else {
    & python -m py_compile $Target
}
if ($LASTEXITCODE -ne 0) {
    throw "Preflight py_compile failed."
}
Write-Host "  Phase 3.7.18 Python compile PASS"

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase371810-v2-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force

Write-Host "[2/7] Backup created:"
Write-Host "  $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371810_v2_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371810_CANONICAL_3OF3_PROMOTION_READINESS_STATE_SYNCHRONIZATION_FIX_V2"

if MARKER in text:
    print("[already fixed] V2 marker present")
    raise SystemExit(0)

lines = text.splitlines()

def find_unique(pattern, label):
    hits = [i for i, line in enumerate(lines) if re.search(pattern, line)]
    if len(hits) != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match, found {len(hits)}")
    return hits[0]

# 1) Replace the persisted promotion_ready assignment structurally.
promo_idx = find_unique(
    r'^\s*promotion_ready\s*=\s*truthy\(readiness\.get\("promotion_ready",\s*False\)\)\s*$',
    "promotion_ready assignment",
)
promo_indent = re.match(r'^(\s*)', lines[promo_idx]).group(1)
lines[promo_idx:promo_idx+1] = [
    promo_indent + "# " + MARKER,
    promo_indent + "# Preserve the persisted readiness signal separately.",
    promo_indent + 'persisted_promotion_ready = truthy(readiness.get("promotion_ready", False))',
]

# 2) Find readiness_consistent assignment after promo assignment.
readiness_idx = None
for i in range(promo_idx + 1, min(len(lines), promo_idx + 40)):
    if re.match(r'^\s*readiness_consistent\s*=\s*True\s*$', lines[i]):
        readiness_idx = i
        break
if readiness_idx is None:
    raise RuntimeError("readiness_consistent anchor not found near promotion readiness")

# 3) Find blockers initialization and insert canonical derivation immediately before it.
blockers_idx = None
for i in range(readiness_idx + 1, min(len(lines), readiness_idx + 120)):
    if re.match(r'^\s*blockers\s*=\s*\[\]\s*$', lines[i]):
        blockers_idx = i
        break
if blockers_idx is None:
    raise RuntimeError("blockers anchor not found")

indent = re.match(r'^(\s*)', lines[blockers_idx]).group(1)

# Find a workflow-health variable that already exists before blockers.
window = "\n".join(lines[max(0, readiness_idx):blockers_idx+1])
workflow_expr = None
for candidate in [
    "workflow_chain_healthy",
    "workflow_healthy",
]:
    if re.search(rf'\b{candidate}\b', window):
        workflow_expr = candidate
        break

if workflow_expr is None:
    # Fallback to absence of workflow failures if that list exists.
    if re.search(r'\bworkflow_failures\b', window):
        workflow_expr = "not workflow_failures"
    else:
        raise RuntimeError("No workflow-health anchor found for canonical readiness")

# Safety-lock variable names are already part of Phase 3.7.18 semantics.
required_vars = ["canonical_3of3", "readiness_consistent", "broker_locked", "real_money_locked", "historical_locked"]
full_text = "\n".join(lines)
for var in required_vars:
    if not re.search(rf'\b{re.escape(var)}\b', full_text):
        raise RuntimeError(f"Required safety/readiness variable not found: {var}")

insert = [
    "",
    indent + "# Observation-layer canonical promotion readiness.",
    indent + "# This derives from existing evidence only; it does not mutate persistence.",
    indent + "canonical_promotion_ready = (",
    indent + "    canonical_3of3",
    indent + "    and readiness_consistent",
    indent + "    and broker_locked",
    indent + "    and real_money_locked",
    indent + "    and historical_locked",
    indent + f"    and ({workflow_expr})",
    indent + ")",
    indent + "promotion_ready = persisted_promotion_ready or canonical_promotion_ready",
    "",
]
lines[blockers_idx:blockers_idx] = insert

# 4) Expose persisted/canonical readiness in result dict.
result_idx = None
for i, line in enumerate(lines):
    if re.search(r'"promotion_ready"\s*:\s*promotion_ready', line):
        result_idx = i
        break
if result_idx is None:
    raise RuntimeError("result promotion_ready field not found")

result_indent = re.match(r'^(\s*)', lines[result_idx]).group(1)
lines[result_idx+1:result_idx+1] = [
    result_indent + '"persisted_promotion_ready": persisted_promotion_ready,',
    result_indent + '"canonical_promotion_ready": canonical_promotion_ready,',
]

# 5) Expose both readiness values in markdown summary.
summary_idx = None
for i, line in enumerate(lines):
    if "Promotion Ready:" in line and "promotion_ready" in line:
        summary_idx = i
        break
if summary_idx is None:
    raise RuntimeError("summary Promotion Ready line not found")

sum_indent = re.match(r'^(\s*)', lines[summary_idx]).group(1)
lines[summary_idx+1:summary_idx+1] = [
    sum_indent + 'f"- Persisted Promotion Ready: **{\'YES\' if persisted_promotion_ready else \'NO\'}**",',
    sum_indent + 'f"- Canonical Promotion Ready: **{\'YES\' if canonical_promotion_ready else \'NO\'}**",',
]

clean = "\n".join(line.rstrip(" \t") for line in lines) + "\n"
path.write_text(clean, encoding="utf-8", newline="\n")

print("[patched]", path)
print("[contract] persisted readiness separated")
print("[contract] canonical 3/3 + safety locks + healthy workflow => canonical promotion ready")
print("[contract] effective promotion_ready = persisted OR canonical")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.18 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
    Write-Host "  restored: $TargetRel"
}

try {
    Write-Host "[3/7] Applying structural synchronization patch..."
    if ($PythonMode -eq "py") {
        & py -3 $PatchPy $Target
    }
    else {
        & python $PatchPy $Target
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Patch helper failed."
    }

    Write-Host "[4/7] Verifying synchronization markers..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Marker in @(
        "PHASE371810_CANONICAL_3OF3_PROMOTION_READINESS_STATE_SYNCHRONIZATION_FIX_V2",
        "persisted_promotion_ready = truthy",
        "canonical_promotion_ready = (",
        "promotion_ready = persisted_promotion_ready or canonical_promotion_ready",
        '"persisted_promotion_ready": persisted_promotion_ready',
        '"canonical_promotion_ready": canonical_promotion_ready',
        "Persisted Promotion Ready:",
        "Canonical Promotion Ready:"
    )) {
        if ($After -notmatch [regex]::Escape($Marker)) {
            throw "Verification failed; missing marker: $Marker"
        }
    }

    Write-Host "  persisted readiness preserved"
    Write-Host "  canonical readiness derived"
    Write-Host "  effective promotion readiness synchronized"

    Write-Host "[5/7] Compile + whitespace checks..."
    if ($PythonMode -eq "py") {
        & py -3 -m py_compile $Target
    }
    else {
        & python -m py_compile $Target
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Post-patch py_compile failed."
    }

    $Trailing = Select-String -LiteralPath $Target -Pattern "[ `t]+$"
    if ($Trailing) {
        throw "Trailing whitespace detected."
    }

    Write-Host "  py_compile PASS"
    Write-Host "  trailing whitespace NONE"

    Write-Host "[6/7] Git safety check..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $TargetRel
        if ($LASTEXITCODE -ne 0) {
            throw "git diff --check failed."
        }

        Write-Host "  git diff --check PASS"
        $env:GIT_PAGER = "cat"
        & git status --short -- $TargetRel
        & git --no-pager diff -- $TargetRel
    }

    Write-Host "[7/7] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.18.10 V2 PATCH APPLIED AND VERIFIED"
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
