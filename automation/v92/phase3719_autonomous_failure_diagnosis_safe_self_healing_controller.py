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
        "# Phase 3.7.19 ??Autonomous Failure Diagnosis",
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
            f"### Run {f['run_id']} ??{f['workflow_name']}",
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
