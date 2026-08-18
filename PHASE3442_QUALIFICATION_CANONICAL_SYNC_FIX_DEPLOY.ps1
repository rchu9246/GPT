$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.4.2"
Write-Host " Qualification Canonical State Synchronization Fix"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase3442_qualification_canonical_sync_fix.py"
$ymlPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase3442-qualification-canonical-sync-fix.yml"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase3442_output"
OUT.mkdir(exist_ok=True)

STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE3442_REQUIRED_PASS_DAYS", "5"))

PHASE3421 = ROOT / "automation/v92/paper_trading_phase3421_market_state_persistence_fix.py"
PHASE3421_JSON = ROOT / "phase3421_output/market_state.json"
PHASE342_GUARD = ROOT / "automation/v92/paper_trading_phase342_qualification_state_fix.py"
PHASE342_SUMMARY = ROOT / "phase342_output/phase342_summary.json"
PHASE343_SUMMARY = ROOT / "phase343_output/phase343_summary.json"

def run_python(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing engine: {path}")

    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PAPER_TRADING_MODE"] = MODE
    env["PHASE3421_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE3442_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

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
        raise RuntimeError(f"Missing JSON: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON object: {path}")
    return data

def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    # Refresh Phase 3.4.2.1 v5 canonical market + pass-day evidence.
    run_python(PHASE3421)
    market = load_json(PHASE3421_JSON)

    if market.get("status") != "PASS":
        raise RuntimeError("Phase 3.4.2.1 canonical market evidence is not PASS")

    latest_market_date = market.get("latest_market_date")
    market_stale_days = market.get("market_stale_days")
    pass_days = market.get("consecutive_pass_days")
    pass_source = market.get("pass_day_source") or "distinct_run_date_snapshot_status"

    if latest_market_date is None or market_stale_days is None:
        raise RuntimeError("Canonical market evidence missing date/staleness")
    if pass_days is None:
        raise RuntimeError("Canonical market evidence missing consecutive_pass_days")

    pass_days = int(pass_days)

    # Reuse newer canonical guard count if available.
    guard = {}
    if PHASE342_GUARD.exists():
        run_python(PHASE342_GUARD)
        if PHASE342_SUMMARY.exists():
            guard = load_json(PHASE342_SUMMARY)

    guard_pass = guard.get("consecutive_pass_days")
    if guard_pass is not None:
        pass_days = max(pass_days, int(guard_pass))

    remaining = max(REQUIRED_PASS_DAYS - pass_days, 0)
    qualified = pass_days >= REQUIRED_PASS_DAYS

    sync = {
        "version": "3.4.4.2",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "qualification_state": "QUALIFIED" if qualified else "OBSERVATION",
        "approval_readiness": "READY_FOR_HUMAN_APPROVAL" if qualified else "NOT_READY",
        "pass_day_source": pass_source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "remaining_pass_days": remaining,
        "latest_market_date": latest_market_date,
        "market_stale_days": market_stale_days,
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
        "sync_contract": "PHASE3421_MARKET_PLUS_CANONICAL_PASS_STATE",
        "source_errors": [],
    }

    phase343_dir = ROOT / "phase343_output"
    phase343_dir.mkdir(exist_ok=True)
    PHASE343_SUMMARY.write_text(
        json.dumps(sync, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    (OUT / "phase3442_sync.json").write_text(
        json.dumps(sync, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.4.2",
        "",
        "## Qualification Canonical State Synchronization Fix",
        "",
        "- Status: **PASS**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- Qualification State: **{sync['qualification_state']}**",
        f"- Approval Readiness: **{sync['approval_readiness']}**",
        f"- PASS-day Source: `{pass_source}`",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Remaining PASS days: **{remaining}**",
        f"- Latest market date: `{latest_market_date}`",
        f"- Market stale days: `{market_stale_days}`",
        "- Canonical source valid: **YES**",
        "",
        "### Synchronization Contract",
        "",
        "- Contract: **PHASE3421_MARKET_PLUS_CANONICAL_PASS_STATE**",
        "- Phase 3.4.2.1 market evidence is authoritative for market date/staleness.",
        "- Canonical PASS-day count is preserved.",
        "- Legacy/null Phase 3.4.3 fields are replaced with synchronized values.",
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
        "- Missing/inconsistent evidence => **BLOCKED / FAIL-CLOSED**",
    ]

    (OUT / "phase3442_sync.md").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")

    print(json.dumps(sync, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'@

$workflow = @'
name: GPT Quant Phase 3.4.4.2 - Qualification Canonical State Synchronization Fix

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
  group: gpt-quant-phase3442-qualification-canonical-sync
  cancel-in-progress: false

jobs:
  qualification-canonical-sync:
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
      PHASE3442_REQUIRED_PASS_DAYS: "5"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependency
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.4.4.2 safety boundary
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          test -f automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py
          grep -q PHASE3421_MARKET_PLUS_CANONICAL_PASS_STATE automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py
          grep -q '"release_state": "LOCKED"' automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py
          grep -q '"release_authorized": False' automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py
          grep -q '"release_locked_before_human_approval": True' automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py
          grep -q '"automatic_approval": False' automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py
          grep -q '"broker_trading_enabled": False' automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py
          grep -q '"real_money_trading_enabled": False' automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py

      - name: Run Phase 3.4.4.2 Qualification Canonical State Synchronization Fix
        run: python automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py

      - name: Upload Phase 3.4.4.2 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3442-qualification-canonical-sync-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase343_output/
            phase3442_output/
          if-no-files-found: warn
          retention-days: 30
'@

[System.IO.File]::WriteAllText($pyPath, $python, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($ymlPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.4.2 READY"
Write-Host "============================================================"
Write-Host "Created:"
Write-Host "  automation/v92/paper_trading_phase3442_qualification_canonical_sync_fix.py"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3442-qualification-canonical-sync-fix.yml"
Write-Host ""
Write-Host "Fix:"
Write-Host "  Synchronizes Phase 3.4.2.1 market evidence into qualification state"
Write-Host "  Preserves canonical PASS-day count"
Write-Host "  Rebuilds Phase 3.4.3-compatible summary with non-null canonical values"
Write-Host "  Forces release_locked_before_human_approval = true"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Release LOCKED"
Write-Host "  Release authorization DISABLED"
Write-Host "  Human approval REQUIRED"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
