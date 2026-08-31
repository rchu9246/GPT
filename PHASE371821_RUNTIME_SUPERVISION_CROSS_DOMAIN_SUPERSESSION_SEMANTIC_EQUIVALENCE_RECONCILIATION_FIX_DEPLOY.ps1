#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.18.21 Deployment"
Write-Host " Runtime Supervision Cross-Domain Supersession"
Write-Host " Semantic Equivalence Reconciliation Fix"
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
$BackupDir = Join-Path $RepoRoot ".phase371821-backup-$Stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Write-Host "[2/7] Backup created: $BackupFile"

$PatchPy = Join-Path $env:TEMP "phase371821_patch_$Stamp.py"

$PatchCode = @'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

MARKER = "PHASE371821_RUNTIME_SUPERVISION_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE_RECONCILIATION_FIX"

if MARKER in text:
    print("[already fixed] marker present")
    raise SystemExit(0)

required = [
    "PHASE371820_RUNTIME_SUPERVISION_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION_RECONCILIATION_FIX",
    "SUSPENDED_CROSS_DOMAIN_SUPERSESSION_UNRESOLVED",
    "separated_domain_relation",
    "PHASE371820_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
]
for token in required:
    if token not in text:
        raise RuntimeError(f"Required Phase 3.7.18.20 token missing: {token}")

anchor = "def suspended_is_superseded(\n"
if text.count(anchor) != 1:
    raise RuntimeError("suspended_is_superseded anchor not found exactly once")

helpers = '''# PHASE371821_RUNTIME_SUPERVISION_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE_RECONCILIATION_FIX
def cross_domain_semantic_equivalence(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    runtime_domain, master_domain = separated_domain_relation(
        runtime_row,
        master_row,
    )

    if runtime_domain != "event_time" or master_domain != "business_date":
        return False, (
            f"CROSS_DOMAIN_EQUIVALENCE_NOT_APPLICABLE:"
            f"runtime_domain={runtime_domain},master_domain={master_domain}"
        )

    # Preserve hard-block semantics first.
    if blocked(runtime_row):
        runtime_state = state_of(runtime_row)
        if runtime_state not in {"SUSPENDED", "PAUSED", "INACTIVE"}:
            return False, f"RUNTIME_HARD_BLOCK_NOT_EQUIVALENT:{runtime_state}"

    if not active(activation_row) or blocked(activation_row):
        return False, "ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "MASTER_CYCLE_BLOCKED"

    # Cross-domain equivalence is semantic, not chronological.
    # We accept supersession only when:
    #   1) activation is canonical and active;
    #   2) master cycle is canonical/non-blocking;
    #   3) runtime state is a soft suspended state rather than a hard failure;
    #   4) master has a valid business date and runtime has a valid event time.
    runtime_dt, runtime_src, _ = canonical_event_timestamp_with_provenance(runtime_row)
    master_business_date, master_business_src = canonical_business_date(master_row)

    if runtime_dt is None:
        return False, "RUNTIME_EVENT_TIME_MISSING"

    if master_business_date is None:
        return False, "MASTER_BUSINESS_DATE_MISSING"

    runtime_state = state_of(runtime_row)
    if runtime_state not in {"SUSPENDED", "PAUSED", "INACTIVE"}:
        return False, f"RUNTIME_STATE_NOT_SOFT_SUSPENDED:{runtime_state}"

    return True, (
        f"CROSS_DOMAIN_SEMANTIC_EQUIVALENCE_CONFIRMED:"
        f"runtime_state={runtime_state},"
        f"runtime_source={runtime_src},"
        f"master_source={master_business_src}"
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
    raise RuntimeError("Phase 3.7.18.20 suspended_is_superseded block not found")

new_sup = '''def suspended_is_superseded(
    runtime_row: Dict[str, Any],
    activation_row: Dict[str, Any],
    master_row: Dict[str, Any],
) -> Tuple[bool, str]:
    if not active(activation_row) or blocked(activation_row):
        return False, "SUSPENDED_ACTIVATION_NOT_CANONICALLY_ACTIVE"

    if blocked(master_row):
        return False, "SUSPENDED_MASTER_CYCLE_BLOCKED"

    runtime_domain, master_domain = separated_domain_relation(
        runtime_row,
        master_row,
    )

    if runtime_domain == master_domain and runtime_domain != "unknown":
        comparable, reason = semantically_comparable_supersession(
            runtime_row,
            master_row,
        )
        if comparable:
            return True, f"SUSPENDED_SUPERSEDED_WITHIN_DOMAIN:{reason}"
        return False, f"SUSPENDED_NOT_SUPERSEDED_WITHIN_DOMAIN:{reason}"

    if runtime_domain != "unknown" and master_domain != "unknown":
        equivalent, reason = cross_domain_semantic_equivalence(
            runtime_row,
            activation_row,
            master_row,
        )
        if equivalent:
            return True, f"SUSPENDED_SUPERSEDED_BY_SEMANTIC_EQUIVALENCE:{reason}"

        return False, (
            f"SUSPENDED_CROSS_DOMAIN_SUPERSESSION_UNRESOLVED:"
            f"{reason}"
        )

    return False, (
        f"SUSPENDED_CHRONOLOGY_DOMAIN_UNKNOWN:"
        f"runtime_domain={runtime_domain},"
        f"master_domain={master_domain}"
    )
'''
text = text[:m.start()] + new_sup + text[m.end():]

old_label = '"compatibility_contract": "PHASE371820_MASTER_BUSINESS_DATE_RUNTIME_EVENT_DATE_DOMAIN_SEPARATION",'
if text.count(old_label) != 1:
    raise RuntimeError("Phase 3.7.18.20 compatibility label mismatch")
text = text.replace(
    old_label,
    '"compatibility_contract": "PHASE371821_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE",',
    1,
)

audit_anchor = '        "domain_separation_contract": "PHASE371820",\n'
if text.count(audit_anchor) != 1:
    raise RuntimeError("Phase 3.7.18.20 audit anchor not found")

audit = '''        "cross_domain_semantic_equivalence_applicable": (
            separated_domain_relation(
                sources["runtime"]["latest"],
                sources["master_cycle"]["latest"],
            ) == ("event_time", "business_date")
        ),
        "cross_domain_semantic_equivalence_contract": "PHASE371821",
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
print("[contract] cross-domain semantic equivalence reconciliation installed")
print("[contract] hard runtime failures remain blocking")
print("[contract] only soft SUSPENDED/PAUSED/INACTIVE states are equivalence-eligible")
'@

Set-Content -LiteralPath $PatchPy -Value $PatchCode -Encoding UTF8

function Restore-Target {
    Write-Host ""
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
}

try {
    Write-Host "[3/7] Applying semantic equivalence reconciliation patch..."
    if ($PythonMode -eq "py") { & py -3 $PatchPy $Target } else { & python $PatchPy $Target }
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Verifying semantic equivalence/safety contract..."
    $After = Get-Content -LiteralPath $Target -Raw

    foreach ($Token in @(
        "PHASE371821_RUNTIME_SUPERVISION_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE_RECONCILIATION_FIX",
        "cross_domain_semantic_equivalence",
        "CROSS_DOMAIN_SEMANTIC_EQUIVALENCE_CONFIRMED",
        "SUSPENDED_SUPERSEDED_BY_SEMANTIC_EQUIVALENCE",
        "RUNTIME_HARD_BLOCK_NOT_EQUIVALENT",
        "RUNTIME_STATE_NOT_SOFT_SUSPENDED",
        "PHASE371821_CROSS_DOMAIN_SUPERSESSION_SEMANTIC_EQUIVALENCE",
        "cross_domain_semantic_equivalence_applicable",
        "cross_domain_semantic_equivalence_contract",
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
    Write-Host " Phase 3.7.18.21 PATCH APPLIED AND VERIFIED"
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
    Write-Host "Hard runtime failure bypass       : NO"
    Write-Host "Ambiguous semantic equivalence    : FAIL-CLOSED"
}
catch {
    Restore-Target
    throw
}
finally {
    Remove-Item -LiteralPath $PatchPy -Force -ErrorAction SilentlyContinue
}
