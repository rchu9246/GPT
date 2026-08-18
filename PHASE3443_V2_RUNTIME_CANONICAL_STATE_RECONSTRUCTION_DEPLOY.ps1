$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.4.3 v2"
Write-Host " Runtime Canonical State Reconstruction"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$bridgePy = Join-Path $automationDir "paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
$gatePy = Join-Path $automationDir "paper_trading_phase344_human_approval_readiness_gate.py"
$workflowPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase3443-runtime-canonical-state-reconstruction.yml"

if (-not (Test-Path $gatePy)) {
    throw "Missing Phase 3.4.4 gate: $gatePy"
}

$backup = "$gatePy.pre3443v2.bak"
if (-not (Test-Path $backup)) {
    Copy-Item $gatePy $backup
}

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE344_REQUIRED_PASS_DAYS", "5"))

PHASE3421 = ROOT / "automation/v92/paper_trading_phase3421_market_state_persistence_fix.py"
PHASE3421_JSON = ROOT / "phase3421_output/market_state.json"

PHASE342_GUARD = ROOT / "automation/v92/paper_trading_phase342_qualification_state_fix.py"
PHASE342_SUMMARY = ROOT / "phase342_output/phase342_summary.json"

OUT3442 = ROOT / "phase3442_output"
OUT344 = ROOT / "phase344_output"

OUT3442.mkdir(exist_ok=True)
OUT344.mkdir(exist_ok=True)

def run_python(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing required engine: {path}")

    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PAPER_TRADING_MODE"] = MODE
    env["PHASE3421_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE344_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    p = subprocess.run(
        [sys.executable, str(path)],
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
        raise RuntimeError(f"{path.name} failed with exit code {p.returncode}")

def load_json(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing JSON evidence: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON object: {path}")
    return data

def normalize_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return str(value).strip().lower() in ("true", "1", "yes", "y")

def reconstruct_state():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    # Step 1: rebuild current market state + pass-day evidence in THIS runner.
    run_python(PHASE3421)
    market = load_json(PHASE3421_JSON)

    if market.get("status") != "PASS":
        raise RuntimeError("Phase 3.4.2.1 market bridge is not PASS")

    latest_market_date = market.get("latest_market_date")
    market_stale_days = market.get("market_stale_days")
    pass_days = market.get("consecutive_pass_days")
    pass_source = market.get("pass_day_source") or "distinct_run_date_snapshot_status"

    if latest_market_date is None or market_stale_days is None:
        raise RuntimeError("Missing current canonical market date/staleness")
    if pass_days is None:
        raise RuntimeError("Missing current canonical consecutive_pass_days")

    pass_days = int(pass_days)

    # Step 2: rebuild canonical qualification guard in THIS runner if available.
    guard = {}
    if PHASE342_GUARD.exists():
        run_python(PHASE342_GUARD)
        if PHASE342_SUMMARY.exists():
            guard = load_json(PHASE342_SUMMARY)

    guard_pass = guard.get("consecutive_pass_days")
    if guard_pass is not None:
        pass_days = max(pass_days, int(guard_pass))

    guard_source_valid = guard.get("canonical_source_valid")
    if guard_source_valid is None:
        guard_source_valid = guard.get("source_valid")
    if guard_source_valid is False:
        raise RuntimeError("Canonical qualification guard reports invalid source")

    required = REQUIRED_PASS_DAYS
    remaining = max(required - pass_days, 0)
    qualified = pass_days >= required

    state = {
        "version": "3.4.4.3-v2",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,

        "reconstruction_contract": "RUNTIME_REBUILD_PHASE3421_PLUS_CANONICAL_GUARD",
        "qualification_state": "QUALIFIED" if qualified else "OBSERVATION",
        "approval_readiness": "READY_FOR_HUMAN_APPROVAL" if qualified else "NOT_READY",
        "human_approval_gate_state": "OPEN_FOR_HUMAN_REVIEW" if qualified else "CLOSED_WAITING_FOR_QUALIFICATION",

        "pass_day_source": pass_source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": required,
        "remaining_pass_days": remaining,

        "latest_market_date": latest_market_date,
        "market_stale_days": int(market_stale_days),
        "canonical_source_valid": True,

        "release_state": "LOCKED",
        "release_authorized": False,
        "release_locked_before_human_approval": True,
        "human_approval_required": True,
        "human_approval_recorded": False,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "fail_closed": True,
    }

    return state

def persist(state):
    # Persist a Phase 3.4.4.2-compatible artifact in the same runner.
    (OUT3442 / "phase3442_sync.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Persist the Phase 3.4.4 gate-ready state.
    (OUT344 / "phase344_readiness.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.4.3 v2",
        "",
        "## Runtime Canonical State Reconstruction",
        "",
        "- Status: **PASS**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- Reconstruction Contract: **{state['reconstruction_contract']}**",
        f"- Qualification State: **{state['qualification_state']}**",
        f"- Approval Readiness: **{state['approval_readiness']}**",
        f"- Human Approval Gate: **{state['human_approval_gate_state']}**",
        f"- PASS-day Source: `{state['pass_day_source']}`",
        f"- Consecutive PASS days: **{state['consecutive_pass_days']} / {state['required_pass_days']}**",
        f"- Remaining PASS days: **{state['remaining_pass_days']}**",
        f"- Latest market date: `{state['latest_market_date']}`",
        f"- Market stale days: `{state['market_stale_days']}`",
        "- Canonical source valid: **YES**",
        "",
        "### Release Safety",
        "",
        "- Release State: **LOCKED**",
        "- Release locked before human approval: **YES**",
        "- Release authorized: **NO**",
        "- Human approval required: **YES**",
        "- Human approval recorded: **NO**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- No cross-workflow artifact dependency is required.",
    ]

    (OUT344 / "phase344_readiness.md").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")

def main():
    state = reconstruct_state()
    persist(state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'@

$patchedGate = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.4
Human Approval Readiness Gate
Patched by Phase 3.4.4.3 v2 Runtime Canonical State Reconstruction.

This gate rebuilds canonical state in the same runner.
It NEVER authorizes release and NEVER enables broker/live-money trading.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py"

def main():
    if not BRIDGE.exists():
        raise RuntimeError(f"Missing runtime reconstruction engine: {BRIDGE}")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = "SHADOW_ONLY_NO_BROKER"

    p = subprocess.run(
        [sys.executable, str(BRIDGE)],
        cwd=str(ROOT),
        env=env,
        text=True,
    )

    return p.returncode

if __name__ == "__main__":
    raise SystemExit(main())
'@

$workflow = @'
name: GPT Quant Phase 3.4.4.3 v2 - Runtime Canonical State Reconstruction

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase3443-v2-runtime-reconstruction
  cancel-in-progress: false

jobs:
  runtime-canonical-reconstruction:
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

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependency
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.4.4.3 v2 safety boundary
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          test -f automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          test -f automation/v92/paper_trading_phase344_human_approval_readiness_gate.py

          grep -q RUNTIME_REBUILD_PHASE3421_PLUS_CANONICAL_GUARD automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          grep -q '"release_state": "LOCKED"' automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          grep -q '"release_authorized": False' automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          grep -q '"release_locked_before_human_approval": True' automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          grep -q '"automatic_approval": False' automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          grep -q '"broker_trading_enabled": False' automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          grep -q '"real_money_trading_enabled": False' automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

      - name: Run Phase 3.4.4.3 v2 Runtime Canonical State Reconstruction
        run: python automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

      - name: Upload Phase 3.4.4.3 v2 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3443-v2-runtime-canonical-state-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
          if-no-files-found: warn
          retention-days: 30
'@

[System.IO.File]::WriteAllText($bridgePy, $python, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($gatePy, $patchedGate, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($workflowPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.4.3 v2 READY"
Write-Host "============================================================"
Write-Host "Created:"
Write-Host "  automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3443-runtime-canonical-state-reconstruction.yml"
Write-Host ""
Write-Host "Overwritten:"
Write-Host "  automation/v92/paper_trading_phase344_human_approval_readiness_gate.py"
Write-Host ""
Write-Host "Backup:"
Write-Host "  automation/v92/paper_trading_phase344_human_approval_readiness_gate.py.pre3443v2.bak"
Write-Host ""
Write-Host "v2 behavior:"
Write-Host "  Rebuilds canonical market + PASS state in the SAME GitHub runner"
Write-Host "  No dependency on a previous workflow's local phase3442_output file"
Write-Host "  Recreates phase3442_sync.json for compatibility"
Write-Host "  Produces Phase 3.4.4 gate-ready evidence directly"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Release LOCKED"
Write-Host "  Release authorization DISABLED"
Write-Host "  Human approval REQUIRED"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
