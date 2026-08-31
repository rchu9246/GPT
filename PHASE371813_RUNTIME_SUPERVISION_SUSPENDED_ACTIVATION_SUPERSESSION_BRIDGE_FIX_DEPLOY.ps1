#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.13 Deployment"
Write-Host " Runtime Supervision Suspended Activation Supersession Bridge Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371813-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force

$PatchPy = Join-Path $env:TEMP "phase371813_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
MARKER = "PHASE371813_RUNTIME_SUPERVISION_SUSPENDED_ACTIVATION_SUPERSESSION_BRIDGE_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371812_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_STATE_RECONCILIATION_FIX",
    "def suspended_is_superseded(",
    'return False, "SUSPENDED_NOT_SUPERSEDED_BY_ACTIVATION"',
    'return False, "SUSPENDED_NOT_SUPERSEDED_BY_MASTER"',
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.12 token missing: {token}")

pattern = re.compile(
    r'def suspended_is_superseded\(\n'
    r'    runtime_row: Dict\[str, Any\],\n'
    r'    activation_row: Dict\[str, Any\],\n'
    r'    master_row: Dict\[str, Any\],\n'
    r'\) -> Tuple\[bool, str\]:\n'
    r'.*?'
    r'    return True, "SUSPENDED_STALE_SUPERSEDED_BY_NEWER_CANONICAL_LIFECYCLE"\n',
    re.S,
)
m = pattern.search(text)
if not m:
    raise RuntimeError("Phase 3.7.18.12 suspended_is_superseded block not found")

replacement = '''def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    # PHASE371813_RUNTIME_SUPERVISION_SUSPENDED_ACTIVATION_SUPERSESSION_BRIDGE_FIX
    runtime_ts = canonical_timestamp(runtime_row)
    activation_ts = canonical_timestamp(activation_row)
    master_ts = canonical_timestamp(master_row)

    if runtime_ts is None:
        return False, "SUSPENDED_RUNTIME_TIMESTAMP_MISSING"
    if master_ts is None:
        return False, "SUSPENDED_MASTER_TIMESTAMP_MISSING"

    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"
    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    if master_ts <= runtime_ts:
        return False, "SUSPENDED_NOT_SUPERSEDED_BY_MASTER"

    if activation_ts is not None and activation_ts > runtime_ts:
        return True, "SUSPENDED_SUPERSEDED_BY_NEWER_ACTIVATION_AND_MASTER"

    return True, "SUSPENDED_SUPERSEDED_BY_ACTIVE_ACTIVATION_AND_NEWER_MASTER_BRIDGE"
'''

text = text[:m.start()] + replacement + text[m.end():]

old = '"compatibility_contract": "PHASE371812_SUSPENDED_CANONICAL_RECONCILIATION",'
if text.count(old) != 1:
    raise RuntimeError("Phase 3.7.18.12 compatibility label not found exactly once")
text = text.replace(
    old,
    '"compatibility_contract": "PHASE371813_SUSPENDED_ACTIVATION_SUPERSESSION_BRIDGE",',
    1,
)

anchor = '''        "master_cycle_timestamp": (
            canonical_timestamp(sources["master_cycle"]["latest"]).isoformat()
            if canonical_timestamp(sources["master_cycle"]["latest"]) else None
        ),
'''
if text.count(anchor) != 1:
    raise RuntimeError("master_cycle_timestamp audit anchor not found")

text = text.replace(
    anchor,
    anchor + '''        "activation_semantically_active": (
            active(sources["activation"]["latest"])
            and not blocked(sources["activation"]["latest"])
        ),
        "master_newer_than_runtime": (
            canonical_timestamp(sources["master_cycle"]["latest"]) is not None
            and canonical_timestamp(sources["runtime"]["latest"]) is not None
            and canonical_timestamp(sources["master_cycle"]["latest"])
                > canonical_timestamp(sources["runtime"]["latest"])
        ),
''',
    1,
)

clean = "\n".join(line.rstrip(" \t") for line in text.splitlines()) + "\n"
path.write_text(clean, encoding="utf-8", newline="\n")

print("[patched]", path)
print("[contract] SUSPENDED reconciles only when master cycle is newer than runtime")
print("[contract] activation must remain active and non-blocking")
print("[contract] no persistence mutation")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[2/7] Backup created: $BackupFile"
    Write-Host "[3/7] Applying activation supersession bridge patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying bridge/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw
    foreach ($Token in @(
        "PHASE371813_RUNTIME_SUPERVISION_SUSPENDED_ACTIVATION_SUPERSESSION_BRIDGE_FIX",
        "SUSPENDED_SUPERSEDED_BY_NEWER_ACTIVATION_AND_MASTER",
        "SUSPENDED_SUPERSEDED_BY_ACTIVE_ACTIVATION_AND_NEWER_MASTER_BRIDGE",
        "SUSPENDED_RUNTIME_TIMESTAMP_MISSING",
        "SUSPENDED_MASTER_TIMESTAMP_MISSING",
        "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE",
        "SUSPENDED_MASTER_CYCLE_BLOCKED",
        "SUSPENDED_NOT_SUPERSEDED_BY_MASTER",
        "PHASE371813_SUSPENDED_ACTIVATION_SUPERSESSION_BRIDGE",
        "activation_semantically_active",
        "master_newer_than_runtime",
        "BROKER_ORDER_SUBMISSION_ENABLED = False",
        "REAL_MONEY_TRADING_ENABLED = False",
        "HISTORICAL_REWRITE_ALLOWED = False"
    )) {
        if ($After -notmatch [regex]::Escape($Token)) {
            throw "Verification failed; missing token: $Token"
        }
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
    Write-Host " Phase 3.7.18.13 PATCH APPLIED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host "Backup: $BackupDir"
    Write-Host ""
    Write-Host "Supabase mutation                : NO"
    Write-Host "Qualification counter mutation   : NO"
    Write-Host "Synthetic qualification          : NO"
    Write-Host "Production schedule mutation     : NO"
    Write-Host "Broker order enablement          : NO"
    Write-Host "Real-money enablement            : NO"
    Write-Host "Historical evidence rewrite      : NO"
    Write-Host "Current/ambiguous SUSPENDED      : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
