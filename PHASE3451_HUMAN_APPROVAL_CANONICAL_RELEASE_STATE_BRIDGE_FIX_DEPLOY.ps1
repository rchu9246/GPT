#requires -Version 5.1
<#
PHASE3451_HUMAN_APPROVAL_CANONICAL_RELEASE_STATE_BRIDGE_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.5.1 — Human Approval Canonical Release State Bridge Fix

Purpose
-------
Fix the bridge between a valid Phase 3.4.4.3 canonical readiness state and the
Phase 3.4.5 human decision so that:

  QUALIFIED
  + READY_FOR_HUMAN_APPROVAL
  + OPEN_FOR_HUMAN_REVIEW
  + canonical_source_valid = true
  + APPROVE
  + exact confirmation phrase
  + non-empty approver

becomes:

  human_approval_recorded = true
  production_paper_activation_authorized = true
  production_paper_release_state = ACTIVE

REJECT always remains LOCKED.

Safety boundary
---------------
- Production Paper only.
- Automatic approval remains disabled.
- Broker trading remains disabled.
- Broker order submission remains disabled.
- Real-money trading remains disabled.
- Live-money release remains unauthorized.
- Any missing/inconsistent canonical evidence fails closed.

This deployer creates/overwrites:
  automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase3451-human-approval-canonical-release-state-bridge-fix.yml

It does NOT delete or weaken Phase 3.4.5.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Write-Section "GPT Quant V9.2 — Phase 3.4.5.1 Deploy"

# Resolve repository root from current directory.
$repoRoot = $null
try {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repoRoot = $null
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    Fail "This script must be run inside the GPT Git repository."
}

Set-Location $repoRoot
Write-Host "Repository: $repoRoot" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py",
    "automation/v92/paper_trading_phase345_human_approval_production_paper_activation.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase3451-human-approval-canonical-release-state-bridge-fix.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase3451-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Write-Section "Writing Phase 3.4.5.1 Python bridge"

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
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase3451_output"
COMPAT_OUT = ROOT / "phase345_output"
OUT.mkdir(exist_ok=True)
COMPAT_OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE345_REQUIRED_PASS_DAYS", "5"))

RECONSTRUCT = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
)
READINESS_JSON = ROOT / "phase344_output/phase344_readiness.json"

APPROVE_PHRASE = "I APPROVE PRODUCTION PAPER ONLY"
REJECT_PHRASE = "I REJECT PRODUCTION PAPER"

SAFETY_CONTRACT = "PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY"
BRIDGE_CONTRACT = "PHASE3451_CANONICAL_READINESS_TO_HUMAN_DECISION_RELEASE_BRIDGE"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing JSON evidence: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON object: {path}")
    return data


def evidence_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def run_reconstruction() -> None:
    if not RECONSTRUCT.exists():
        raise RuntimeError(f"Missing reconstruction engine: {RECONSTRUCT}")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE344_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE3421_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    proc = subprocess.run(
        [sys.executable, str(RECONSTRUCT)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Canonical reconstruction failed with exit code {proc.returncode}"
        )


def canonical_gate(readiness: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []

    checks = [
        (
            readiness.get("status") == "PASS",
            f"status={readiness.get('status')!r}, expected 'PASS'",
        ),
        (
            readiness.get("canonical_source_valid") is True,
            "canonical_source_valid is not true",
        ),
        (
            readiness.get("qualification_state") == "QUALIFIED",
            (
                "qualification_state="
                f"{readiness.get('qualification_state')!r}, expected 'QUALIFIED'"
            ),
        ),
        (
            readiness.get("approval_readiness") == "READY_FOR_HUMAN_APPROVAL",
            (
                "approval_readiness="
                f"{readiness.get('approval_readiness')!r}, "
                "expected 'READY_FOR_HUMAN_APPROVAL'"
            ),
        ),
        (
            readiness.get("human_approval_gate_state") == "OPEN_FOR_HUMAN_REVIEW",
            (
                "human_approval_gate_state="
                f"{readiness.get('human_approval_gate_state')!r}, "
                "expected 'OPEN_FOR_HUMAN_REVIEW'"
            ),
        ),
    ]

    for ok, message in checks:
        if not ok:
            failures.append(message)

    try:
        pass_days = int(readiness.get("consecutive_pass_days") or 0)
    except (TypeError, ValueError):
        pass_days = 0
        failures.append("consecutive_pass_days is not a valid integer")

    if pass_days < REQUIRED_PASS_DAYS:
        failures.append(
            f"consecutive_pass_days={pass_days}, required={REQUIRED_PASS_DAYS}"
        )

    if not readiness.get("latest_market_date"):
        failures.append("latest_market_date is missing")

    # IMPORTANT:
    # release_state=LOCKED and release_authorized=false are EXPECTED here.
    # This is the pre-human-approval canonical state and must NOT be treated
    # as a reason to reject an otherwise valid human APPROVE decision.
    return (len(failures) == 0, failures)


def persist(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = evidence_hash(result)

    json_text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (OUT / "phase3451_decision.json").write_text(json_text, encoding="utf-8")

    # Compatibility mirror so existing Phase 3.4.5 consumers can read the
    # post-bridge decision schema without any cross-workflow artifact.
    (COMPAT_OUT / "phase345_decision.json").write_text(json_text, encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.5.1",
        "",
        "## Human Approval Canonical Release State Bridge Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Bridge Contract: **{result['bridge_contract']}**",
        f"- Canonical Source Valid: **{'YES' if result['canonical_source_valid'] else 'NO'}**",
        f"- Qualification State: **{result['qualification_state']}**",
        f"- Approval Readiness: **{result['approval_readiness']}**",
        f"- Human Approval Gate: **{result['human_approval_gate_state']}**",
        (
            "- Consecutive PASS days: "
            f"**{result['consecutive_pass_days']} / {result['required_pass_days']}**"
        ),
        f"- Latest Market Date: `{result['latest_market_date']}`",
        "",
        "### Canonical State Bridge",
        "",
        f"- Canonical Gate Eligible: **{'YES' if result['canonical_gate_eligible'] else 'NO'}**",
        f"- Pre-Human Release State: **{result['canonical_release_state_before']}**",
        (
            "- Pre-Human Release Authorized: "
            f"**{'YES' if result['canonical_release_authorized_before'] else 'NO'}**"
        ),
        f"- Human Decision: **{result['human_decision']}**",
        f"- Approver: `{result['human_approver']}`",
        (
            "- Human Approval Recorded: "
            f"**{'YES' if result['human_approval_recorded'] else 'NO'}**"
        ),
        (
            "- Human Rejection Recorded: "
            f"**{'YES' if result['human_rejection_recorded'] else 'NO'}**"
        ),
        (
            "- Production Paper Activation Authorized: "
            f"**{'YES' if result['production_paper_activation_authorized'] else 'NO'}**"
        ),
        (
            "- Production Paper Release: "
            f"**{result['production_paper_release_state']}**"
        ),
        f"- Transition: `{result['release_transition']}`",
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
        "- Fail-closed policy: **ENABLED**",
        (
            "- Fail-closed triggered: "
            f"**{'YES' if result['fail_closed_triggered'] else 'NO'}**"
        ),
    ]

    if result.get("errors"):
        summary.extend(["", "### Errors", ""])
        summary.extend(f"- {item}" for item in result["errors"])

    md_text = "\n".join(summary) + "\n"
    (OUT / "phase3451_decision.md").write_text(md_text, encoding="utf-8")
    (COMPAT_OUT / "phase345_decision.md").write_text(md_text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(md_text)


def build_fail_closed_result(
    *,
    decision: str,
    approver: str,
    note: str,
    readiness: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    try:
        pass_days = int(readiness.get("consecutive_pass_days") or 0)
    except (TypeError, ValueError):
        pass_days = 0

    return {
        "version": "3.4.5.1",
        "status": "BLOCKED",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "bridge_contract": BRIDGE_CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "canonical_source_valid": readiness.get("canonical_source_valid") is True,
        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "human_approval_gate_state": readiness.get("human_approval_gate_state"),
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": readiness.get("latest_market_date"),
        "market_stale_days": readiness.get("market_stale_days"),
        "canonical_gate_eligible": False,
        "canonical_release_state_before": readiness.get("release_state", "LOCKED"),
        "canonical_release_authorized_before": bool(
            readiness.get("release_authorized", False)
        ),
        "human_decision": decision,
        "human_approver": approver,
        "human_approval_recorded": False,
        "human_rejection_recorded": decision == "REJECT",
        "approval_note": note,
        "production_paper_release_state": "LOCKED",
        "production_paper_activation_authorized": False,
        "release_transition": "BLOCKED_FAIL_CLOSED",
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": True,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    parser.add_argument("--approver", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    decision = args.decision.strip().upper()
    approver = args.approver.strip()
    confirmation = args.confirmation.strip()
    note = args.note.strip()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation: mode must remain SHADOW_ONLY_NO_BROKER")

    # Rebuild readiness in this same runner. No cross-workflow artifact dependency.
    run_reconstruction()
    readiness = load_json(READINESS_JSON)

    gate_ok, gate_failures = canonical_gate(readiness)

    expected_confirmation = (
        APPROVE_PHRASE if decision == "APPROVE" else REJECT_PHRASE
    )

    input_failures: list[str] = []
    if not approver:
        input_failures.append("Human approver must not be empty")
    if confirmation != expected_confirmation:
        input_failures.append(
            "Confirmation phrase mismatch; expected exactly: "
            f"{expected_confirmation}"
        )

    failures = gate_failures + input_failures
    if failures:
        result = build_fail_closed_result(
            decision=decision,
            approver=approver,
            note=note,
            readiness=readiness,
            errors=failures,
        )
        persist(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            "PHASE3451 BLOCKED / FAIL-CLOSED: " + "; ".join(failures),
            file=sys.stderr,
        )
        return 2

    pass_days = int(readiness.get("consecutive_pass_days") or 0)
    approved = decision == "APPROVE"

    # THE 3.4.5.1 BRIDGE:
    # The reconstructed canonical readiness intentionally arrives LOCKED before
    # human approval. A valid APPROVE is the ONLY event that transitions the
    # Production Paper release state to ACTIVE.
    release_state = "ACTIVE" if approved else "LOCKED"
    release_authorized = approved
    transition = (
        "LOCKED_TO_ACTIVE_BY_EXPLICIT_HUMAN_APPROVAL"
        if approved
        else "LOCKED_TO_LOCKED_BY_EXPLICIT_HUMAN_REJECTION"
    )

    result: dict[str, Any] = {
        "version": "3.4.5.1",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "bridge_contract": BRIDGE_CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "canonical_source_valid": True,
        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "human_approval_gate_state": readiness.get("human_approval_gate_state"),
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": readiness.get("latest_market_date"),
        "market_stale_days": readiness.get("market_stale_days"),
        "canonical_gate_eligible": True,

        # Preserve the reconstructed pre-human state as evidence.
        "canonical_release_state_before": readiness.get("release_state", "LOCKED"),
        "canonical_release_authorized_before": bool(
            readiness.get("release_authorized", False)
        ),
        "release_locked_before_human_approval": True,

        # Explicit human decision.
        "human_decision": decision,
        "human_approver": approver,
        "human_approval_recorded": approved,
        "human_rejection_recorded": not approved,
        "approval_note": note,

        # Post-human Production Paper state.
        "production_paper_release_state": release_state,
        "production_paper_activation_authorized": release_authorized,
        "release_transition": transition,

        # Hard safety locks — never changed by APPROVE.
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,

        # Policy is always enabled; it is not triggered on a valid decision.
        "fail_closed_policy": True,
        "fail_closed_triggered": False,
        "errors": [],
    }

    persist(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if approved:
        print(
            "PHASE3451 PASS: explicit human APPROVE bridged canonical "
            "readiness to Production Paper ACTIVE; broker/live-money remain disabled."
        )
    else:
        print(
            "PHASE3451 PASS: explicit human REJECT preserved Production Paper LOCKED."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Write-Section "Writing Phase 3.4.5.1 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.5.1 - Human Approval Canonical Release State Bridge Fix

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
  group: gpt-quant-phase3451-human-approval-canonical-release-bridge
  cancel-in-progress: false

jobs:
  human-approval-canonical-release-bridge:
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

      - name: Validate Phase 3.4.5.1 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py
          test -f automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q 'PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY' \
            automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py

          grep -q '"automatic_approval": False' \
            automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py

          grep -q '"broker_trading_enabled": False' \
            automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py

          grep -q '"live_money_release_authorized": False' \
            automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py

          echo "Phase 3.4.5.1 safety contract: PASS"

      - name: Execute Phase 3.4.5.1 human approval bridge
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py \
            --decision "${{ inputs.decision }}" \
            --approver "${{ inputs.approver }}" \
            --confirmation "${{ inputs.confirmation }}" \
            --note "${{ inputs.note }}"

      - name: Validate Phase 3.4.5.1 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase3451_output/phase3451_decision.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase3451_output/phase3451_decision.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.5.1", data
          assert data["status"] == "PASS", data
          assert data["canonical_source_valid"] is True, data
          assert data["canonical_gate_eligible"] is True, data
          assert data["qualification_state"] == "QUALIFIED", data
          assert data["approval_readiness"] == "READY_FOR_HUMAN_APPROVAL", data
          assert data["human_approval_gate_state"] == "OPEN_FOR_HUMAN_REVIEW", data

          # These are intentionally hard-disabled even after APPROVE.
          assert data["automatic_approval"] is False, data
          assert data["broker_trading_enabled"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data
          assert data["fail_closed_triggered"] is False, data

          if data["human_decision"] == "APPROVE":
              assert data["human_approval_recorded"] is True, data
              assert data["human_rejection_recorded"] is False, data
              assert data["production_paper_release_state"] == "ACTIVE", data
              assert data["production_paper_activation_authorized"] is True, data
              assert (
                  data["release_transition"]
                  == "LOCKED_TO_ACTIVE_BY_EXPLICIT_HUMAN_APPROVAL"
              ), data
          else:
              assert data["human_approval_recorded"] is False, data
              assert data["human_rejection_recorded"] is True, data
              assert data["production_paper_release_state"] == "LOCKED", data
              assert data["production_paper_activation_authorized"] is False, data
              assert (
                  data["release_transition"]
                  == "LOCKED_TO_LOCKED_BY_EXPLICIT_HUMAN_REJECTION"
              ), data

          print("Phase 3.4.5.1 output validation: PASS")
          PY

      - name: Upload Phase 3.4.5.1 approval evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3451-human-approval-bridge-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
            phase345_output/
            phase3451_output/
          if-no-files-found: warn
          retention-days: 90
'@

Set-Content -LiteralPath $workflowTarget -Value $workflow -Encoding UTF8
Write-Host "Wrote: $workflowTarget" -ForegroundColor Green

Write-Section "Static validation"

$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} else {
    Fail "Python was not found in PATH. Files were written, but compile validation could not run."
}

if ($pythonCmd -eq "py") {
    & py -3 -m py_compile $pythonTarget
} else {
    & python -m py_compile $pythonTarget
}

if ($LASTEXITCODE -ne 0) {
    Fail "Python compile validation failed."
}
Write-Host "Python compile: PASS" -ForegroundColor Green

# Strict textual safety checks locally.
$source = Get-Content -LiteralPath $pythonTarget -Raw
$safetyNeedles = @(
    '"automatic_approval": False',
    '"broker_trading_enabled": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False',
    '"live_money_release_authorized": False',
    'PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY',
    'LOCKED_TO_ACTIVE_BY_EXPLICIT_HUMAN_APPROVAL'
)

foreach ($needle in $safetyNeedles) {
    if (-not $source.Contains($needle)) {
        Fail "Safety/bridge token missing from Python file: $needle"
    }
}
Write-Host "Safety token scan: PASS" -ForegroundColor Green

Write-Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Write-Section "DEPLOY COMPLETE"
Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Review GitHub Desktop changes."
Write-Host "  2) Commit and Push origin."
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.5.1"
Write-Host "  4) First run REJECT safety path:"
Write-Host '       decision     = REJECT'
Write-Host '       confirmation = I REJECT PRODUCTION PAPER'
Write-Host "  5) Then run APPROVE bridge path:"
Write-Host '       decision     = APPROVE'
Write-Host '       confirmation = I APPROVE PRODUCTION PAPER ONLY'
Write-Host ""
Write-Host "Expected APPROVE result:" -ForegroundColor Cyan
Write-Host "  Human Approval Recorded: YES"
Write-Host "  Production Paper Activation Authorized: YES"
Write-Host "  Production Paper Release: ACTIVE"
Write-Host "  Broker trading: DISABLED"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host ""
Write-Host "Backup folder (only if prior targets existed): $backupRoot" -ForegroundColor DarkGray
