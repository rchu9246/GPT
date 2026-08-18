$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.5"
Write-Host " Human Approval Decision + Production Paper Activation"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase345_human_approval_production_paper_activation.py"
$workflowPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase345-human-approval-production-paper-activation.yml"
$gatePath = Join-Path $automationDir "paper_trading_phase344_human_approval_readiness_gate.py"
$reconstructPath = Join-Path $automationDir "paper_trading_phase3443_runtime_canonical_state_reconstruction.py"

if (-not (Test-Path $gatePath)) {
    throw "Missing Phase 3.4.4 gate: $gatePath"
}

if (-not (Test-Path $reconstructPath)) {
    throw "Missing Phase 3.4.4.3 runtime reconstruction engine: $reconstructPath"
}

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase345_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
REQUIRED_PASS_DAYS = int(os.getenv("PHASE345_REQUIRED_PASS_DAYS", "5"))

RECONSTRUCT = ROOT / "automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
READINESS_JSON = ROOT / "phase344_output/phase344_readiness.json"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run_reconstruction():
    if not RECONSTRUCT.exists():
        raise RuntimeError(f"Missing reconstruction engine: {RECONSTRUCT}")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE344_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    p = subprocess.run(
        [sys.executable, str(RECONSTRUCT)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)

    if p.returncode != 0:
        raise RuntimeError(f"Canonical reconstruction failed with exit code {p.returncode}")

def load_json(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing readiness evidence: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid readiness JSON: {path}")
    return data

def evidence_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    parser.add_argument("--approver", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    run_reconstruction()
    readiness = load_json(READINESS_JSON)

    if readiness.get("status") != "PASS":
        raise RuntimeError("Readiness status is not PASS")
    if readiness.get("canonical_source_valid") is not True:
        raise RuntimeError("Canonical source invalid")
    if readiness.get("qualification_state") != "QUALIFIED":
        raise RuntimeError("Qualification state is not QUALIFIED")
    if readiness.get("approval_readiness") != "READY_FOR_HUMAN_APPROVAL":
        raise RuntimeError("Approval readiness is not READY_FOR_HUMAN_APPROVAL")
    if readiness.get("human_approval_gate_state") != "OPEN_FOR_HUMAN_REVIEW":
        raise RuntimeError("Human approval gate is not OPEN_FOR_HUMAN_REVIEW")

    pass_days = int(readiness.get("consecutive_pass_days") or 0)
    if pass_days < REQUIRED_PASS_DAYS:
        raise RuntimeError("Insufficient PASS-day count")

    latest_market_date = readiness.get("latest_market_date")
    if not latest_market_date:
        raise RuntimeError("Missing latest_market_date")

    expected_confirmation = (
        "I APPROVE PRODUCTION PAPER ONLY"
        if args.decision == "APPROVE"
        else "I REJECT PRODUCTION PAPER"
    )

    if args.confirmation.strip() != expected_confirmation:
        raise RuntimeError(
            "Confirmation phrase mismatch. "
            f"Expected exactly: {expected_confirmation}"
        )

    approved = args.decision == "APPROVE"

    # IMPORTANT:
    # Approval only activates PRODUCTION PAPER.
    # Broker and real-money execution remain hard-disabled.
    result = {
        "version": "3.4.5",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,

        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "human_approval_gate_state": readiness.get("human_approval_gate_state"),
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": latest_market_date,
        "market_stale_days": readiness.get("market_stale_days"),
        "canonical_source_valid": True,

        "human_decision": args.decision,
        "human_approver": args.approver,
        "human_approval_recorded": approved,
        "human_rejection_recorded": not approved,
        "approval_note": args.note,

        "production_paper_release_state": "ACTIVE" if approved else "LOCKED",
        "production_paper_activation_authorized": approved,

        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "live_money_release_authorized": False,

        "safety_contract": "PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY",
        "fail_closed": True,
    }

    result["evidence_sha256"] = evidence_hash(result)

    (OUT / "phase345_decision.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.5",
        "",
        "## Human Approval Decision + Production Paper Activation",
        "",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- Qualification State: **{result['qualification_state']}**",
        f"- Approval Readiness: **{result['approval_readiness']}**",
        f"- Human Approval Gate: **{result['human_approval_gate_state']}**",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Latest market date: `{latest_market_date}`",
        f"- Canonical source valid: **YES**",
        "",
        "### Human Decision",
        "",
        f"- Decision: **{args.decision}**",
        f"- Approver: `{args.approver}`",
        f"- Human approval recorded: **{'YES' if approved else 'NO'}**",
        f"- Production Paper Release: **{'ACTIVE' if approved else 'LOCKED'}**",
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
        "",
        "### Safety Boundary",
        "",
        "- Production Paper only: **YES**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Broker order submission: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Live-money release authorized: **NO**",
        "- Missing/inconsistent evidence => **BLOCKED / FAIL-CLOSED**",
    ]

    (OUT / "phase345_decision.md").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'@

$workflow = @'
name: GPT Quant Phase 3.4.5 - Human Approval + Production Paper Activation

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string

      decision:
        description: Human decision
        required: true
        type: choice
        options:
          - REJECT
          - APPROVE
        default: REJECT

      approver:
        description: Human approver name or operator ID
        required: true
        type: string

      confirmation:
        description: For APPROVE type exactly "I APPROVE PRODUCTION PAPER ONLY"; for REJECT type exactly "I REJECT PRODUCTION PAPER"
        required: true
        type: string

      note:
        description: Optional approval/rejection note
        required: false
        default: ""
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase345-human-approval-production-paper
  cancel-in-progress: false

jobs:
  human-approval-production-paper:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE3421_REQUIRED_PASS_DAYS: "5"
      PHASE344_REQUIRED_PASS_DAYS: "5"
      PHASE345_REQUIRED_PASS_DAYS: "5"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependency
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.4.5 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py
          test -f automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY \
            automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py

          grep -q '"automatic_approval": False' \
            automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py

          grep -q '"broker_trading_enabled": False' \
            automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py

          grep -q '"live_money_release_authorized": False' \
            automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py

          echo "Phase 3.4.5 safety contract: PASS"

      - name: Execute human approval decision
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py \
            --decision "${{ inputs.decision }}" \
            --approver "${{ inputs.approver }}" \
            --confirmation "${{ inputs.confirmation }}" \
            --note "${{ inputs.note }}"

      - name: Validate Phase 3.4.5 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase345_output/phase345_decision.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase345_output/phase345_decision.json").read_text(encoding="utf-8")
          )

          assert data["canonical_source_valid"] is True, data
          assert data["automatic_approval"] is False, data
          assert data["broker_trading_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data

          if data["human_decision"] == "APPROVE":
              assert data["production_paper_release_state"] == "ACTIVE", data
              assert data["production_paper_activation_authorized"] is True, data
              assert data["human_approval_recorded"] is True, data
          else:
              assert data["production_paper_release_state"] == "LOCKED", data
              assert data["production_paper_activation_authorized"] is False, data

          print("Phase 3.4.5 output validation: PASS")
          PY

      - name: Upload Phase 3.4.5 approval evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase345-human-approval-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
            phase345_output/
          if-no-files-found: warn
          retention-days: 90
'@

[System.IO.File]::WriteAllText($pyPath, $python, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($workflowPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.5 READY"
Write-Host "============================================================"
Write-Host "Created:"
Write-Host "  automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase345-human-approval-production-paper-activation.yml"
Write-Host ""
Write-Host "Human decision:"
Write-Host "  APPROVE => activates PRODUCTION PAPER ONLY"
Write-Host "  REJECT  => keeps Production Paper LOCKED"
Write-Host ""
Write-Host "Exact APPROVE confirmation:"
Write-Host '  I APPROVE PRODUCTION PAPER ONLY'
Write-Host ""
Write-Host "Exact REJECT confirmation:"
Write-Host '  I REJECT PRODUCTION PAPER'
Write-Host ""
Write-Host "Safety:"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Broker order submission DISABLED"
Write-Host "  Real-money trading DISABLED"
Write-Host "  Live-money release authorization DISABLED"
Write-Host ""
Write-Host "Next:"
Write-Host "  GitHub Desktop -> Commit -> Push origin"
Write-Host "  Actions -> GPT Quant Phase 3.4.5 - Human Approval + Production Paper Activation"
Write-Host "  Run workflow"
