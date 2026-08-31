#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.18 Deployment"
Write-Host " Normalized Master Cycle Business-Date"
Write-Host " vs Runtime Event-Date Reconciliation Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371818-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371818_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371818_RUNTIME_SUPERVISION_NORMALIZED_MASTER_CYCLE_BUSINESS_DATE_RUNTIME_EVENT_DATE_RECONCILIATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371817_RUNTIME_SUPERVISION_CROSS_SOURCE_CANONICAL_EVENT_TIME_SEMANTIC_NORMALIZATION_FIX",
    "semantically_comparable_supersession",
    "MASTER_CYCLE_DATE_BEFORE_RUNTIME_DATE",
    "SAME_DAY_CROSS_SEMANTIC_AMBIGUOUS",
    "PHASE371817_CROSS_SOURCE_EVENT_TIME_SEMANTIC_NORMALIZATION",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.17 token missing: {token}")

pattern = re.compile(
    r'def semantically_comparable_supersession\(runtime_row: Dict\[str, Any\], master_row: Dict\[str, Any\]\):\n'
    r'.*?'
    r'(?=\ndef suspended_is_superseded\()',
    re.S,
)
m = pattern.search(text)
if not m:
    raise RuntimeError("Phase 3.7.18.17 semantic comparison function not found")

new_func = '''# PHASE371818_RUNTIME_SUPERVISION_NORMALIZED_MASTER_CYCLE_BUSINESS_DATE_RUNTIME_EVENT_DATE_RECONCILIATION_FIX
def canonical_business_date(row: Dict[str, Any]):
    if not row:
        return None, None

    lower = {str(k).lower(): v for k, v in row.items()}
    for name in ("cycle_date", "run_date", "trade_date", "date"):
        raw = text(lower.get(name))
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw[:10]).date(), name
        except Exception:
            continue

    dt, source, _ = canonical_event_timestamp_with_provenance(row)
    if dt is not None:
        return dt.date(), source

    return None, None

def semantically_comparable_supersession(runtime_row: Dict[str, Any], master_row: Dict[str, Any]):
    runtime_dt, runtime_src, runtime_sem = canonical_semantic_event_time(runtime_row)
    master_dt, master_src, master_sem = canonical_semantic_event_time(master_row)

    runtime_business_date, runtime_business_src = canonical_business_date(runtime_row)
    master_business_date, master_business_src = canonical_business_date(master_row)

    if runtime_dt is None and runtime_business_date is None:
        return False, "RUNTIME_EVENT_AND_BUSINESS_DATE_MISSING"

    if master_dt is None and master_business_date is None:
        return False, "MASTER_EVENT_AND_BUSINESS_DATE_MISSING"

    if runtime_sem == "unknown" or master_sem == "unknown":
        return False, (
            f"UNKNOWN_EVENT_TIME_SEMANTICS:"
            f"runtime={runtime_src},master={master_src}"
        )

    if runtime_sem == master_sem and runtime_dt is not None and master_dt is not None:
        return (
            master_dt > runtime_dt,
            f"SAME_SEMANTIC_CLASS:{runtime_sem}:runtime={runtime_src},master={master_src}"
        )

    if master_sem == "cycle_date" and runtime_sem in {"event", "lifecycle"}:
        if master_business_date is None or runtime_business_date is None:
            return False, (
                f"CROSS_SOURCE_BUSINESS_DATE_MISSING:"
                f"runtime={runtime_business_src},master={master_business_src}"
            )

        if master_business_date > runtime_business_date:
            return True, (
                f"MASTER_BUSINESS_DATE_AFTER_RUNTIME_EVENT_DATE:"
                f"runtime={runtime_src}/{runtime_business_date},"
                f"master={master_src}/{master_business_date}"
            )

        if master_business_date == runtime_business_date:
            return False, (
                f"SAME_BUSINESS_DATE_CROSS_SEMANTIC_AMBIGUOUS:"
                f"runtime={runtime_src}/{runtime_business_date},"
                f"master={master_src}/{master_business_date}"
            )

        return False, (
            f"MASTER_BUSINESS_DATE_BEFORE_RUNTIME_EVENT_DATE:"
            f"runtime={runtime_src}/{runtime_business_date},"
            f"master={master_src}/{master_business_date}"
        )

    if runtime_sem == "cycle_date" and master_sem in {"event", "lifecycle"}:
        if runtime_business_date is None or master_business_date is None:
            return False, "CROSS_SOURCE_BUSINESS_DATE_MISSING"
        return (
            master_business_date > runtime_business_date,
            (
                f"MASTER_EVENT_DATE_VS_RUNTIME_BUSINESS_DATE:"
                f"runtime={runtime_src}/{runtime_business_date},"
                f"master={master_src}/{master_business_date}"
            ),
        )

    if {runtime_sem, master_sem} <= {"event", "lifecycle"}:
        if runtime_dt is None or master_dt is None:
            return False, "PRECISE_CROSS_SEMANTIC_TIMESTAMP_MISSING"
        return (
            master_dt > runtime_dt,
            f"PRECISE_CROSS_SEMANTIC:runtime={runtime_src},master={master_src}"
        )

    return False, (
        f"UNSAFE_CROSS_SOURCE_EVENT_TIME_SEMANTICS:"
        f"runtime={runtime_src}/{runtime_sem},master={master_src}/{master_sem}"
    )

'''
text = text[:m.start()] + new_func + text[m.end():]

old_label = '"compatibility_contract": "PHASE371817_CROSS_SOURCE_EVENT_TIME_SEMANTIC_NORMALIZATION",'
if text.count(old_label) != 1:
    raise RuntimeError("Phase 3.7.18.17 compatibility label mismatch")
text = text.replace(
    old_label,
    '"compatibility_contract": "PHASE371818_BUSINESS_DATE_RUNTIME_EVENT_DATE_RECONCILIATION",',
    1,
)

audit_anchor = '        "cross_source_event_time_contract": "PHASE371817",\n'
if text.count(audit_anchor) != 1:
    raise RuntimeError("Phase 3.7.18.17 audit anchor not found")

audit = '''        "runtime_business_date": (
            canonical_business_date(sources["runtime"]["latest"])[0].isoformat()
            if canonical_business_date(sources["runtime"]["latest"])[0] else None
        ),
        "runtime_business_date_provenance": canonical_business_date(
            sources["runtime"]["latest"]
        )[1],
        "master_cycle_business_date": (
            canonical_business_date(sources["master_cycle"]["latest"])[0].isoformat()
            if canonical_business_date(sources["master_cycle"]["latest"])[0] else None
        ),
        "master_cycle_business_date_provenance": canonical_business_date(
            sources["master_cycle"]["latest"]
        )[1],
        "business_date_event_date_contract": "PHASE371818",
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
print("[contract] business-date vs runtime-event-date reconciliation installed")
print("[contract] same-date ambiguity remains fail-closed")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[3/7] Applying business-date/runtime-event-date reconciliation patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying chronology/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE371818_RUNTIME_SUPERVISION_NORMALIZED_MASTER_CYCLE_BUSINESS_DATE_RUNTIME_EVENT_DATE_RECONCILIATION_FIX",
        "canonical_business_date",
        "MASTER_BUSINESS_DATE_AFTER_RUNTIME_EVENT_DATE",
        "MASTER_BUSINESS_DATE_BEFORE_RUNTIME_EVENT_DATE",
        "SAME_BUSINESS_DATE_CROSS_SEMANTIC_AMBIGUOUS",
        "PHASE371818_BUSINESS_DATE_RUNTIME_EVENT_DATE_RECONCILIATION",
        "runtime_business_date",
        "master_cycle_business_date",
        "business_date_event_date_contract",
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
    Write-Host " Phase 3.7.18.18 PATCH APPLIED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host "Backup: $BackupDir"
    Write-Host ""
    Write-Host "Supabase mutation                 : NO"
    Write-Host "Qualification counter mutation    : NO"
    Write-Host "Synthetic qualification           : NO"
    Write-Host "Production schedule mutation      : NO"
    Write-Host "Broker order enablement           : NO"
    Write-Host "Real-money enablement             : NO"
    Write-Host "Historical evidence rewrite       : NO"
    Write-Host "Ambiguous business-date chronology: FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
