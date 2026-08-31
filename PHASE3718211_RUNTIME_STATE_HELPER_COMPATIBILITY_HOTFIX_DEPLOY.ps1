#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.21.1 Deployment"
Write-Host " Runtime State Helper Compatibility Hotfix"
Write-Host "============================================================"
Write-Host ""

$RepoRoot = (Get-Location).Path
$TargetRel = "automation\v92\paper_trading_phase374_production_paper_daily_cycle_monitoring_evidence_accumulation.py"
$Target = Join-Path $RepoRoot $TargetRel

if (-not (Test-Path -LiteralPath $Target)) {
    throw "Required Phase 3.7.4 target not found: $TargetRel"
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

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase3718211-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase3718211_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE3718211_RUNTIME_STATE_HELPER_COMPATIBILITY_HOTFIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371821_RUNTIME_SUPERVISION_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE_RECONCILIATION_FIX",
    "cross_domain_semantic_equivalence",
    "state_of(runtime_row)",
    "PHASE371821_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.21 token missing: {token}")

anchor = "def cross_domain_semantic_equivalence(\n"
if text.count(anchor) != 1:
    raise RuntimeError("cross_domain_semantic_equivalence anchor not found exactly once")

helper = '''# PHASE3718211_RUNTIME_STATE_HELPER_COMPATIBILITY_HOTFIX
def runtime_state_compat(row: Dict[str, Any]) -> str:
    if not row:
        return "UNKNOWN"

    lower = {str(k).lower(): v for k, v in row.items()}

    # Prefer runtime/supervision specific fields, then generic state/status.
    for key in (
        "runtime_state",
        "supervision_state",
        "operational_state",
        "state",
        "status",
    ):
        raw = text(lower.get(key))
        if raw:
            return raw.strip().upper()

    return "UNKNOWN"

'''
text = text.replace(anchor, helper + anchor, 1)

count = text.count("state_of(runtime_row)")
if count < 1:
    raise RuntimeError("No state_of(runtime_row) calls found")

text = text.replace("state_of(runtime_row)", "runtime_state_compat(runtime_row)")

# Add compatibility audit contract next to Phase 3.7.18.21 contract.
audit_anchor = '        "cross_domain_semantic_equivalence_contract": "PHASE371821",\n'
if text.count(audit_anchor) != 1:
    raise RuntimeError("Phase 3.7.18.21 audit anchor not found")

audit = '''        "runtime_state_helper_contract": "PHASE3718211",
'''
text = text.replace(audit_anchor, audit_anchor + audit, 1)

for forbidden in (
    "state_of(runtime_row)",
    "BROKER_ORDER_SUBMISSION_ENABLED = True",
    "REAL_MONEY_TRADING_ENABLED = True",
    "HISTORICAL_REWRITE_ALLOWED = True",
):
    if forbidden in text:
        raise RuntimeError(f"Forbidden token remains after patch: {forbidden}")

for hard in ("REVOKED", "FAIL_CLOSED", "BLOCKED", "HALTED", "ERROR", "FAILED"):
    if f'"{hard}"' not in text:
        raise RuntimeError(f"Hard safety state missing after patch: {hard}")

clean = "\n".join(line.rstrip(" \t") for line in text.splitlines()) + "\n"
path.write_text(clean, encoding="utf-8", newline="\n")

print("[patched]", path)
print(f"[contract] replaced {count} undefined state_of(runtime_row) call(s)")
print("[contract] runtime_state_compat helper installed")
print("[contract] supersession semantics unchanged")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
    Write-Host "  restored: $TargetRel"
}

try {
    Write-Host "[3/7] Applying runtime state helper compatibility hotfix..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying helper/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE3718211_RUNTIME_STATE_HELPER_COMPATIBILITY_HOTFIX",
        "runtime_state_compat",
        "runtime_state_helper_contract",
        "PHASE371821_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE",
        "BROKER_ORDER_SUBMISSION_ENABLED = False",
        "REAL_MONEY_TRADING_ENABLED = False",
        "HISTORICAL_REWRITE_ALLOWED = False"
    )) {
        if ($After -notmatch [regex]::Escape($Token)) {
            throw "Verification failed; missing token: $Token"
        }
    }

    if ($After -match [regex]::Escape("state_of(runtime_row)")) {
        throw "Undefined state_of(runtime_row) call still present."
    }

    Write-Host "[5/7] Compile + whitespace checks..."
    if ($PythonMode -eq "py") { & py -3 -m py_compile $Target } else { & python -m py_compile $Target }
    if ($LASTEXITCODE -ne 0) { throw "Post-patch py_compile failed." }

    $Trailing = Select-String -LiteralPath $Target -Pattern "[ `t]+$"
    if ($Trailing) { throw "Trailing whitespace detected." }

    Write-Host "[6/7] Git safety check..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $TargetRel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        $env:GIT_PAGER = "cat"
        & git status --short -- $TargetRel
        & git --no-pager diff -- $TargetRel
    }

    Write-Host "[7/7] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.18.21.1 HOTFIX APPLIED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host "Backup: $BackupDir"
    Write-Host ""
    Write-Host "Runtime helper compatibility      : FIXED"
    Write-Host "Supersession semantics changed    : NO"
    Write-Host "Supabase mutation                 : NO"
    Write-Host "Qualification counter mutation    : NO"
    Write-Host "Synthetic qualification           : NO"
    Write-Host "Production schedule mutation      : NO"
    Write-Host "Broker order enablement           : NO"
    Write-Host "Real-money enablement             : NO"
    Write-Host "Historical evidence rewrite       : NO"
    Write-Host "Hard runtime failure bypass       : NO"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
