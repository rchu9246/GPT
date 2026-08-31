#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.12 Deployment"
Write-Host " Runtime Supervision Suspended Canonical State Reconciliation Fix"
Write-Host "============================================================"
Write-Host ""

$RepoRoot = (Get-Location).Path
$TargetRel = "automation\v92\paper_trading_phase374_production_paper_daily_cycle_monitoring_evidence_accumulation.py"
$Target = Join-Path $RepoRoot $TargetRel

if (-not (Test-Path -LiteralPath $Target)) { throw "Required Phase 3.7.4 target not found: $TargetRel" }

$PythonMode = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { throw "Python not found in PATH." }

Write-Host "[1/7] Preflight compile..."
if ($PythonMode -eq "py") { & py -3 -m py_compile $Target } else { & python -m py_compile $Target }
if ($LASTEXITCODE -ne 0) { throw "Preflight py_compile failed." }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $RepoRoot ".phase371812-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force

$PatchPy = Join-Path $env:TEMP "phase371812_patch_$Stamp.py"
$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
MARKER = "PHASE371812_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_STATE_RECONCILIATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "def runtime_supervision_ready(",
    'runtime_ok, runtime_state = runtime_supervision_ready(sources["runtime"]["latest"])',
    'if not runtime_ok: blockers.append(f"RUNTIME_SUPERVISION_NOT_READY:{runtime_state}")',
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.4 token missing: {token}")

anchor = "def runtime_supervision_ready(row: Dict[str, Any]) -> Tuple[bool, str]:\n"
if text.count(anchor) != 1:
    raise RuntimeError("runtime_supervision_ready anchor mismatch")

helpers = '''# PHASE371812_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_STATE_RECONCILIATION_FIX
def canonical_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    if not row:
        return None
    lower = {str(k).lower(): v for k, v in row.items()}
    for name in (
        "updated_at","created_at","run_at","observed_at","validated_at",
        "cycle_at","cycle_date","run_date","trade_date","date",
    ):
        raw = text(lower.get(name))
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            try:
                dt = datetime.fromisoformat(raw[:10])
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None

def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    runtime_ts = canonical_timestamp(runtime_row)
    activation_ts = canonical_timestamp(activation_row)
    master_ts = canonical_timestamp(master_row)

    if runtime_ts is None:
        return False, "SUSPENDED_RUNTIME_TIMESTAMP_MISSING"
    if activation_ts is None:
        return False, "SUSPENDED_ACTIVATION_TIMESTAMP_MISSING"
    if master_ts is None:
        return False, "SUSPENDED_MASTER_TIMESTAMP_MISSING"
    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"
    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"
    if activation_ts <= runtime_ts:
        return False, "SUSPENDED_NOT_SUPERSEDED_BY_ACTIVATION"
    if master_ts <= runtime_ts:
        return False, "SUSPENDED_NOT_SUPERSEDED_BY_MASTER"

    return True, "SUSPENDED_STALE_SUPERSEDED_BY_NEWER_CANONICAL_LIFECYCLE"

'''
text = text.replace(anchor, helpers + anchor, 1)

pattern = re.compile(
    r'def runtime_supervision_ready\(row: Dict\[str, Any\]\) -> Tuple\[bool, str\]:\n.*?(?=\ndef main\(\) -> int:)',
    re.S,
)
m = pattern.search(text)
if not m:
    raise RuntimeError("runtime_supervision_ready function block not found")

new_func = '''def runtime_supervision_ready(
    row: Dict[str, Any],
    activation_row: Optional[Dict[str, Any]] = None,
    master_row: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    if not row:
        return False, "MISSING"

    state = field_state(
        row,
        ("supervision_state", "runtime_supervision", "runtime_supervision_state", "state", "status"),
    )

    hard_block_states = {"REVOKED","FAIL_CLOSED","BLOCKED","HALTED","ERROR","FAILED"}
    ready_states = {
        "CONTINUE_ACTIVE","CONTINUE_WITH_OBSERVATION","ACTIVE","ENABLED",
        "READY","PASS","AUTHORIZED_PAPER_CONTINUATION",
    }

    if state in hard_block_states:
        return False, state

    if state == "SUSPENDED":
        ok, reason = suspended_is_superseded(
            row,
            activation_row or {},
            master_row or {},
        )
        return ok, reason

    if state in ready_states:
        return True, state

    if not blocked(row):
        return True, state or "PRESENT_NON_BLOCKING"

    return False, state or "BLOCKED"
'''
text = text[:m.start()] + new_func + text[m.end():]

old_call = '    runtime_ok, runtime_state = runtime_supervision_ready(sources["runtime"]["latest"])\n'
if text.count(old_call) != 1:
    raise RuntimeError("runtime supervision call anchor mismatch")
text = text.replace(
    old_call,
    '''    runtime_ok, runtime_state = runtime_supervision_ready(
        sources["runtime"]["latest"],
        sources["activation"]["latest"],
        sources["master_cycle"]["latest"],
    )
''',
    1,
)

old_resolution = '''    result["runtime_supervision_resolution"] = {
        "table": sources["runtime"]["table"],
        "state": runtime_state,
        "ready": runtime_ok,
        "compatibility_contract": "PHASE367_PHASE3727_CANONICAL",
    }
'''
if text.count(old_resolution) != 1:
    raise RuntimeError("runtime supervision resolution block mismatch")

new_resolution = '''    result["runtime_supervision_resolution"] = {
        "table": sources["runtime"]["table"],
        "state": runtime_state,
        "ready": runtime_ok,
        "compatibility_contract": "PHASE371812_SUSPENDED_CANONICAL_RECONCILIATION",
        "runtime_timestamp": (
            canonical_timestamp(sources["runtime"]["latest"]).isoformat()
            if canonical_timestamp(sources["runtime"]["latest"]) else None
        ),
        "activation_timestamp": (
            canonical_timestamp(sources["activation"]["latest"]).isoformat()
            if canonical_timestamp(sources["activation"]["latest"]) else None
        ),
        "master_cycle_timestamp": (
            canonical_timestamp(sources["master_cycle"]["latest"]).isoformat()
            if canonical_timestamp(sources["master_cycle"]["latest"]) else None
        ),
    }
'''
text = text.replace(old_resolution, new_resolution, 1)

clean = "\n".join(line.rstrip(" \t") for line in text.splitlines()) + "\n"
path.write_text(clean, encoding="utf-8", newline="\n")

print("[patched]", path)
print("[contract] SUSPENDED reconciles only when newer canonical lifecycle evidence supersedes it")
print("[contract] missing or ambiguous chronology remains fail-closed")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[2/7] Backup created: $BackupFile"
    Write-Host "[3/7] Applying patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying contract..."
    $After = Get-Content -LiteralPath $Target -Raw
    foreach ($Token in @(
        "PHASE371812_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_STATE_RECONCILIATION_FIX",
        "def canonical_timestamp",
        "def suspended_is_superseded",
        "SUSPENDED_RUNTIME_TIMESTAMP_MISSING",
        "SUSPENDED_NOT_SUPERSEDED_BY_ACTIVATION",
        "SUSPENDED_NOT_SUPERSEDED_BY_MASTER",
        "SUSPENDED_STALE_SUPERSEDED_BY_NEWER_CANONICAL_LIFECYCLE",
        "PHASE371812_SUSPENDED_CANONICAL_RECONCILIATION",
        "BROKER_ORDER_SUBMISSION_ENABLED = False",
        "REAL_MONEY_TRADING_ENABLED = False",
        "HISTORICAL_REWRITE_ALLOWED = False"
    )) {
        if ($After -notmatch [regex]::Escape($Token)) { throw "Verification failed; missing token: $Token" }
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
    Write-Host " Phase 3.7.18.12 PATCH APPLIED AND VERIFIED"
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
    Write-Host "Ambiguous SUSPENDED data         : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
