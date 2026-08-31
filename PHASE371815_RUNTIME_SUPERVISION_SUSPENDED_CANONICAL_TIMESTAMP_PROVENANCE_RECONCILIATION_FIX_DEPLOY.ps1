#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.15 Deployment"
Write-Host " Runtime Supervision Suspended Canonical Timestamp"
Write-Host " Provenance Reconciliation Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371815-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371815_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371815_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_TIMESTAMP_PROVENANCE_RECONCILIATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371814_RUNTIME_SUPERVISION_SUSPENDED_MASTER_CYCLE_SUPERSESSION_CHRONOLOGY_RECONCILIATION_FIX_V2",
    "def canonical_timestamp(",
    "def suspended_is_superseded(",
    "PHASE371814_V2_MASTER_CYCLE_CHRONOLOGY_RECONCILIATION",
    "SUSPENDED_NOT_SUPERSEDED_BY_MASTER",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.14 V2 token missing: {token}")

pat_ts = re.compile(
    r'def canonical_timestamp\(row: Dict\[str, Any\]\) -> Optional\[datetime\]:\n.*?(?=\ndef suspended_is_superseded\()',
    re.S,
)
m = pat_ts.search(text)
if not m:
    raise RuntimeError("canonical_timestamp function block not found")

new_ts = '''# PHASE371815_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_TIMESTAMP_PROVENANCE_RECONCILIATION_FIX
CANONICAL_TIMESTAMP_PRIORITY = (
    "updated_at",
    "observed_at",
    "validated_at",
    "run_at",
    "cycle_at",
    "created_at",
    "cycle_date",
    "run_date",
    "trade_date",
    "date",
)

def canonical_timestamp_with_provenance(row: Dict[str, Any]):
    if not row:
        return None, None, None

    lower = {str(k).lower(): v for k, v in row.items()}

    for name in CANONICAL_TIMESTAMP_PRIORITY:
        raw = text(lower.get(name))
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc), name, raw
        except Exception:
            try:
                dt = datetime.fromisoformat(raw[:10])
                return dt.replace(tzinfo=timezone.utc), name, raw
            except Exception:
                continue

    return None, None, None

def canonical_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    dt, _, _ = canonical_timestamp_with_provenance(row)
    return dt
'''
text = text[:m.start()] + new_ts + text[m.end():]

pat_sup = re.compile(
    r'def suspended_is_superseded\(\n'
    r'    runtime_row: Dict\[str, Any\],\n'
    r'    activation_row: Dict\[str, Any\],\n'
    r'    master_row: Dict\[str, Any\],\n'
    r'\) -> Tuple\[bool, str\]:\n.*?(?=\ndef runtime_supervision_ready\()',
    re.S,
)
m = pat_sup.search(text)
if not m:
    raise RuntimeError("suspended_is_superseded block not found")

new_sup = '''def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    runtime_ts, runtime_src, _ = canonical_timestamp_with_provenance(runtime_row)
    activation_ts, activation_src, _ = canonical_timestamp_with_provenance(activation_row)
    master_ts, master_src, _ = canonical_timestamp_with_provenance(master_row)

    if runtime_ts is None:
        return False, "SUSPENDED_RUNTIME_TIMESTAMP_PROVENANCE_MISSING"

    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    strong_sources = {
        "updated_at",
        "observed_at",
        "validated_at",
        "run_at",
        "cycle_at",
        "created_at",
    }

    if master_ts is not None and master_ts > runtime_ts and master_src in strong_sources:
        return True, f"SUSPENDED_SUPERSEDED_BY_MASTER:{master_src}"

    if (
        activation_ts is not None
        and activation_ts > runtime_ts
        and activation_src in strong_sources
        and master_ts is not None
        and master_ts >= runtime_ts
    ):
        return True, (
            f"SUSPENDED_MASTER_PROVENANCE_RECONCILED:"
            f"activation={activation_src},master={master_src}"
        )

    if master_ts is None:
        return False, "SUSPENDED_MASTER_TIMESTAMP_PROVENANCE_MISSING"

    return False, (
        f"SUSPENDED_NOT_SUPERSEDED_BY_MASTER:"
        f"runtime_source={runtime_src},master_source={master_src}"
    )
'''
text = text[:m.start()] + new_sup + text[m.end():]

old_label = '"compatibility_contract": "PHASE371814_V2_MASTER_CYCLE_CHRONOLOGY_RECONCILIATION",'
if text.count(old_label) != 1:
    raise RuntimeError("Phase 3.7.18.14 V2 compatibility label mismatch")
text = text.replace(
    old_label,
    '"compatibility_contract": "PHASE371815_TIMESTAMP_PROVENANCE_RECONCILIATION",',
    1,
)

anchor = '''        "master_cycle_timestamp": (
            canonical_timestamp(sources["master_cycle"]["latest"]).isoformat()
            if canonical_timestamp(sources["master_cycle"]["latest"]) else None
        ),
'''
if text.count(anchor) != 1:
    raise RuntimeError("master_cycle_timestamp audit anchor not found")

audit = '''        "runtime_timestamp_provenance": canonical_timestamp_with_provenance(
            sources["runtime"]["latest"]
        )[1],
        "activation_timestamp_provenance": canonical_timestamp_with_provenance(
            sources["activation"]["latest"]
        )[1],
        "master_cycle_timestamp_provenance": canonical_timestamp_with_provenance(
            sources["master_cycle"]["latest"]
        )[1],
        "timestamp_provenance_contract": "PHASE371815",
'''
text = text.replace(anchor, anchor + audit, 1)

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
print("[contract] timestamp provenance resolver installed")
print("[contract] ambiguous provenance remains fail-closed")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[3/7] Applying timestamp provenance reconciliation patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying provenance/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE371815_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_TIMESTAMP_PROVENANCE_RECONCILIATION_FIX",
        "CANONICAL_TIMESTAMP_PRIORITY",
        "canonical_timestamp_with_provenance",
        "PHASE371815_TIMESTAMP_PROVENANCE_RECONCILIATION",
        "runtime_timestamp_provenance",
        "activation_timestamp_provenance",
        "master_cycle_timestamp_provenance",
        "timestamp_provenance_contract",
        "SUSPENDED_RUNTIME_TIMESTAMP_PROVENANCE_MISSING",
        "SUSPENDED_MASTER_TIMESTAMP_PROVENANCE_MISSING",
        "SUSPENDED_NOT_SUPERSEDED_BY_MASTER",
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
    Write-Host " Phase 3.7.18.15 PATCH APPLIED AND VERIFIED"
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
    Write-Host "Unknown timestamp provenance     : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
