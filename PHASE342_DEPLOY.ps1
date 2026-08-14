$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant V9.2 Phase 3.4.2 Deployment"
Write-Host " Qualification State Persistence Fix"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase342_qualification_state_fix.py"
$ymlPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase342.yml"

$python = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.2
Qualification State Persistence Fix

Fixes Phase 3.4.1 false-positive behavior:
- Calls Phase 3.4 using the ENV contract it actually expects.
- Reads canonical phase34_result.json instead of scraping stdout.
- Persists qualification state into phase342_output/.
- Fails closed when key qualification fields are missing.
- Never approves/revokes a release.
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
OUTDIR = ROOT / "phase342_output"
OUTDIR.mkdir(exist_ok=True)

VERSION = "3.4.2"
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE342_REQUIRED_PASS_DAYS", "5"))

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

    (OUTDIR / "phase34_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (OUTDIR / "phase34_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")

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
    missing = []
    for field in REQUIRED_FIELDS:
        if field not in data or data[field] is None:
            missing.append(field)

    if missing:
        return False, missing

    if str(data.get("pass_day_source")) != "distinct_run_date_snapshot_status":
        return False, ["pass_day_source_mismatch"]

    if str(data.get("mode")) != MODE:
        return False, ["safety_mode_mismatch"]

    try:
        int(data.get("consecutive_pass_days"))
        int(data.get("market_stale_days"))
    except (TypeError, ValueError):
        return False, ["numeric_qualification_field_invalid"]

    return True, []


def build_summary(data, source_valid, source_errors):
    if source_valid:
        status = str(data.get("status"))
        qualification = str(data.get("qualification_state"))
        release = str(data.get("release_state"))
        pass_days = int(data.get("consecutive_pass_days"))
        latest_market_date = str(data.get("latest_market_date"))
        stale_days = int(data.get("market_stale_days"))
        source = str(data.get("pass_day_source"))
    else:
        status = "BLOCKED"
        qualification = "BLOCKED"
        release = "LOCKED"
        pass_days = None
        latest_market_date = None
        stale_days = None
        source = data.get("pass_day_source") if isinstance(data, dict) else None

    return {
        "version": VERSION,
        "checked_at": now_iso(),
        "status": status,
        "qualification_state": qualification,
        "release_state": release,
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "automation_mode": "DAILY_EVALUATION_ONLY",
        "requested_action": "evaluate",
        "pass_day_source": source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": latest_market_date,
        "market_stale_days": stale_days,
        "source_valid": source_valid,
        "source_errors": source_errors,
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
        f.write("# GPT Quant V9.2 Paper Trading - Phase 3.4.2\n\n")
        f.write("## Qualification State Persistence Fix\n\n")
        f.write(f"- Status: **{val(summary['status'])}**\n")
        f.write(f"- Qualification State: **{val(summary['qualification_state'])}**\n")
        f.write(f"- Release State: **{val(summary['release_state'])}**\n")
        f.write(f"- Strategy: `{summary['strategy_version']}`\n")
        f.write(f"- Trading Mode: `{summary['trading_mode']}`\n")
        f.write(f"- PASS-day Source: `{val(summary['pass_day_source'])}`\n")
        f.write(
            f"- Consecutive PASS days: **{val(summary['consecutive_pass_days'])} / "
            f"{summary['required_pass_days']}**\n"
        )
        f.write(f"- Latest market date: `{val(summary['latest_market_date'])}`\n")
        f.write(f"- Market stale days: `{val(summary['market_stale_days'])}`\n")
        f.write(f"- Canonical source valid: **{'YES' if summary['source_valid'] else 'NO'}**\n")

        if summary["source_errors"]:
            f.write(f"- Source errors: `{', '.join(summary['source_errors'])}`\n")

        f.write("\n### Safety Locks\n\n")
        f.write("- Human approval required: **YES**\n")
        f.write("- Automatic approval: **DISABLED**\n")
        f.write("- Broker trading: **DISABLED**\n")
        f.write("- Real-money trading: **DISABLED**\n")
        f.write("- Missing qualification data => **BLOCKED / FAIL-CLOSED**\n")


def main():
    print("=== GPT Quant V9.2 Phase 3.4.2 Qualification State Persistence Fix ===")
    run_phase34_evaluate()
    data = load_phase34_result()

    source_valid, source_errors = validate_source(data)
    summary = build_summary(data, source_valid, source_errors)

    (OUTDIR / "phase342_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUTDIR / "phase34_canonical_result.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    write_step_summary(summary)

    # Critical fix: never show a green successful qualification state
    # when the canonical Phase 3.4 fields cannot be verified.
    return 0 if source_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
'@

$workflow = @'
name: GPT Quant V9.2 Paper Trading Phase 3.4.2 - Qualification State Persistence Fix

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
  schedule:
    # 09:12 UTC = 17:12 Asia/Taipei, weekdays.
    - cron: "12 9 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-v92-phase342-qualification-state
  cancel-in-progress: false

jobs:
  qualification-state-persistence:
    runs-on: ubuntu-latest
    timeout-minutes: 12

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PHASE342_REQUIRED_PASS_DAYS: "5"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Validate Phase 3.4.2 environment
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase34_human_approval_release.py
          test -f automation/v92/paper_trading_phase342_qualification_state_fix.py

      - name: Run Phase 3.4.2 Qualification State Persistence Fix
        run: python automation/v92/paper_trading_phase342_qualification_state_fix.py

      - name: Upload Phase 3.4.2 diagnostics
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase342-qualification-state-${{ github.run_id }}
          path: |
            phase34_result.json
            phase34_summary.md
            phase342_output/
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
Write-Host " PHASE 3.4.2 DEPLOYMENT READY"
Write-Host "============================================================"
Write-Host ""
Write-Host "Fixes:"
Write-Host "  Reads canonical phase34_result.json"
Write-Host "  Uses PAPER_STRATEGY_VERSION + PHASE34_ACTION=evaluate"
Write-Host "  Persists PASS days / market date / stale days"
Write-Host "  Missing key qualification state => BLOCKED / fail-closed"
Write-Host ""
Write-Host "Next:"
Write-Host "  GitHub Desktop -> Commit -> Push origin"
Write-Host "  GitHub Actions -> Phase 3.4.2 -> Run workflow -> V9.1"
