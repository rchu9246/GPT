#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=================================================================="
Write-Host " GPT Quant Phase 3.7.19.1"
Write-Host " Failure Log Evidence Deep Inspection + Targeted Workflow Discovery"
Write-Host " DRY-RUN / RECOMMEND-ONLY"
Write-Host "=================================================================="

$Root = (Get-Location).Path
$PyRel  = "automation\v92\phase37191_failure_log_evidence_deep_inspection_targeted_workflow_discovery.py"
$YmlRel = ".github\workflows\gpt-quant-v92-phase37191-failure-log-evidence-deep-inspection-targeted-workflow-discovery.yml"
$Py  = Join-Path $Root $PyRel
$Yml = Join-Path $Root $YmlRel

New-Item -ItemType Directory -Force -Path (Split-Path $Py) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $Yml) | Out-Null

$Python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { throw "Python not found." }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Root ".phase37191-backup-$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
if (Test-Path $Py)  { Copy-Item $Py  (Join-Path $Backup ([IO.Path]::GetFileName($Py))) -Force }
if (Test-Path $Yml) { Copy-Item $Yml (Join-Path $Backup ([IO.Path]::GetFileName($Yml))) -Force }

$PySource = @'
from __future__ import annotations

import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CONTRACT = "PHASE37191_FAILURE_LOG_EVIDENCE_DEEP_INSPECTION_TARGETED_WORKFLOW_DISCOVERY"
MODE = "DRY_RUN_RECOMMEND_ONLY"
OUT = Path("artifacts/phase37191")
MAX_RUNS = 50
MAX_LOG_BYTES = 8000000

TARGET_HINTS = (
    "3.7.10", "3710", "multi-day qualification", "multi day qualification",
    "3.7.13", "3713", "natural qualification", "qualification orchestration",
)

SAFETY = {
    "source_mutation": False,
    "git_commit": False,
    "git_push": False,
    "supabase_mutation": False,
    "qualification_counter_mutation": False,
    "synthetic_qualification": False,
    "production_schedule_mutation": False,
    "broker_order_enablement": False,
    "real_money_enablement": False,
    "historical_evidence_rewrite": False,
    "automatic_patch_application": False,
}

RULES = [
    ("CODE_COMPATIBILITY", r"\b(NameError|ImportError|ModuleNotFoundError|AttributeError|TypeError|SyntaxError|KeyError)\b.{0,300}",
     "HIGH", True, "Generate a compatibility-only repair plan. Do not apply source changes automatically."),
    ("TIMEOUT_POLLING", r"(timed out|timeout|conclusion=pending|status=in_progress|polling|poll limit|exceeded .* timeout).{0,300}",
     "HIGH", True, "Inspect child-workflow polling interval, timeout budget, and final conclusion retrieval semantics."),
    ("CHILD_WORKFLOW_FAILURE", r"(Dispatching Phase|child workflow|workflow_dispatch|failed with conclusion=failure|conclusion=failure).{0,300}",
     "HIGH", True, "Trace the dispatched child workflow run and inspect its own failed job/step before changing the orchestrator."),
    ("DATABASE_SCHEMA_COMPATIBILITY", r"(PostgREST|PGRST|SQLSTATE|column .* does not exist|relation .* does not exist|schema cache|undefined column).{0,300}",
     "HIGH", False, "Recommend schema-contract compatibility only. Do not mutate Supabase automatically."),
    ("CANONICAL_EVIDENCE", r"(CANONICAL|canonical|reconciliation|SUPERVISION_NOT_READY|NOT_SUPERSEDED|evidence mismatch|provenance).{0,300}",
     "MEDIUM", False, "Collect canonical blocker/provenance and require human review before any state mutation."),
    ("WORKFLOW_CONTRACT", r"(workflow.*not found|Invalid workflow|No files were found|artifact.*not found|HTTP 404|404 Not Found|permission denied).{0,300}",
     "HIGH", True, "Inspect workflow filename, dispatch contract, permissions, and artifact paths."),
    ("SAFETY_BOUNDARY", r"(FAIL_CLOSED|REVOKED|safety revocation|BROKER|REAL_MONEY|qualification bypass).{0,300}",
     "HIGH", False, "Preserve fail-closed behavior and require explicit human review."),
]

def headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gpt-quant-phase37191",
    }

def api_json(url, token):
    req = urllib.request.Request(url, headers=headers(token))
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))

def api_bytes(url, token):
    req = urllib.request.Request(url, headers=headers(token))
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(MAX_LOG_BYTES)

def unzip_logs(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            parts = []
            for name in z.namelist():
                try:
                    parts.append("===== " + name + " =====\n" + z.read(name).decode("utf-8", errors="replace"))
                except Exception:
                    pass
            return "\n".join(parts)
    except zipfile.BadZipFile:
        return data.decode("utf-8", errors="replace")

def is_target(run):
    text = " ".join(str(run.get(k) or "") for k in ("name","display_title","path","event")).lower()
    return any(h in text for h in TARGET_HINTS)

def classify(text):
    for category, pattern, confidence, eligible, rec in RULES:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            sig = re.sub(r"\s+", " ", m.group(0)).strip()[:500]
            return category, sig, confidence, eligible, rec
    return "UNKNOWN", "No known failure signature matched after deep inspection", "LOW", False, "Preserve fail-closed behavior and review captured evidence."

def excerpt(text, signature):
    if signature and signature in text:
        i = text.find(signature)
        return text[max(0, i-700):min(len(text), i+1100)]
    m = re.search(r"(Traceback|Error:|ERROR|Exception|failed with conclusion=failure|Process completed with exit code)", text, re.I)
    if m:
        return text[max(0,m.start()-500):min(len(text),m.start()+1300)]
    return text[:1800]

def child_refs(text):
    found = []
    for p in (r"Dispatching Phase\s+([^\r\n]+)", r"Workflow:\s*([^\s]+\.ya?ml)", r"actions/runs/(\d+)", r"run[_ ]id[=: ]+(\d+)"):
        for m in re.finditer(p, text, re.I):
            v = m.group(1).strip()
            if v and v not in found:
                found.append(v)
    return found[:20]

def main():
    repo = os.getenv("GITHUB_REPOSITORY","").strip()
    token = os.getenv("GITHUB_TOKEN","").strip()
    if not repo or not token:
        raise SystemExit("GITHUB_REPOSITORY/GITHUB_TOKEN missing")

    q = urllib.parse.urlencode({"status":"completed","per_page":str(MAX_RUNS)})
    runs = api_json(f"https://api.github.com/repos/{repo}/actions/runs?{q}", token).get("workflow_runs", [])
    failed = [r for r in runs if r.get("conclusion") == "failure"]
    selected = [r for r in failed if is_target(r)][:10] + [r for r in failed if not is_target(r)][:10]

    findings = []
    for run in selected:
        rid = int(run["id"])
        notes = []
        try:
            jobs = api_json(f"https://api.github.com/repos/{repo}/actions/runs/{rid}/jobs?per_page=100", token).get("jobs", [])
        except Exception as e:
            jobs = []
            notes.append(f"JOB_READ_FAILED: {e}")

        meta = []
        failed_jobs = []
        for job in jobs:
            meta.append(f"JOB {job.get('name')} status={job.get('status')} conclusion={job.get('conclusion')}")
            failed_steps = []
            for step in job.get("steps", []) or []:
                meta.append(f"STEP {step.get('number')} {step.get('name')} status={step.get('status')} conclusion={step.get('conclusion')}")
                if step.get("conclusion") == "failure":
                    failed_steps.append(step.get("name"))
            if job.get("conclusion") == "failure":
                failed_jobs.append({"job_name": job.get("name"), "failed_steps": failed_steps, "html_url": job.get("html_url")})

        logs = ""
        try:
            logs = unzip_logs(api_bytes(f"https://api.github.com/repos/{repo}/actions/runs/{rid}/logs", token))
        except Exception as e:
            notes.append(f"RUN_LOG_READ_FAILED: {e}")

        combined = "\n".join([
            f"workflow={run.get('name')}",
            f"path={run.get('path')}",
            f"display_title={run.get('display_title')}",
            "\n".join(meta),
            logs,
        ])

        category, signature, confidence, eligible, rec = classify(combined)
        findings.append({
            "run_id": rid,
            "workflow_name": run.get("name"),
            "workflow_file": run.get("path"),
            "html_url": run.get("html_url"),
            "created_at": run.get("created_at"),
            "targeted": is_target(run),
            "category": category,
            "confidence": confidence,
            "signature": signature,
            "recommendation": rec,
            "auto_fix_eligible_class": eligible,
            "automatic_patch_applied": False,
            "failed_jobs": failed_jobs,
            "child_workflow_references": child_refs(combined),
            "log_excerpt": excerpt(combined, signature),
            "notes": notes,
        })

    result = {
        "contract": CONTRACT,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": repo,
        "failed_runs_scanned": len(selected),
        "targeted_runs_found": sum(1 for f in findings if f["targeted"]),
        "findings": findings,
        "safety": SAFETY,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"phase37191_failure_diagnosis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Phase 3.7.19.1 — Failure Log Evidence Deep Inspection",
        "",
        f"- Mode: **{MODE}**",
        f"- Failed Runs Scanned: **{result['failed_runs_scanned']}**",
        f"- Targeted Runs Found: **{result['targeted_runs_found']}**",
        "- Automatic Patch Application: **DISABLED**",
        "- Source Mutation: **DISABLED**",
        "- Supabase Mutation: **DISABLED**",
        "- Qualification Counter Mutation: **DISABLED**",
        "- Broker / Real-Money: **DISABLED**",
        "",
        "## Findings",
        "",
    ]
    for f in findings:
        md += [
            f"### Run {f['run_id']} — {f.get('workflow_name')}",
            f"- Targeted 3.7.10 / 3.7.13: **{'YES' if f['targeted'] else 'NO'}**",
            f"- Category: **{f['category']}**",
            f"- Confidence: **{f['confidence']}**",
            f"- Signature: `{f['signature']}`",
            f"- Auto-Fix Eligible Class: **{'YES' if f['auto_fix_eligible_class'] else 'NO'}**",
            f"- Recommendation: {f['recommendation']}",
        ]
        if f["failed_jobs"]:
            md.append("- Failed Jobs:")
            for j in f["failed_jobs"]:
                md.append(f"  - `{j.get('job_name')}` → {', '.join(j.get('failed_steps') or []) or 'unknown step'}")
        if f["child_workflow_references"]:
            md.append("- Child Workflow References:")
            for ref in f["child_workflow_references"]:
                md.append(f"  - `{ref}`")
        if f["log_excerpt"]:
            clean = f["log_excerpt"].replace("```", "~~~")
            md += ["", "<details>", "<summary>Failure log excerpt</summary>", "", "```text", clean[:3000], "```", "</details>"]
        if f["notes"]:
            md.append("- Notes:")
            for n in f["notes"]:
                md.append(f"  - `{n}`")
        md.append("")

    if not findings:
        md.append("No failed workflow runs found in the current scan window.")

    (OUT/"phase37191_failure_diagnosis.md").write_text("\n".join(md)+"\n", encoding="utf-8")

    print(f"PHASE37191_MODE={MODE}")
    print(f"FAILED_RUNS_SCANNED={result['failed_runs_scanned']}")
    print(f"TARGETED_RUNS_FOUND={result['targeted_runs_found']}")
    print("AUTOMATIC_PATCH_APPLICATION=DISABLED")
    print("SOURCE_MUTATION=DISABLED")
    print("SUPABASE_MUTATION=DISABLED")
    print("QUALIFICATION_COUNTER_MUTATION=DISABLED")
    print("BROKER_ORDER_SUBMISSION=DISABLED")
    print("REAL_MONEY_TRADING=DISABLED")

if __name__ == "__main__":
    main()
'@

$YmlSource = @'
name: GPT Quant Phase 3.7.19.1 - Failure Log Evidence Deep Inspection Targeted Workflow Discovery

on:
  workflow_dispatch:
  schedule:
    - cron: "27 * * * *"

permissions:
  contents: read
  actions: read

jobs:
  diagnose:
    name: failure-log-deep-inspection
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.19.1
        run: python -m py_compile automation/v92/phase37191_failure_log_evidence_deep_inspection_targeted_workflow_discovery.py

      - name: Validate safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/phase37191_failure_log_evidence_deep_inspection_targeted_workflow_discovery.py"
          grep -q 'MODE = "DRY_RUN_RECOMMEND_ONLY"' "$f"
          grep -q '"source_mutation": False' "$f"
          grep -q '"git_push": False' "$f"
          grep -q '"supabase_mutation": False' "$f"
          grep -q '"qualification_counter_mutation": False' "$f"
          grep -q '"broker_order_enablement": False' "$f"
          grep -q '"real_money_enablement": False' "$f"
          grep -q '"automatic_patch_application": False' "$f"
          echo "Phase 3.7.19.1 safety contract: PASS"

      - name: Run failure log deep inspection
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: python automation/v92/phase37191_failure_log_evidence_deep_inspection_targeted_workflow_discovery.py

      - name: Publish diagnostic summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase37191/phase37191_failure_diagnosis.md ]; then
            cat artifacts/phase37191/phase37191_failure_diagnosis.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload diagnostic evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37191-failure-log-evidence
          path: artifacts/phase37191
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
    Write-Host "[2/8] Writing Phase 3.7.19.1 controller..."
    Set-Content -LiteralPath $Py -Value $PySource -Encoding UTF8

    Write-Host "[3/8] Writing Phase 3.7.19.1 workflow..."
    Set-Content -LiteralPath $Yml -Value $YmlSource -Encoding UTF8

    Write-Host "[4/8] Python compile verification..."
    if ($Python -eq "py") { & py -3 -m py_compile $Py } else { & python -m py_compile $Py }
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed." }

    Write-Host "[5/8] Safety contract verification..."
    $p = Get-Content -LiteralPath $Py -Raw
    foreach ($t in @(
        'MODE = "DRY_RUN_RECOMMEND_ONLY"',
        '"source_mutation": False',
        '"git_commit": False',
        '"git_push": False',
        '"supabase_mutation": False',
        '"qualification_counter_mutation": False',
        '"synthetic_qualification": False',
        '"production_schedule_mutation": False',
        '"broker_order_enablement": False',
        '"real_money_enablement": False',
        '"historical_evidence_rewrite": False',
        '"automatic_patch_application": False'
    )) {
        if ($p -notmatch [regex]::Escape($t)) { throw "Missing safety token: $t" }
    }

    Write-Host "[6/8] Workflow verification..."
    $y = Get-Content -LiteralPath $Yml -Raw
    foreach ($t in @("workflow_dispatch:", "schedule:", 'cron: "27 * * * *"', "contents: read", "actions: read")) {
        if ($y -notmatch [regex]::Escape($t)) { throw "Workflow verification failed: $t" }
    }
    if ($y -match "contents:\s*write") { throw "Forbidden workflow permission: contents: write" }
    if ($y -match "actions:\s*write") { throw "Forbidden workflow permission: actions: write" }

    Write-Host "[7/8] Git diff verification..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        & git diff --check -- $PyRel $YmlRel
        if ($LASTEXITCODE -ne 0) { throw "git diff --check failed." }
        & git status --short -- $PyRel $YmlRel
    }

    Write-Host "[8/8] SUCCESS"
    Write-Host "=================================================================="
    Write-Host " Phase 3.7.19.1 DEPLOYED AND VERIFIED"
    Write-Host "=================================================================="
    Write-Host "Mode                           : DRY-RUN / RECOMMEND-ONLY"
    Write-Host "Deep failure-log inspection    : YES"
    Write-Host "Target Phase 3.7.10 discovery  : YES"
    Write-Host "Target Phase 3.7.13 discovery  : YES"
    Write-Host "Child workflow reference scan  : YES"
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
    Write-Host "ROLLBACK: restoring Phase 3.7.19.1 targets..." -ForegroundColor Yellow
    Restore-Targets
    throw
}
