$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.4.1"
Write-Host " Canonical Market Evidence Consistency Fix"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase3441_canonical_market_evidence_consistency_fix.py"
$ymlPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase3441-canonical-market-evidence-consistency-fix.yml"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase3441_output"
OUT.mkdir(exist_ok=True)

STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"

PHASE3421 = ROOT / "automation/v92/paper_trading_phase3421_market_state_persistence_fix.py"
PHASE3421_JSON = ROOT / "phase3421_output/market_state.json"

PHASE344 = ROOT / "automation/v92/paper_trading_phase344_human_approval_readiness_gate.py"
PHASE344_JSON = ROOT / "phase344_output/phase344_readiness.json"

def run_python(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing engine: {path}")

    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PAPER_TRADING_MODE"] = MODE

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

    # Refresh authoritative market contract.
    run_python(PHASE3421)
    market = load_json(PHASE3421_JSON)

    # Refresh existing readiness gate.
    run_python(PHASE344)
    gate = load_json(PHASE344_JSON)

    if market.get("status") != "PASS":
        raise RuntimeError("Phase 3.4.2.1 canonical market evidence is not PASS")

    latest_market_date = market.get("latest_market_date")
    market_stale_days = market.get("market_stale_days")

    if latest_market_date is None or market_stale_days is None:
        raise RuntimeError("Canonical market evidence missing date/staleness")

    # Canonical precedence rule:
    # Phase 3.4.2.1 v5 market contract ALWAYS overrides older downstream copies.
    result = dict(gate)
    result["version"] = "3.4.4.1"
    result["canonical_market_contract"] = "PHASE3421_V5_AUTHORITATIVE"
    result["latest_market_date"] = latest_market_date
    result["market_stale_days"] = market_stale_days
    result["market_status"] = market.get("market_status")
    result["market_source"] = market.get("market_source")
    result["market_source_kind"] = market.get("market_source_kind")
    result["canonical_market_consistency"] = True

    # Safety invariants: force-locked regardless of upstream content.
    result["release_state"] = "LOCKED"
    result["release_authorized"] = False
    result["human_approval_required"] = True
    result["automatic_approval"] = False
    result["broker_trading_enabled"] = False
    result["real_money_trading_enabled"] = False
    result["fail_closed"] = True

    (OUT / "phase3441_consistency.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.4.1",
        "",
        "## Canonical Market Evidence Consistency Fix",
        "",
        f"- Status: **{result.get('status')}**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- Qualification State: **{result.get('qualification_state')}**",
        f"- Approval Readiness: **{result.get('approval_readiness')}**",
        f"- Human Approval Gate: **{result.get('human_approval_gate_state')}**",
        f"- PASS-day Source: `{result.get('pass_day_source')}`",
        f"- Consecutive PASS days: **{result.get('consecutive_pass_days')} / {result.get('required_pass_days')}**",
        f"- Remaining PASS days: **{result.get('remaining_pass_days')}**",
        "",
        "### Canonical Market Contract",
        "",
        "- Contract: **PHASE3421_V5_AUTHORITATIVE**",
        f"- Latest market date: `{latest_market_date}`",
        f"- Market stale days: `{market_stale_days}`",
        f"- Market status: `{result.get('market_status')}`",
        f"- Market source: `{result.get('market_source')}`",
        f"- Market source kind: `{result.get('market_source_kind')}`",
        "- Canonical market consistency: **YES**",
        "",
        "### Release Safety",
        "",
        "- Release State: **LOCKED**",
        "- Release authorized: **NO**",
        "- Human approval required: **YES**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- This phase changes evidence precedence only.",
    ]

    (OUT / "phase3441_consistency.md").write_text(
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
name: GPT Quant Phase 3.4.4.1 - Canonical Market Evidence Consistency Fix

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
  group: gpt-quant-phase3441-canonical-market-consistency
  cancel-in-progress: false

jobs:
  canonical-market-consistency:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependency
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.4.4.1 safety boundary
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          test -f automation/v92/paper_trading_phase344_human_approval_readiness_gate.py
          test -f automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py
          grep -q PHASE3421_V5_AUTHORITATIVE automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py
          grep -q '"release_authorized"] = False' automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py
          grep -q '"automatic_approval"] = False' automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py
          grep -q '"broker_trading_enabled"] = False' automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py
          grep -q '"real_money_trading_enabled"] = False' automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py

      - name: Run Phase 3.4.4.1 Canonical Market Evidence Consistency Fix
        run: python automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py

      - name: Upload Phase 3.4.4.1 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3441-canonical-market-consistency-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase343_output/
            phase344_output/
            phase3441_output/
          if-no-files-found: warn
          retention-days: 30
'@

[System.IO.File]::WriteAllText($pyPath, $python, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($ymlPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.4.1 READY"
Write-Host "============================================================"
Write-Host "Created:"
Write-Host "  automation/v92/paper_trading_phase3441_canonical_market_evidence_consistency_fix.py"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3441-canonical-market-evidence-consistency-fix.yml"
Write-Host ""
Write-Host "Consistency rule:"
Write-Host "  Phase 3.4.2.1 v5 market evidence ALWAYS wins"
Write-Host "  PASS-day count is unchanged"
Write-Host "  Gate readiness is unchanged"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Release LOCKED"
Write-Host "  Human approval REQUIRED"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
