#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.16 Deployment"
Write-Host " Runtime Supervision Suspended Canonical Event"
Write-Host " Chronology Reconciliation Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371816-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371816_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371816_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371815_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_TIMESTAMP_PROVENANCE_RECONCILIATION_FIX",
    "canonical_timestamp_with_provenance",
    "PHASE371815_TIMESTAMP_PROVENANCE_RECONCILIATION",
    "SUSPENDED_NOT_SUPERSEDED_BY_MASTER",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.15 token missing: {token}")

anchor = """def canonical_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    dt, _, _ = canonical_timestamp_with_provenance(row)
    return dt
"""
if text.count(anchor) != 1:
    raise RuntimeError("canonical_timestamp anchor not found exactly once")

event_helpers = """
# PHASE371816_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION_FIX
CANONICAL_EVENT_TIMESTAMP_PRIORITY = (
    "observed_at",
    "validated_at",
    "run_at",
    "cycle_at",
    "cycle_date",
    "run_date",
    "trade_date",
    "date",
    "updated_at",
    "created_at",
)

def canonical_event_timestamp_with_provenance(row: Dict[str, Any]):
    if not row:
        return None, None, None

    lower = {str(k).lower(): v for k, v in row.items()}

    for name in CANONICAL_EVENT_TIMESTAMP_PRIORITY:
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

def canonical_event_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    dt, _, _ = canonical_event_timestamp_with_provenance(row)
    return dt
"""
text = text.replace(anchor, anchor + event_helpers, 1)

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
    raise RuntimeError("suspended_is_superseded function block not found")

new_supersession = """def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    runtime_ts, runtime_src, _ = canonical_timestamp_with_provenance(runtime_row)
    activation_ts, activation_src, _ = canonical_timestamp_with_provenance(activation_row)
    master_ts, master_src, _ = canonical_timestamp_with_provenance(master_row)

    runtime_event_ts, runtime_event_src, _ = canonical_event_timestamp_with_provenance(runtime_row)
    activation_event_ts, activation_event_src, _ = canonical_event_timestamp_with_provenance(activation_row)
    master_event_ts, master_event_src, _ = canonical_event_timestamp_with_provenance(master_row)

    if runtime_ts is None and runtime_event_ts is None:
        return False, "SUSPENDED_RUNTIME_CHRONOLOGY_MISSING"

    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    if runtime_event_ts is not None and master_event_ts is not None:
        if master_event_ts > runtime_event_ts:
            return True, (
                f"SUSPENDED_SUPERSEDED_BY_MASTER_EVENT:"
                f"runtime={runtime_event_src},master={master_event_src}"
            )

        if (
            activation_event_ts is not None
            and activation_event_ts > runtime_event_ts
            and master_event_ts >= runtime_event_ts
        ):
            return True, (
                f"SUSPENDED_EVENT_CHRONOLOGY_RECONCILED:"
                f"activation={activation_event_src},master={master_event_src}"
            )

        return False, (
            f"SUSPENDED_NOT_SUPERSEDED_BY_MASTER_EVENT:"
            f"runtime_source={runtime_event_src},master_source={master_event_src}"
        )

    strong_sources = {
        "updated_at",
        "observed_at",
        "validated_at",
        "run_at",
        "cycle_at",
        "created_at",
    }

    if master_ts is not None and runtime_ts is not None:
        if master_ts > runtime_ts and master_src in strong_sources:
            return True, f"SUSPENDED_SUPERSEDED_BY_MASTER_TIMESTAMP:{master_src}"

    if (
        activation_ts is not None
        and runtime_ts is not None
        and activation_ts > runtime_ts
        and activation_src in strong_sources
        and master_ts is not None
        and master_ts >= runtime_ts
    ):
        return True, (
            f"SUSPENDED_TIMESTAMP_PROVENANCE_RECONCILED:"
            f"activation={activation_src},master={master_src}"
        )

    if master_ts is None and master_event_ts is None:
        return False, "SUSPENDED_MASTER_CHRONOLOGY_MISSING"

    return False, (
        f"SUSPENDED_NOT_SUPERSEDED_BY_MASTER:"
        f"runtime_source={runtime_src},master_source={master_src}"
    )
"""
text = text[:m.start()] + new_supersession + text[m.end():]

old_label = '"compatibility_contract": "PHASE371815_TIMESTAMP_PROVENANCE_RECONCILIATION",'
if text.count(old_label) != 1:
    raise RuntimeError(
        f"Expected one Phase 3.7.18.15 compatibility label, found {text.count(old_label)}"
    )
text = text.replace(
    old_label,
    '"compatibility_contract": "PHASE371816_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION",',
    1,
)

audit_anchor = '        "timestamp_provenance_contract": "PHASE371815",\n'
if text.count(audit_anchor) != 1:
    raise RuntimeError("timestamp provenance audit anchor not found")

audit = """        "runtime_event_timestamp": (
            canonical_event_timestamp(sources["runtime"]["latest"]).isoformat()
            if canonical_event_timestamp(sources["runtime"]["latest"]) else None
        ),
        "activation_event_timestamp": (
            canonical_event_timestamp(sources["activation"]["latest"]).isoformat()
            if canonical_event_timestamp(sources["activation"]["latest"]) else None
        ),
        "master_cycle_event_timestamp": (
            canonical_event_timestamp(sources["master_cycle"]["latest"]).isoformat()
            if canonical_event_timestamp(sources["master_cycle"]["latest"]) else None
        ),
        "runtime_event_timestamp_provenance": canonical_event_timestamp_with_provenance(
            sources["runtime"]["latest"]
        )[1],
        "activation_event_timestamp_provenance": canonical_event_timestamp_with_provenance(
            sources["activation"]["latest"]
        )[1],
        "master_cycle_event_timestamp_provenance": canonical_event_timestamp_with_provenance(
            sources["master_cycle"]["latest"]
        )[1],
        "event_chronology_contract": "PHASE371816",
"""
text = text.replace(audit_anchor, audit_anchor + audit, 1)

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
print("[contract] canonical event chronology resolver installed")
print("[contract] ambiguous event chronology remains fail-closed")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[3/7] Applying canonical event chronology reconciliation patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying event chronology/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE371816_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION_FIX",
        "CANONICAL_EVENT_TIMESTAMP_PRIORITY",
        "canonical_event_timestamp_with_provenance",
        "PHASE371816_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION",
        "runtime_event_timestamp",
        "activation_event_timestamp",
        "master_cycle_event_timestamp",
        "runtime_event_timestamp_provenance",
        "activation_event_timestamp_provenance",
        "master_cycle_event_timestamp_provenance",
        "event_chronology_contract",
        "SUSPENDED_NOT_SUPERSEDED_BY_MASTER_EVENT",
        "SUSPENDED_SUPERSEDED_BY_MASTER_EVENT",
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
    Write-Host " Phase 3.7.18.16 PATCH APPLIED AND VERIFIED"
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
    Write-Host "Ambiguous event chronology       : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
