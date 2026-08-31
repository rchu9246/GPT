$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Phase = "3.7.18.14"
$Target = "automation/v92/paper_trading_phase374_production_paper_daily_cycle_monitoring_evidence_accumulation.py"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path (Get-Location) ".phase371814-backup-$Stamp"
$PatchPy = Join-Path $env:TEMP "phase371814_patch_$Stamp.py"

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

Write-Host "============================================================"
Write-Host " GPT Quant Phase $Phase Deployment"
Write-Host " Runtime Supervision Suspended Master Cycle"
Write-Host " Supersession Chronology Reconciliation Fix"
Write-Host "============================================================"
Write-Host ""

if (-not (Test-Path ".git")) { Fail "Run from the GPT repository root." }
if (-not (Test-Path $Target)) { Fail "Target not found: $Target" }

Write-Host "[1/7] Preflight compile..."
python -m py_compile $Target
if ($LASTEXITCODE -ne 0) { Fail "Existing Phase 3.7.4 Python does not compile." }

Write-Host "[2/7] Backup..."
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Copy-Item $Target (Join-Path $BackupDir ([IO.Path]::GetFileName($Target))) -Force
Write-Host "  Backup: $BackupDir"

Write-Host "[3/7] Applying chronology reconciliation patch..."

$helper = @'
from pathlib import Path
import re, sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
original = text

old = '''"master_newer_than_runtime": (
            canonical_timestamp(sources["master_cycle"]["latest"]) is not None
            and canonical_timestamp(sources["runtime"]["latest"]) is not None
            and canonical_timestamp(sources["master_cycle"]["latest"])
            > canonical_timestamp(sources["runtime"]["latest"])
        ),'''

new = '''"master_newer_than_runtime": (
            canonical_timestamp(sources["master_cycle"]["latest"]) is not None
            and canonical_timestamp(sources["runtime"]["latest"]) is not None
            and canonical_timestamp(sources["master_cycle"]["latest"])
            > canonical_timestamp(sources["runtime"]["latest"])
        ),
        "master_supersession_chronology_reconciled": (
            canonical_timestamp(sources["runtime"]["latest"]) is not None
            and (
                (
                    canonical_timestamp(sources["master_cycle"]["latest"]) is not None
                    and canonical_timestamp(sources["master_cycle"]["latest"])
                    > canonical_timestamp(sources["runtime"]["latest"])
                )
                or
                (
                    canonical_timestamp(sources["activation"]["latest"]) is not None
                    and canonical_timestamp(sources["activation"]["latest"])
                    > canonical_timestamp(sources["runtime"]["latest"])
                    and active(sources["activation"]["latest"])
                    and not blocked(sources["activation"]["latest"])
                )
            )
        ),'''

if old in text:
    text = text.replace(old, new, 1)
elif '"master_supersession_chronology_reconciled"' not in text:
    raise RuntimeError("Expected Phase 3.7.18.13 chronology anchor not found; fail-closed.")

anchor = 'chronology["master_newer_than_runtime"]'
if "master_supersession_chronology_reconciled" in text:
    positions = [m.start() for m in re.finditer(re.escape(anchor), text)]
    patched_gate = False
    for pos in reversed(positions):
        window = text[max(0,pos-1000):min(len(text),pos+1000)]
        if "SUSPEND" in window.upper() or "runtime_supervision" in window:
            replacement = '(chronology["master_newer_than_runtime"] or chronology["master_supersession_chronology_reconciled"])'
            text = text[:pos] + replacement + text[pos+len(anchor):]
            patched_gate = True
            break
    if not patched_gate and "SUSPENDED_NOT_SUPERSEDED_BY_MASTER" not in text:
        raise RuntimeError("Master supersession runtime gate not found; fail-closed.")

for forbidden in [
    "BROKER_ORDER_SUBMISSION=ENABLED",
    "REAL_MONEY_TRADING=ENABLED",
    "SYNTHETIC_CYCLE_DATE=ENABLED",
    "MANUAL_COUNTER_INCREMENT=ENABLED",
    "QUALIFICATION_THRESHOLD_BYPASS=ENABLED",
]:
    if forbidden in text and forbidden not in original:
        raise RuntimeError("Forbidden safety mutation introduced: " + forbidden)

path.write_text(text, encoding="utf-8", newline="\n")
print("Patch helper PASS")
'@

Set-Content -LiteralPath $PatchPy -Value $helper -Encoding UTF8

try {
    python $PatchPy $Target
    if ($LASTEXITCODE -ne 0) { throw "Patch helper failed." }

    Write-Host "[4/7] Post-patch compile..."
    python -m py_compile $Target
    if ($LASTEXITCODE -ne 0) { throw "Post-patch compile failed." }

    Write-Host "[5/7] Safety contract verification..."
    $src = Get-Content -Raw -LiteralPath $Target
    if ($src -notmatch 'master_supersession_chronology_reconciled') { throw "Chronology contract missing." }
    if ($src -notmatch 'canonical_timestamp') { throw "Canonical timestamp contract missing." }
    if ($src -notmatch 'SUSPENDED') { throw "SUSPENDED fail-closed semantics missing." }

    Write-Host "[6/7] Git whitespace verification..."
    git diff --check -- $Target
    if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }

    Write-Host "[7/7] SUCCESS"
}
catch {
    Write-Host "ROLLBACK: restoring original Phase 3.7.4 Python..." -ForegroundColor Yellow
    $BackupFile = Join-Path $BackupDir ([IO.Path]::GetFileName($Target))
    if (Test-Path $BackupFile) { Copy-Item $BackupFile $Target -Force }
    Remove-Item $PatchPy -Force -ErrorAction SilentlyContinue
    Fail $_.Exception.Message
}
finally {
    Remove-Item $PatchPy -Force -ErrorAction SilentlyContinue
}

Write-Host "============================================================"
Write-Host " Phase $Phase PATCH APPLIED AND VERIFIED"
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
Write-Host "Ambiguous chronology              : FAIL-CLOSED"
Write-Host ""
Write-Host "NEXT: review diff, stage target, commit, push, then re-run Phase 3.7.4 first."
