#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.17 Deployment"
Write-Host " Cross-Source Canonical Event-Time Semantic Normalization Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371817-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371817_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371817_RUNTIME_SUPERVISION_CROSS_SOURCE_CANONICAL_EVENT_TIME_SEMANTIC_NORMALIZATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371816_RUNTIME_SUPERVISION_SUSPENDED_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION_FIX",
    "canonical_event_timestamp_with_provenance",
    "PHASE371816_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION",
    "SUSPENDED_NOT_SUPERSEDED_BY_MASTER_EVENT",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.16 token missing: {token}")

anchor = "def suspended_is_superseded(\n"
if text.count(anchor) != 1:
    raise RuntimeError("suspended_is_superseded anchor not found exactly once")

helpers = '''# PHASE371817_RUNTIME_SUPERVISION_CROSS_SOURCE_CANONICAL_EVENT_TIME_SEMANTIC_NORMALIZATION_FIX
EVENT_TIME_SEMANTIC_CLASS = {
    "observed_at": "event",
    "validated_at": "event",
    "run_at": "event",
    "cycle_at": "event",
    "updated_at": "lifecycle",
    "created_at": "lifecycle",
    "cycle_date": "cycle_date",
    "run_date": "cycle_date",
    "trade_date": "cycle_date",
    "date": "cycle_date",
}

def timestamp_semantic_class(source: Optional[str]) -> str:
    if not source:
        return "unknown"
    return EVENT_TIME_SEMANTIC_CLASS.get(source, "unknown")

def normalize_cycle_date_boundary(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)

def canonical_semantic_event_time(row: Dict[str, Any]):
    dt, source, _ = canonical_event_timestamp_with_provenance(row)
    semantic = timestamp_semantic_class(source)
    if dt is None:
        return None, source, semantic
    if semantic == "cycle_date":
        dt = normalize_cycle_date_boundary(dt)
    return dt, source, semantic

def semantically_comparable_supersession(runtime_row: Dict[str, Any], master_row: Dict[str, Any]):
    runtime_dt, runtime_src, runtime_sem = canonical_semantic_event_time(runtime_row)
    master_dt, master_src, master_sem = canonical_semantic_event_time(master_row)

    if runtime_dt is None:
        return False, "RUNTIME_EVENT_TIME_MISSING"
    if master_dt is None:
        return False, "MASTER_EVENT_TIME_MISSING"
    if runtime_sem == "unknown" or master_sem == "unknown":
        return False, f"UNKNOWN_EVENT_TIME_SEMANTICS:runtime={runtime_src},master={master_src}"

    if runtime_sem == master_sem:
        return master_dt > runtime_dt, (
            f"SAME_SEMANTIC_CLASS:{runtime_sem}:runtime={runtime_src},master={master_src}"
        )

    if master_sem == "cycle_date" and runtime_sem in {"event", "lifecycle"}:
        if master_dt.date() > runtime_dt.date():
            return True, f"MASTER_CYCLE_DATE_AFTER_RUNTIME_DATE:runtime={runtime_src},master={master_src}"
        if master_dt.date() == runtime_dt.date():
            return False, f"SAME_DAY_CROSS_SEMANTIC_AMBIGUOUS:runtime={runtime_src},master={master_src}"
        return False, f"MASTER_CYCLE_DATE_BEFORE_RUNTIME_DATE:runtime={runtime_src},master={master_src}"

    if runtime_sem == "cycle_date" and master_sem in {"event", "lifecycle"}:
        return master_dt > runtime_dt, (
            f"MASTER_PRECISE_TIME_VS_RUNTIME_CYCLE_DATE:runtime={runtime_src},master={master_src}"
        )

    if {runtime_sem, master_sem} <= {"event", "lifecycle"}:
        return master_dt > runtime_dt, (
            f"PRECISE_CROSS_SEMANTIC:runtime={runtime_src},master={master_src}"
        )

    return False, (
        f"UNSAFE_CROSS_SOURCE_EVENT_TIME_SEMANTICS:"
        f"runtime={runtime_src}/{runtime_sem},master={master_src}/{master_sem}"
    )

'''
text = text.replace(anchor, helpers + anchor, 1)

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
    raise RuntimeError("Phase 3.7.18.16 suspended_is_superseded block not found")

new_sup = '''def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    comparable, reason = semantically_comparable_supersession(runtime_row, master_row)
    if comparable:
        return True, f"SUSPENDED_SUPERSEDED_BY_NORMALIZED_MASTER_EVENT:{reason}"

    activation_dt, activation_src, activation_sem = canonical_semantic_event_time(activation_row)
    runtime_dt, runtime_src, runtime_sem = canonical_semantic_event_time(runtime_row)
    master_dt, master_src, master_sem = canonical_semantic_event_time(master_row)

    if (
        activation_dt is not None
        and runtime_dt is not None
        and activation_sem in {"event", "lifecycle"}
        and runtime_sem in {"event", "lifecycle"}
        and activation_dt > runtime_dt
        and master_dt is not None
        and master_sem == "cycle_date"
        and master_dt.date() > runtime_dt.date()
    ):
        return True, (
            f"SUSPENDED_CROSS_SOURCE_SEMANTIC_RECONCILED:"
            f"runtime={runtime_src}/{runtime_sem},"
            f"activation={activation_src}/{activation_sem},"
            f"master={master_src}/{master_sem}"
        )

    return False, f"SUSPENDED_NOT_SUPERSEDED_BY_NORMALIZED_MASTER_EVENT:{reason}"
'''
text = text[:m.start()] + new_sup + text[m.end():]

old_label = '"compatibility_contract": "PHASE371816_CANONICAL_EVENT_CHRONOLOGY_RECONCILIATION",'
if text.count(old_label) != 1:
    raise RuntimeError("Phase 3.7.18.16 compatibility label mismatch")
text = text.replace(
    old_label,
    '"compatibility_contract": "PHASE371817_CROSS_SOURCE_EVENT_TIME_SEMANTIC_NORMALIZATION",',
    1,
)

audit_anchor = '        "event_chronology_contract": "PHASE371816",\n'
if text.count(audit_anchor) != 1:
    raise RuntimeError("event chronology audit anchor not found")

audit = '''        "runtime_event_time_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(sources["runtime"]["latest"])[1]
        ),
        "activation_event_time_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(sources["activation"]["latest"])[1]
        ),
        "master_cycle_event_time_semantic": timestamp_semantic_class(
            canonical_event_timestamp_with_provenance(sources["master_cycle"]["latest"])[1]
        ),
        "cross_source_event_time_contract": "PHASE371817",
'''
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
print("[contract] cross-source event-time semantic normalization installed")
print("[contract] updated_at vs run_date no longer treated as identical semantics")
print("[contract] ambiguous same-day cross-semantics remains fail-closed")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[3/7] Applying cross-source semantic normalization patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying semantic/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE371817_RUNTIME_SUPERVISION_CROSS_SOURCE_CANONICAL_EVENT_TIME_SEMANTIC_NORMALIZATION_FIX",
        "EVENT_TIME_SEMANTIC_CLASS",
        "timestamp_semantic_class",
        "canonical_semantic_event_time",
        "semantically_comparable_supersession",
        "PHASE371817_CROSS_SOURCE_EVENT_TIME_SEMANTIC_NORMALIZATION",
        "runtime_event_time_semantic",
        "activation_event_time_semantic",
        "master_cycle_event_time_semantic",
        "cross_source_event_time_contract",
        "SUSPENDED_NOT_SUPERSEDED_BY_NORMALIZED_MASTER_EVENT",
        "SUSPENDED_SUPERSEDED_BY_NORMALIZED_MASTER_EVENT",
        "SAME_DAY_CROSS_SEMANTIC_AMBIGUOUS",
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
    Write-Host " Phase 3.7.18.17 PATCH APPLIED AND VERIFIED"
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
    Write-Host "Unknown/cross-source semantics   : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
