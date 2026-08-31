#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.20 Deployment"
Write-Host " Master Business-Date / Runtime Event-Date"
Write-Host " Domain Separation Reconciliation Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371820-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371820_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371820_RUNTIME_SUPERVISION_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION_RECONCILIATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371819_RUNTIME_SUPERVISION_CROSS_DOMAIN_BUSINESS_DATE_EVENT_TIME_SUPERSESSION_RECONCILIATION_FIX",
    "cross_domain_supersession_evidence",
    "MASTER_BUSINESS_DATE_PRECEDES_RUNTIME_EVENT_DATE",
    "PHASE371819_CROSS_DOMAIN_BUSINESS_DATE_EVENT_TIME_RECONCILIATION",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.19 token missing: {token}")

# Add explicit domain separation helper before cross_domain_supersession_evidence().
anchor = "def cross_domain_supersession_evidence(\n"
if text.count(anchor) != 1:
    raise RuntimeError("Phase 3.7.18.19 cross-domain anchor not found exactly once")

helpers = '''# PHASE371820_RUNTIME_SUPERVISION_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION_RECONCILIATION_FIX
def chronology_domain(source: Optional[str]) -> str:
    semantic = timestamp_semantic_class(source)
    if semantic == "cycle_date":
        return "business_date"
    if semantic in {"event", "lifecycle"}:
        return "event_time"
    return "unknown"

def separated_domain_relation(
    runtime_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[str, str]:
    _, runtime_src, _ = canonical_event_timestamp_with_provenance(runtime_row)
    _, master_src, _ = canonical_event_timestamp_with_provenance(master_row)

    runtime_domain = chronology_domain(runtime_src)
    master_domain = chronology_domain(master_src)

    return runtime_domain, master_domain

'''
text = text.replace(anchor, helpers + anchor, 1)

# Replace cross-domain evidence with domain-separation semantics.
pattern = re.compile(
    r'def cross_domain_supersession_evidence\(\n'
    r'    runtime_row: Dict\[str, Any\],\n'
    r'    master_row: Dict\[str, Any\],\n'
    r'\) -> Tuple\[bool, str\]:\n'
    r'.*?'
    r'(?=\ndef semantically_comparable_supersession\()',
    re.S,
)
m = pattern.search(text)
if not m:
    raise RuntimeError("Phase 3.7.18.19 cross_domain_supersession_evidence block not found")

new_cross_domain = '''def cross_domain_supersession_evidence(
    runtime_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    runtime_event_dt, runtime_event_src, runtime_event_sem = canonical_semantic_event_time(runtime_row)
    master_event_dt, master_event_src, master_event_sem = canonical_semantic_event_time(master_row)

    runtime_business_date, runtime_business_src = canonical_business_date(runtime_row)
    master_business_date, master_business_src = canonical_business_date(master_row)

    runtime_domain, master_domain = separated_domain_relation(runtime_row, master_row)

    if runtime_domain == "unknown" or master_domain == "unknown":
        return False, (
            f"UNKNOWN_CHRONOLOGY_DOMAIN:"
            f"runtime={runtime_event_src}/{runtime_domain},"
            f"master={master_event_src}/{master_domain}"
        )

    # If both are in the same domain, chronology may be compared directly.
    if runtime_domain == master_domain:
        if runtime_domain == "event_time":
            if runtime_event_dt is None or master_event_dt is None:
                return False, "SAME_EVENT_DOMAIN_TIMESTAMP_MISSING"
            return (
                master_event_dt > runtime_event_dt,
                (
                    f"SAME_EVENT_DOMAIN_COMPARISON:"
                    f"runtime={runtime_event_src},master={master_event_src}"
                ),
            )

        if runtime_domain == "business_date":
            if runtime_business_date is None or master_business_date is None:
                return False, "SAME_BUSINESS_DOMAIN_DATE_MISSING"
            return (
                master_business_date > runtime_business_date,
                (
                    f"SAME_BUSINESS_DOMAIN_COMPARISON:"
                    f"runtime={runtime_business_src},master={master_business_src}"
                ),
            )

    # Critical Phase 3.7.18.20 rule:
    # master business-date and runtime event-time are deliberately separate
    # clock domains. A date such as master.run_date MUST NOT be declared stale
    # solely because runtime.updated_at occurs later in wall-clock time.
    if runtime_domain == "event_time" and master_domain == "business_date":
        if master_business_date is None:
            return False, "MASTER_BUSINESS_DATE_MISSING"
        if runtime_event_dt is None:
            return False, "RUNTIME_EVENT_TIME_MISSING"

        return False, (
            f"CROSS_DOMAIN_SEPARATED_NO_DIRECT_SUPERSESSION:"
            f"runtime={runtime_event_src}/{runtime_event_dt.date()},"
            f"master={master_business_src}/{master_business_date}"
        )

    if runtime_domain == "business_date" and master_domain == "event_time":
        if runtime_business_date is None or master_event_dt is None:
            return False, "CROSS_DOMAIN_CHRONOLOGY_MISSING"
        return False, (
            f"CROSS_DOMAIN_SEPARATED_NO_DIRECT_SUPERSESSION:"
            f"runtime={runtime_business_src}/{runtime_business_date},"
            f"master={master_event_src}/{master_event_dt.date()}"
        )

    return False, (
        f"UNSAFE_DOMAIN_RELATION:"
        f"runtime={runtime_domain},master={master_domain}"
    )
'''
text = text[:m.start()] + new_cross_domain + text[m.end():]

# Replace suspended reconciliation so separated domains do not get misclassified
# as "master is older". They remain fail-closed but with domain-specific reason.
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
    raise RuntimeError("suspended_is_superseded block not found")

new_sup = '''def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    runtime_domain, master_domain = separated_domain_relation(runtime_row, master_row)

    # Same-domain evidence may prove chronological supersession.
    if runtime_domain == master_domain and runtime_domain != "unknown":
        comparable, reason = semantically_comparable_supersession(
            runtime_row,
            master_row,
        )
        if comparable:
            return True, f"SUSPENDED_SUPERSEDED_WITHIN_DOMAIN:{reason}"
        return False, f"SUSPENDED_NOT_SUPERSEDED_WITHIN_DOMAIN:{reason}"

    # Cross-domain evidence is intentionally not compared as older/newer.
    # We preserve fail-closed behavior, but classify the blocker correctly.
    if runtime_domain != "unknown" and master_domain != "unknown":
        return False, (
            f"SUSPENDED_CROSS_DOMAIN_SUPERSESSION_UNRESOLVED:"
            f"runtime_domain={runtime_domain},"
            f"master_domain={master_domain}"
        )

    return False, (
        f"SUSPENDED_CHRONOLOGY_DOMAIN_UNKNOWN:"
        f"runtime_domain={runtime_domain},"
        f"master_domain={master_domain}"
    )
'''
text = text[:m.start()] + new_sup + text[m.end():]

old_label = '"compatibility_contract": "PHASE371819_CROSS_DOMAIN_BUSINESS_DATE_EVENT_TIME_RECONCILIATION",'
if text.count(old_label) != 1:
    raise RuntimeError("Phase 3.7.18.19 compatibility label mismatch")
text = text.replace(
    old_label,
    '"compatibility_contract": "PHASE371820_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION",',
    1,
)

audit_anchor = '        "cross_domain_supersession_contract": "PHASE371819",\n'
if text.count(audit_anchor) != 1:
    raise RuntimeError("Phase 3.7.18.19 audit anchor not found")

audit = '''        "runtime_chronology_domain": separated_domain_relation(
            sources["runtime"]["latest"],
            sources["master_cycle"]["latest"],
        )[0],
        "master_cycle_chronology_domain": separated_domain_relation(
            sources["runtime"]["latest"],
            sources["master_cycle"]["latest"],
        )[1],
        "domain_separation_contract": "PHASE371820",
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
print("[contract] business-date and event-time domains explicitly separated")
print("[contract] no direct older/newer verdict across domains")
print("[contract] unresolved cross-domain supersession remains fail-closed")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[3/7] Applying domain separation reconciliation patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying domain separation/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE371820_RUNTIME_SUPERVISION_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION_RECONCILIATION_FIX",
        "chronology_domain",
        "separated_domain_relation",
        "CROSS_DOMAIN_SEPARATED_NO_DIRECT_SUPERSESSION",
        "SUSPENDED_CROSS_DOMAIN_SUPERSESSION_UNRESOLVED",
        "PHASE371820_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION",
        "runtime_chronology_domain",
        "master_cycle_chronology_domain",
        "domain_separation_contract",
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
    Write-Host " Phase 3.7.18.20 PATCH APPLIED AND VERIFIED"
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
    Write-Host "Cross-domain unresolved state     : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
