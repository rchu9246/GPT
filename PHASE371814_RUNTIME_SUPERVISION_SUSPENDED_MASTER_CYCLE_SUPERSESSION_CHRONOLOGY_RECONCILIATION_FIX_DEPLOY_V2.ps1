#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.14 V2 Deployment"
Write-Host " Runtime Supervision Suspended Master Cycle"
Write-Host " Supersession Chronology Reconciliation Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371814-v2-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371814_v2_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371814_RUNTIME_SUPERVISION_SUSPENDED_MASTER_CYCLE_SUPERSESSION_CHRONOLOGY_RECONCILIATION_FIX_V2"

if MARKER in text:
    print("[already fixed] V2 marker present")
    raise SystemExit(0)

required = [
    "PHASE371813_SUSPENDED_ACTIVATION_SUPERSESSION_BRIDGE",
    "def suspended_is_superseded(",
    '"master_newer_than_runtime": (',
    '"activation_semantically_active": (',
    '"runtime_timestamp": (',
    '"master_cycle_timestamp": (',
    "SUSPENDED_NOT_SUPERSEDED_BY_MASTER",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.13 token missing: {token}")

pattern = re.compile(
    r'def suspended_is_superseded\(\n'
    r'    runtime_row: Dict\[str, Any\],\n'
    r'    activation_row: Dict\[str, Any\],\n'
    r'    master_row: Dict\[str, Any\],\n'
    r'\) -> Tuple\[bool, str\]:\n'
    r'.*?'
    r'(?=\ndef runtime_supervision_ready\()',
    re.S,
)

m = pattern.search(text)
if not m:
    raise RuntimeError(
        "Actual Phase 3.7.18.13 suspended_is_superseded function not found; "
        "refusing ambiguous modification."
    )

new_func = '''def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    # PHASE371814_RUNTIME_SUPERVISION_SUSPENDED_MASTER_CYCLE_SUPERSESSION_CHRONOLOGY_RECONCILIATION_FIX_V2
    runtime_ts = canonical_timestamp(runtime_row)
    activation_ts = canonical_timestamp(activation_row)
    master_ts = canonical_timestamp(master_row)

    if runtime_ts is None:
        return False, "SUSPENDED_RUNTIME_TIMESTAMP_MISSING"

    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    if master_ts is not None and master_ts > runtime_ts:
        if activation_ts is not None and activation_ts > runtime_ts:
            return True, "SUSPENDED_SUPERSEDED_BY_NEWER_ACTIVATION_AND_MASTER"
        return True, "SUSPENDED_SUPERSEDED_BY_ACTIVE_ACTIVATION_AND_NEWER_MASTER"

    if activation_ts is not None and activation_ts > runtime_ts:
        return True, "SUSPENDED_MASTER_CHRONOLOGY_RECONCILED_BY_NEWER_ACTIVE_ACTIVATION"

    if master_ts is None:
        return False, "SUSPENDED_MASTER_TIMESTAMP_MISSING"

    return False, "SUSPENDED_NOT_SUPERSEDED_BY_MASTER"
'''

text = text[:m.start()] + new_func + text[m.end():]

old_label = '"compatibility_contract": "PHASE371813_SUSPENDED_ACTIVATION_SUPERSESSION_BRIDGE",'
if text.count(old_label) != 1:
    raise RuntimeError(
        f"Expected exactly one Phase 3.7.18.13 compatibility label, found {text.count(old_label)}"
    )

text = text.replace(
    old_label,
    '"compatibility_contract": "PHASE371814_V2_MASTER_CYCLE_CHRONOLOGY_RECONCILIATION",',
    1,
)

lines = text.splitlines()
start = None
end = None

for i, line in enumerate(lines):
    if '"master_newer_than_runtime": (' in line:
        start = i
        depth = 0
        for j in range(i, min(len(lines), i + 20)):
            depth += lines[j].count("(") - lines[j].count(")")
            if j > i and depth <= 0 and lines[j].strip().endswith("),"):
                end = j
                break
        break

if start is None or end is None:
    raise RuntimeError("master_newer_than_runtime audit block could not be located structurally")

indent = re.match(r'^(\s*)', lines[start]).group(1)
lines[end+1:end+1] = [
    indent + '"master_chronology_reconciliation_contract": "PHASE371814_V2",',
    indent + '"master_chronology_fail_closed": True,',
]

text = "\n".join(lines) + "\n"

for hard in ("REVOKED", "FAIL_CLOSED", "BLOCKED", "HALTED", "ERROR", "FAILED"):
    if f'"{hard}"' not in text:
        raise RuntimeError(f"Hard safety state missing after patch: {hard}")

for forbidden in (
    "BROKER_ORDER_SUBMISSION_ENABLED = True",
    "REAL_MONEY_TRADING_ENABLED = True",
    "HISTORICAL_REWRITE_ALLOWED = True",
):
    if forbidden in text:
        raise RuntimeError(f"Forbidden safety mutation detected: {forbidden}")

clean = "\n".join(line.rstrip(" \t") for line in text.splitlines()) + "\n"
path.write_text(clean, encoding="utf-8", newline="\n")

print("[patched]", path)
print("[contract] structural V2 patch applied")
print("[contract] master chronology can reconcile through newer active activation")
print("[contract] ambiguous chronology remains fail-closed")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
    Write-Host "  restored: $TargetRel"
}

try {
    Write-Host "[3/7] Applying V2 structural chronology patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying reconciliation contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE371814_RUNTIME_SUPERVISION_SUSPENDED_MASTER_CYCLE_SUPERSESSION_CHRONOLOGY_RECONCILIATION_FIX_V2",
        "PHASE371814_V2_MASTER_CYCLE_CHRONOLOGY_RECONCILIATION",
        "SUSPENDED_MASTER_CHRONOLOGY_RECONCILED_BY_NEWER_ACTIVE_ACTIVATION",
        "SUSPENDED_NOT_SUPERSEDED_BY_MASTER",
        "SUSPENDED_MASTER_TIMESTAMP_MISSING",
        "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE",
        "master_chronology_reconciliation_contract",
        "master_chronology_fail_closed",
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
    Write-Host " Phase 3.7.18.14 V2 PATCH APPLIED AND VERIFIED"
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
    Write-Host "Ambiguous chronology             : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
