#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.7.19"
Write-Host " Autonomous Failure Diagnosis + Safe Self-Healing Controller"
Write-Host " DRY-RUN / RECOMMEND-ONLY"
Write-Host "============================================================"

$Root = (Get-Location).Path
$PyRel = "automation\v92\phase3719_autonomous_failure_diagnosis_safe_self_healing_controller.py"
$YmlRel = ".github\workflows\gpt-quant-v92-phase3719-autonomous-failure-diagnosis-safe-self-healing-controller.yml"
$Py = Join-Path $Root $PyRel
$Yml = Join-Path $Root $YmlRel

New-Item -ItemType Directory -Force -Path (Split-Path $Py) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $Yml) | Out-Null

$Python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { throw "Python not found." }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Root ".phase3719-backup-$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
if (Test-Path $Py) { Copy-Item $Py (Join-Path $Backup ([IO.Path]::GetFileName($Py))) -Force }
if (Test-Path $Yml) { Copy-Item $Yml (Join-Path $Backup ([IO.Path]::GetFileName($Yml))) -Force }

$PySource = @'
from __future__ import annotations
import json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONTRACT = "PHASE3719_AUTONOMOUS_FAILURE_DIAGNOSIS_SAFE_SELF_HEALING_CONTROLLER"
MODE = "DRY_RUN_RECOMMEND_ONLY"
OUT = Path("artifacts/phase3719")
SAFETY = {
    "source_mutation": False,
    "git_commit": False,
    "git_push": False,
    "supabase_mutation": False,
    "qualification_counter_mutation": False,
    "production_schedule_mutation": False,
    "broker_order_enablement": False,
    "real_money_enablement": False,
    "historical_evidence_rewrite": False,
    "automatic_patch_application": False,
}

def api_get(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "gpt-quant-phase3719",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def classify(text):
    rules = [
        ("CODE_COMPATIBILITY", r"NameError|ImportError|ModuleNotFoundError|AttributeError|TypeError|SyntaxError",
         "Generate a compatibility repair plan only. Do not apply it automatically.", True),
        ("TIMEOUT_POLLING", r"timed out|timeout|in_progress.*pending|conclusion=pending|polling",
         "Inspect child-workflow polling interval and timeout budget.", True),
        ("CANONICAL_EVIDENCE", r"canonical|SUPERVISION_NOT_READY|NOT_SUPERSEDED|RECONCILIATION",
         "Collect the exact blocker/provenance and require human review before mutation.", False),
        ("DATABASE_SCHEMA_COMPATIBILITY", r"PostgREST|PGRST|column .* does not exist|relation .* does not exist|SQLSTATE",
         "Recommend schema compatibility mapping only; do not mutate Supabase.", False),
        ("SAFETY_BOUNDARY", r"REVOKED|FAIL_CLOSED|BROKER|REAL_MONEY|safety revocation|qualification bypass",
         "Preserve fail-closed state. Human review required.", False),
        ("WORKFLOW_CONTRACT", r"workflow.*not found|404|artifact.*not found|No files were found|Invalid workflow",
         "Inspect workflow path, dispatch contract, artifact path, and permissions.", True),
    ]
    for category, pattern, recommendation, eligible in rules:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            return category, m.group(0)[:200], recommendation, eligible
    return "UNKNOWN", "No known signature matched", "Preserve fail-closed state and review manually.", False

def main():
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not repo or not token:
        raise SystemExit("GITHUB_REPOSITORY/GITHUB_TOKEN missing")

    q = urllib.parse.urlencode({"status":"completed","per_page":"20"})
    runs = api_get(f"https://api.github.com/repos/{repo}/actions/runs?{q}", token).get("workflow_runs", [])
    failed = [r for r in runs if r.get("conclusion") == "failure"]

    findings = []
    for run in failed:
        rid = run["id"]
        jobs = api_get(f"https://api.github.com/repos/{repo}/actions/runs/{rid}/jobs?per_page=100", token).get("jobs", [])
        blob = [run.get("name",""), str(run.get("path",""))]
        for job in jobs:
            if job.get("conclusion") == "failure":
                blob.append(job.get("name",""))
                for step in job.get("steps", []) or []:
                    blob.append(f"{step.get('name')} {step.get('conclusion')}")
        category, signature, recommendation, eligible = classify("\n".join(blob))
        findings.append({
            "run_id": rid,
            "workflow_name": run.get("name"),
            "workflow_file": run.get("path"),
            "html_url": run.get("html_url"),
            "category": category,
            "signature": signature,
            "recommendation": recommendation,
            "auto_fix_eligible_class": eligible,
            "automatic_patch_applied": False,
        })

    result = {
        "contract": CONTRACT,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": repo,
        "failed_runs_scanned": len(failed),
        "findings": findings,
        "safety": SAFETY,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"phase3719_failure_diagnosis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    md = [
        "# Phase 3.7.19 — Autonomous Failure Diagnosis",
        "",
        f"- Mode: **{MODE}**",
        f"- Failed Runs Scanned: **{len(failed)}**",
        "- Automatic Patch Application: **DISABLED**",
        "- Source Mutation: **DISABLED**",
        "- Supabase Mutation: **DISABLED**",
        "- Broker / Real-Money: **DISABLED**",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        md.append("No failed runs found in the current scan window.")
    for f in findings:
        md += [
            f"### Run {f['run_id']} — {f['workflow_name']}",
            f"- Category: **{f['category']}**",
            f"- Signature: `{f['signature']}`",
            f"- Auto-Fix Eligible Class: **{'YES' if f['auto_fix_eligible_class'] else 'NO'}**",
            f"- Recommendation: {f['recommendation']}",
            "",
        ]
    (OUT/"phase3719_failure_diagnosis.md").write_text("\n".join(md)+"\n", encoding="utf-8")

    print(f"PHASE3719_MODE={MODE}")
    print(f"FAILED_RUNS_SCANNED={len(failed)}")
    print(f"FINDINGS={len(findings)}")
    print("AUTOMATIC_PATCH_APPLICATION=DISABLED")
    print("SOURCE_MUTATION=DISABLED")
    print("SUPABASE_MUTATION=DISABLED")
    print("BROKER_ORDER_SUBMISSION=DISABLED")
    print("REAL_MONEY_TRADING=DISABLED")

if __name__ == "__main__":
    main()
'@

$YmlSource = @'
name: GPT Quant Phase 3.7.19 - Autonomous Failure Diagnosis Safe Self-Healing Controller

on:
  workflow_dispatch:
  schedule:
    - cron: "17 * * * *"

permissions:
  contents: read
  actions: read

jobs:
  diagnose:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.19
        run: python -m py_compile automation/v92/phase3719_autonomous_failure_diagnosis_safe_self_healing_controller.py

      - name: Validate safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/phase3719_autonomous_failure_diagnosis_safe_self_healing_controller.py"
          grep -q '"source_mutation": False' "$f"
          grep -q '"git_push": False' "$f"
          grep -q '"supabase_mutation": False' "$f"
          grep -q '"broker_order_enablement": False' "$f"
          grep -q '"real_money_enablement": False' "$f"
          grep -q '"automatic_patch_application": False' "$f"
          echo "Phase 3.7.19 safety contract: PASS"

      - name: Run autonomous diagnosis
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: python automation/v92/phase3719_autonomous_failure_diagnosis_safe_self_healing_controller.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3719/phase3719_failure_diagnosis.md ]; then
            cat artifacts/phase3719/phase3719_failure_diagnosis.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload diagnosis evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3719-autonomous-failure-diagnosis
          path: artifacts/phase3719
          if-no-files-found: warn
          retention-days: 90
'@

function Restore-Targets {
    $b1 = Join-Path $Backup ([IO.Path]::GetFileName($Py))
    $b2 = Join-Path $Backup ([IO.Path]::GetFileName($Yml))
    if (Test-Path $b1) { Copy-Item $b1 $Py -Force } elseif (Test-Path $Py) { Remove-Item $Py -Force }
    if (Test-Path $b2) { Copy-Item $b2 $Yml -Force } elseif (Test-Path $Yml) { Remove-Item $Yml -Force }
}

try {
    Write-Host "[1/8] Backup prepared: $Backup"
    Write-Host "[2/8] Writing controller..."
    Set-Content -LiteralPath $Py -Value $PySource -Encoding UTF8
    Write-Host "[3/8] Writing workflow..."
    Set-Content -LiteralPath $Yml -Value $YmlSource -Encoding UTF8

    Write-Host "[4/8] Compile check..."
    if ($Python -eq "py") { & py -3 -m py_compile $Py } else { & python -m py_compile $Py }
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed." }

    Write-Host "[5/8] Safety verification..."
    $p = Get-Content $Py -Raw
    foreach ($t in @(
        'MODE = "DRY_RUN_RECOMMEND_ONLY"',
        '"source_mutation": False',
        '"git_push": False',
        '"supabase_mutation": False',
        '"qualification_counter_mutation": False',
        '"broker_order_enablement": False',
        '"real_money_enablement": False',
        '"historical_evidence_rewrite": False',
        '"automatic_patch_application": False'
    )) {
        if ($p -notmatch [regex]::Escape($t)) { throw "Missing safety token: $t" }
    }

    Write-Host "[6/8] Workflow verification..."
    $y = Get-Content $Yml -Raw
    foreach ($t in @("workflow_dispatch:", "schedule:", 'cron: "17 * * * *"', "contents: read", "actions: read")) {
        if ($y -notmatch [regex]::Escape($t)) { throw "Workflow verification failed: $t" }
    }
    if ($y -match "contents:\s*write") { throw "contents: write is forbidden." }

    Write-Host "[7/8] Git diff check..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $PyRel $YmlRel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        & git status --short -- $PyRel $YmlRel
    }

    Write-Host "[8/8] SUCCESS"
    Write-Host "============================================================"
    Write-Host " Phase 3.7.19 DEPLOYED AND VERIFIED"
    Write-Host "============================================================"
    Write-Host "Mode                           : DRY-RUN / RECOMMEND-ONLY"
    Write-Host "Hourly diagnosis               : YES"
    Write-Host "Automatic patch application    : NO"
    Write-Host "Source mutation                : NO"
    Write-Host "Git commit / push              : NO"
    Write-Host "Supabase mutation              : NO"
    Write-Host "Qualification counter mutation : NO"
    Write-Host "Broker order enablement        : NO"
    Write-Host "Real-money enablement          : NO"
    Write-Host "Historical evidence rewrite    : NO"
}
catch {
    Write-Host "ROLLBACK: restoring deployment targets..." -ForegroundColor Yellow
    Restore-Targets
    throw
}
