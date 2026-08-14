$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.2 Phase 3.4.3 Deployment"
Write-Host " Qualification Completion + Approval Readiness"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase343_approval_readiness.py"
$ymlPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase343.yml"

$python = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.3
Qualification Completion + Approval Readiness

Purpose:
- Re-evaluate canonical Phase 3.4 qualification state.
- Require Phase 3.4.2-grade canonical fields.
- Detect completion of required PASS days.
- Transition only to READY_FOR_HUMAN_APPROVAL.
- Never auto-approve.
- Never unlock release.
- Never enable broker or real-money trading.
- Fail closed on missing/inconsistent qualification data.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE34 = ROOT / "automation" / "v92" / "paper_trading_phase34_human_approval_release.py"
PHASE34_RESULT = ROOT / "phase34_result.json"
OUTDIR = ROOT / "phase343_output"
OUTDIR.mkdir(exist_ok=True)

VERSION = "3.4.3"
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE343_REQUIRED_PASS_DAYS", "5"))

REQUIRED_FIELDS = (
    "status",
    "qualification_state",
    "release_state",
    "consecutive_pass_days",
    "latest_market_date",
    "market_stale_days",
    "pass_day_source",
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_phase34_evaluate():
    if not PHASE34.exists():
        raise RuntimeError(f"Missing Phase 3.4 engine: {PHASE34}")

    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY_VERSION
    env["PAPER_TRADING_MODE"] = MODE
    env["PHASE34_ACTION"] = "evaluate"
    env["PHASE34_APPROVER"] = ""
    env["PHASE34_APPROVAL_TEXT"] = ""

    proc = subprocess.run(
        [sys.executable, str(PHASE34)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    (OUTDIR / "phase34_stdout.txt").write_text(
        proc.stdout or "", encoding="utf-8"
    )
    (OUTDIR / "phase34_stderr.txt").write_text(
        proc.stderr or "", encoding="utf-8"
    )

    if proc.returncode != 0:
        raise RuntimeError(
            "Phase 3.4 evaluate returned non-zero exit code.\n"
            f"exit_code={proc.returncode}\n"
            f"stdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )


def load_phase34_result():
    if not PHASE34_RESULT.exists():
        raise RuntimeError(
            "Phase 3.4 completed but phase34_result.json was not generated."
        )

    try:
        data = json.loads(PHASE34_RESULT.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid phase34_result.json: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("phase34_result.json is not a JSON object.")

    return data


def validate_source(data):
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in data or data[field] is None:
            errors.append(f"missing:{field}")

    if errors:
        return False, errors

    if str(data.get("pass_day_source")) != "distinct_run_date_snapshot_status":
        errors.append("pass_day_source_mismatch")

    # Phase 3.4 canonical engine currently exposes safety mode as "mode".
    if str(data.get("mode")) != MODE:
        errors.append("safety_mode_mismatch")

    try:
        pass_days = int(data.get("consecutive_pass_days"))
        stale_days = int(data.get("market_stale_days"))
    except (TypeError, ValueError):
        errors.append("numeric_qualification_field_invalid")
        return False, errors

    if pass_days < 0:
        errors.append("negative_pass_day_count")

    if stale_days < 0:
        errors.append("negative_market_stale_days")

    if str(data.get("release_state")).upper() != "LOCKED":
        errors.append("release_not_locked_before_human_approval")

    return len(errors) == 0, errors


def build_summary(data, source_valid, source_errors):
    if not source_valid:
        return {
            "version": VERSION,
            "checked_at": now_iso(),
            "status": "BLOCKED",
            "qualification_state": "BLOCKED",
            "approval_readiness": "BLOCKED",
            "release_state": "LOCKED",
            "strategy_version": STRATEGY_VERSION,
            "trading_mode": MODE,
            "pass_day_source": data.get("pass_day_source") if isinstance(data, dict) else None,
            "consecutive_pass_days": None,
            "required_pass_days": REQUIRED_PASS_DAYS,
            "remaining_pass_days": None,
            "latest_market_date": None,
            "market_stale_days": None,
            "canonical_source_valid": False,
            "source_errors": source_errors,
            "human_approval_required": True,
            "automatic_approval": False,
            "broker_trading_enabled": False,
            "real_money_trading_enabled": False,
        }

    canonical_status = str(data.get("status")).upper()
    pass_days = int(data.get("consecutive_pass_days"))
    stale_days = int(data.get("market_stale_days"))
    latest_market_date = str(data.get("latest_market_date"))
    source = str(data.get("pass_day_source"))
    remaining = max(REQUIRED_PASS_DAYS - pass_days, 0)

    # Qualification completion is intentionally stricter than a simple
    # pass-day threshold: the canonical daily evaluation itself must PASS.
    complete = (
        canonical_status == "PASS"
        and pass_days >= REQUIRED_PASS_DAYS
    )

    if complete:
        status = "PASS"
        qualification_state = "QUALIFIED"
        approval_readiness = "READY_FOR_HUMAN_APPROVAL"
    else:
        status = "PASS" if canonical_status == "PASS" else "BLOCKED"
        qualification_state = "OBSERVATION" if canonical_status == "PASS" else "BLOCKED"
        approval_readiness = "NOT_READY" if canonical_status == "PASS" else "BLOCKED"

    return {
        "version": VERSION,
        "checked_at": now_iso(),
        "status": status,
        "canonical_status": canonical_status,
        "qualification_state": qualification_state,
        "approval_readiness": approval_readiness,
        "release_state": "LOCKED",
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "pass_day_source": source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "remaining_pass_days": remaining,
        "latest_market_date": latest_market_date,
        "market_stale_days": stale_days,
        "canonical_source_valid": True,
        "source_errors": [],
        "human_approval_required": True,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
    }


def write_step_summary(summary):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return

    def val(v):
        return "N/A" if v is None else str(v)

    with open(path, "a", encoding="utf-8") as f:
        f.write("# GPT Quant V9.2 Paper Trading - Phase 3.4.3\n\n")
        f.write("## Qualification Completion + Approval Readiness\n\n")
        f.write(f"- Status: **{val(summary['status'])}**\n")
        f.write(f"- Qualification State: **{val(summary['qualification_state'])}**\n")
        f.write(f"- Approval Readiness: **{val(summary['approval_readiness'])}**\n")
        f.write(f"- Release State: **{val(summary['release_state'])}**\n")
        f.write(f"- Strategy: `{summary['strategy_version']}`\n")
        f.write(f"- Trading Mode: `{summary['trading_mode']}`\n")
        f.write(f"- PASS-day Source: `{val(summary['pass_day_source'])}`\n")
        f.write(
            f"- Consecutive PASS days: **{val(summary['consecutive_pass_days'])} / "
            f"{summary['required_pass_days']}**\n"
        )
        f.write(f"- Remaining PASS days: **{val(summary['remaining_pass_days'])}**\n")
        f.write(f"- Latest market date: `{val(summary['latest_market_date'])}`\n")
        f.write(f"- Market stale days: `{val(summary['market_stale_days'])}`\n")
        f.write(
            f"- Canonical source valid: **"
            f"{'YES' if summary['canonical_source_valid'] else 'NO'}**\n"
        )

        if summary["source_errors"]:
            f.write(f"- Source errors: `{', '.join(summary['source_errors'])}`\n")

        f.write("\n### Approval Gate\n\n")
        if summary["approval_readiness"] == "READY_FOR_HUMAN_APPROVAL":
            f.write("- Qualification requirement: **COMPLETE**\n")
            f.write("- Human approval request: **ALLOWED**\n")
        elif summary["approval_readiness"] == "NOT_READY":
            f.write("- Qualification requirement: **INCOMPLETE**\n")
            f.write("- Human approval request: **NOT YET ALLOWED**\n")
        else:
            f.write("- Qualification requirement: **BLOCKED**\n")
            f.write("- Human approval request: **BLOCKED**\n")

        f.write("\n### Safety Locks\n\n")
        f.write("- Human approval required: **YES**\n")
        f.write("- Automatic approval: **DISABLED**\n")
        f.write("- Release remains locked: **YES**\n")
        f.write("- Broker trading: **DISABLED**\n")
        f.write("- Real-money trading: **DISABLED**\n")
        f.write("- Missing/inconsistent qualification data => **BLOCKED / FAIL-CLOSED**\n")


def main():
    print("=== GPT Quant V9.2 Phase 3.4.3 Qualification Completion + Approval Readiness ===")

    run_phase34_evaluate()
    data = load_phase34_result()

    source_valid, source_errors = validate_source(data)
    summary = build_summary(data, source_valid, source_errors)

    (OUTDIR / "phase343_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUTDIR / "phase34_canonical_result.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    write_step_summary(summary)

    # Fail closed only for invalid canonical data or non-PASS canonical state.
    # Being below 5/5 is a valid OBSERVATION state, not a workflow failure.
    if not source_valid:
        return 1
    if summary["status"] == "BLOCKED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

$workflow = @'
name: GPT Quant V9.2 Paper Trading Phase 3.4.3 - Qualification Completion + Approval Readiness

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string

  schedule:
    # 09:18 UTC = 17:18 Asia/Taipei, weekdays.
    # Runs after Phase 3.4.2 daily qualification-state check.
    - cron: "18 9 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-v92-phase343-approval-readiness
  cancel-in-progress: false

jobs:
  qualification-completion:
    runs-on: ubuntu-latest
    timeout-minutes: 12

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PHASE343_REQUIRED_PASS_DAYS: "5"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Validate Phase 3.4.3 environment
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase34_human_approval_release.py
          test -f automation/v92/paper_trading_phase342_qualification_state_fix.py
          test -f automation/v92/paper_trading_phase343_approval_readiness.py

      - name: Run Phase 3.4.2 canonical persistence guard
        run: python automation/v92/paper_trading_phase342_qualification_state_fix.py

      - name: Run Phase 3.4.3 Qualification Completion + Approval Readiness
        run: python automation/v92/paper_trading_phase343_approval_readiness.py

      - name: Upload Phase 3.4.3 diagnostics
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase343-approval-readiness-${{ github.run_id }}
          path: |
            phase34_result.json
            phase34_summary.md
            phase342_output/
            phase343_output/
          if-no-files-found: warn
          retention-days: 30
'@

[System.IO.File]::WriteAllText($pyPath, $python, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($ymlPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Created:"
Write-Host "  $pyPath"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.3 DEPLOYMENT READY"
Write-Host "============================================================"
Write-Host ""
Write-Host "Behavior:"
Write-Host "  < 5 PASS days  -> OBSERVATION / NOT_READY / LOCKED"
Write-Host "  >=5 PASS days  -> QUALIFIED / READY_FOR_HUMAN_APPROVAL / LOCKED"
Write-Host "  Invalid source -> BLOCKED / FAIL-CLOSED / LOCKED"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Automatic approval: DISABLED"
Write-Host "  Broker trading: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host ""
Write-Host "Next:"
Write-Host "  GitHub Desktop -> Commit -> Push origin"
Write-Host "  GitHub Actions -> Phase 3.4.3 -> Run workflow -> V9.1"
