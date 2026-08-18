$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.4.3 v3"
Write-Host " Human Approval Workflow Safety Contract Alignment Fix"
Write-Host "============================================================"

$root = (Get-Location).Path
$workflowDir = Join-Path $root ".github\workflows"
$automationDir = Join-Path $root "automation\v92"

New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null
New-Item -ItemType Directory -Force -Path $automationDir | Out-Null

$workflowPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase344-human-approval-readiness-gate.yml"
$gatePath = Join-Path $automationDir "paper_trading_phase344_human_approval_readiness_gate.py"
$bridgePath = Join-Path $automationDir "paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
$marketBridgePath = Join-Path $automationDir "paper_trading_phase3421_market_state_persistence_fix.py"

if (-not (Test-Path $gatePath)) {
    throw "Missing Phase 3.4.4 gate: $gatePath"
}

if (-not (Test-Path $bridgePath)) {
    throw "Missing Phase 3.4.4.3 v2 runtime reconstruction bridge: $bridgePath"
}

if (-not (Test-Path $marketBridgePath)) {
    throw "Missing Phase 3.4.2.1 market bridge: $marketBridgePath"
}

if (Test-Path $workflowPath) {
    $backup = "$workflowPath.pre3443v3.bak"
    if (-not (Test-Path $backup)) {
        Copy-Item $workflowPath $backup
    }
}

$workflow = @'
name: GPT Quant Phase 3.4.4 - Human Approval Readiness Gate

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
  group: gpt-quant-phase344-human-approval-readiness
  cancel-in-progress: false

jobs:
  human-approval-readiness:
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

      - name: Validate Phase 3.4.4 aligned safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase344_human_approval_readiness_gate.py
          test -f automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py
          test -f automation/v92/paper_trading_phase3421_market_state_persistence_fix.py

          # The Phase 3.4.4 gate is now a bridge into same-runner canonical reconstruction.
          grep -q 'paper_trading_phase3443_runtime_canonical_state_reconstruction.py' \
            automation/v92/paper_trading_phase344_human_approval_readiness_gate.py

          # Validate the actual authoritative safety contract in the reconstruction engine.
          grep -q 'RUNTIME_REBUILD_PHASE3421_PLUS_CANONICAL_GUARD' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q '"release_state": "LOCKED"' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q '"release_authorized": False' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q '"release_locked_before_human_approval": True' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q '"human_approval_required": True' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q '"automatic_approval": False' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q '"broker_trading_enabled": False' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py

          echo "Phase 3.4.4 aligned safety contract: PASS"

      - name: Run Phase 3.4.4 Human Approval Readiness Gate
        run: python automation/v92/paper_trading_phase344_human_approval_readiness_gate.py

      - name: Validate runtime readiness output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase344_output/phase344_readiness.json

          python - <<'PY'
          import json
          from pathlib import Path

          p = Path("phase344_output/phase344_readiness.json")
          data = json.loads(p.read_text(encoding="utf-8"))

          assert data.get("status") == "PASS", data
          assert data.get("canonical_source_valid") is True, data

          assert data.get("release_state") == "LOCKED", data
          assert data.get("release_authorized") is False, data
          assert data.get("release_locked_before_human_approval") is True, data
          assert data.get("human_approval_required") is True, data
          assert data.get("automatic_approval") is False, data
          assert data.get("broker_trading_enabled") is False, data
          assert data.get("real_money_trading_enabled") is False, data

          pass_days = int(data.get("consecutive_pass_days", 0))
          required = int(data.get("required_pass_days", 5))

          if pass_days >= required:
              assert data.get("qualification_state") == "QUALIFIED", data
              assert data.get("approval_readiness") == "READY_FOR_HUMAN_APPROVAL", data
              assert data.get("human_approval_gate_state") == "OPEN_FOR_HUMAN_REVIEW", data
          else:
              assert data.get("qualification_state") == "OBSERVATION", data
              assert data.get("approval_readiness") == "NOT_READY", data
              assert data.get("human_approval_gate_state") == "CLOSED_WAITING_FOR_QUALIFICATION", data

          print("Runtime readiness output validation: PASS")
          print(json.dumps(data, ensure_ascii=False, indent=2))
          PY

      - name: Upload Phase 3.4.4 readiness evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase344-human-approval-readiness-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
          if-no-files-found: warn
          retention-days: 30
'@

[System.IO.File]::WriteAllText(
    $workflowPath,
    $workflow,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.4.3 v3 READY"
Write-Host "============================================================"
Write-Host "Overwritten:"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase344-human-approval-readiness-gate.yml"
Write-Host ""
Write-Host "Alignment:"
Write-Host "  Old safety grep contract REMOVED"
Write-Host "  Phase 3.4.4 now validates the v2 runtime reconstruction engine"
Write-Host "  Gate executes same-runner canonical reconstruction"
Write-Host "  Runtime output is validated after execution"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Release LOCKED"
Write-Host "  Release authorization DISABLED"
Write-Host "  Release locked before human approval = YES"
Write-Host "  Human approval REQUIRED"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
Write-Host ""
Write-Host "Next:"
Write-Host "  GitHub Desktop -> Commit -> Push origin"
Write-Host "  Actions -> GPT Quant Phase 3.4.4 - Human Approval Readiness Gate"
Write-Host "  Run workflow"
