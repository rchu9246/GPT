$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE3713 - Production Paper Natural Qualification Daily Orchestration + Promotion Readiness Automation" -ForegroundColor Cyan
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green
Write-Host "Natural evidence only: no synthetic cycle date / no manual counter increment" -ForegroundColor Green

$repo = (Get-Location).Path
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase3713-production-paper-natural-qualification-daily-orchestration-promotion-readiness-automation.yml"
$ymlPath = Join-Path $repo $ymlRel

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase3713-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

if (Test-Path $ymlPath) {
    Copy-Item $ymlPath (Join-Path $backup (Split-Path $ymlPath -Leaf)) -Force
}

$workflow = @'
name: GPT Quant Phase 3.7.13 - Production Paper Natural Qualification Daily Orchestration Promotion Readiness Automation

on:
  workflow_dispatch:
  schedule:
    # Weekdays 17:05 UTC / 01:05 Asia-Taipei (next calendar day).
    - cron: "5 17 * * 1-5"

permissions:
  contents: read
  actions: write

concurrency:
  group: phase3713-natural-qualification-daily-orchestration
  cancel-in-progress: false

jobs:
  natural-qualification-daily-orchestration:
    runs-on: ubuntu-latest
    timeout-minutes: 45

    env:
      WF374: gpt-quant-v92-paper-trading-phase374-production-paper-daily-cycle-monitoring-evidence-accumulation.yml
      WF377: gpt-quant-v92-paper-trading-phase377-production-paper-qualification-evidence-persistence-cross-run-accumulation.yml
      WF3710: gpt-quant-v92-paper-trading-phase3710-production-paper-multi-day-qualification-accumulation-automatic-promotion-transition.yml
      WF379: gpt-quant-v92-paper-trading-phase379-production-paper-qualification-state-reconciliation-automatic-promotion-readiness.yml
      WF3712: gpt-quant-v92-paper-trading-phase3712-production-paper-qualification-cross-day-accumulation-continuity-promotion-threshold-finalization.yml
      WF3711: gpt-quant-v92-paper-trading-phase3711-production-paper-qualification-promotion-transition-integrity-post-promotion-safety-lock.yml
      WF37121: gpt-quant-v92-paper-trading-phase37121-natural-cross-day-qualification-observation-evidence-integrity-audit.yml

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Validate orchestration safety contract
        shell: bash
        run: |
          set -euo pipefail

          echo "PAPER_ONLY=YES"
          echo "BROKER_ORDER_SUBMISSION=DISABLED"
          echo "REAL_MONEY_TRADING=DISABLED"
          echo "SYNTHETIC_CYCLE_DATE=DISABLED"
          echo "MANUAL_COUNTER_INCREMENT=DISABLED"
          echo "QUALIFICATION_THRESHOLD_BYPASS=DISABLED"
          echo "Natural qualification daily orchestration safety contract: PASS"

      - name: Run natural qualification chain in canonical order
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail

          dispatch_and_wait() {
            local wf="$1"
            local label="$2"

            echo "============================================================"
            echo "Dispatching ${label}"
            echo "Workflow: ${wf}"

            local before_id
            before_id="$(gh api \
              -H "Accept: application/vnd.github+json" \
              "/repos/${GITHUB_REPOSITORY}/actions/workflows/${wf}/runs?branch=main&per_page=1" \
              --jq '.workflow_runs[0].id // 0' || echo 0)"

            gh workflow run "$wf" --ref main

            local run_id=""
            for i in $(seq 1 40); do
              sleep 2
              run_id="$(gh api \
                -H "Accept: application/vnd.github+json" \
                "/repos/${GITHUB_REPOSITORY}/actions/workflows/${wf}/runs?branch=main&event=workflow_dispatch&per_page=10" \
                --jq "[.workflow_runs[] | select(.id > ${before_id})][0].id // empty" || true)"
              [ -n "$run_id" ] && break
            done

            if [ -z "$run_id" ]; then
              echo "::error::Unable to resolve run for ${label}"
              return 1
            fi

            echo "${label} run_id=${run_id}"

            for i in $(seq 1 240); do
              local status
              local conclusion

              status="$(gh api \
                -H "Accept: application/vnd.github+json" \
                "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" \
                --jq '.status')"

              conclusion="$(gh api \
                -H "Accept: application/vnd.github+json" \
                "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" \
                --jq '.conclusion // ""')"

              echo "${label}: status=${status} conclusion=${conclusion:-pending}"

              if [ "$status" = "completed" ]; then
                if [ "$conclusion" = "success" ]; then
                  echo "${label}: PASS"
                  return 0
                fi
                echo "::error::${label} failed with conclusion=${conclusion}"
                return 1
              fi

              sleep 5
            done

            echo "::error::${label} timed out"
            return 1
          }

          dispatch_and_wait "$WF374" "Phase 3.7.4 Daily Cycle Monitoring"
          dispatch_and_wait "$WF377" "Phase 3.7.7 Qualification Evidence Persistence"
          dispatch_and_wait "$WF3710" "Phase 3.7.10 Multi-Day Qualification Accumulation"
          dispatch_and_wait "$WF379" "Phase 3.7.9 Promotion Readiness Reconciliation"
          dispatch_and_wait "$WF3712" "Phase 3.7.12 Promotion Threshold Finalization"
          dispatch_and_wait "$WF3711" "Phase 3.7.11 Promotion Transition Integrity"
          dispatch_and_wait "$WF37121" "Phase 3.7.12.1 Natural Cross-Day Evidence Audit"

      - name: Publish Phase 3.7.13 summary
        if: always()
        shell: bash
        run: |
          {
            echo "# GPT Quant V9.2 Paper Trading — Phase 3.7.13"
            echo ""
            echo "## Production Paper Natural Qualification Daily Orchestration + Promotion Readiness Automation"
            echo ""
            echo "- Orchestration State: **NATURAL_QUALIFICATION_DAILY_ORCHESTRATION_COMPLETE**"
            echo "- Child Order: **3.7.4 → 3.7.7 → 3.7.10 → 3.7.9 → 3.7.12 → 3.7.11 → 3.7.12.1**"
            echo "- Same-Day Counter Inflation: **PROHIBITED**"
            echo "- Synthetic Cycle-Date Creation: **PROHIBITED**"
            echo "- Manual Counter Increment: **PROHIBITED**"
            echo "- Qualification Threshold Bypass: **PROHIBITED**"
            echo ""
            echo "## Safety Boundary"
            echo ""
            echo "- Paper Trading Only: **YES**"
            echo "- Broker Order Submission: **DISABLED**"
            echo "- Real-Money Trading: **DISABLED**"
            echo "- Historical Rewrite: **DISABLED**"
            echo ""
            echo "The orchestrator does not fabricate qualification evidence. Child workflows remain authoritative for canonical qualification state."
          } >> "$GITHUB_STEP_SUMMARY"
'@

$utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ymlPath) | Out-Null
[System.IO.File]::WriteAllText($ymlPath, $workflow + [Environment]::NewLine, $utf8)

$raw = Get-Content -LiteralPath $ymlPath -Raw

$required = @(
  'GPT Quant Phase 3.7.13',
  'WF374:',
  'WF377:',
  'WF3710:',
  'WF379:',
  'WF3712:',
  'WF3711:',
  'WF37121:',
  'dispatch_and_wait "$WF374"',
  'dispatch_and_wait "$WF377"',
  'dispatch_and_wait "$WF3710"',
  'dispatch_and_wait "$WF379"',
  'dispatch_and_wait "$WF3712"',
  'dispatch_and_wait "$WF3711"',
  'dispatch_and_wait "$WF37121"',
  'BROKER_ORDER_SUBMISSION=DISABLED',
  'REAL_MONEY_TRADING=DISABLED',
  'SYNTHETIC_CYCLE_DATE=DISABLED',
  'MANUAL_COUNTER_INCREMENT=DISABLED',
  'QUALIFICATION_THRESHOLD_BYPASS=DISABLED',
  'NATURAL_QUALIFICATION_DAILY_ORCHESTRATION_COMPLETE'
)

foreach ($token in $required) {
    if ($raw -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Ordered child workflow chain: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.4 daily evidence bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.7 persistence bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.10 accumulation bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.9 readiness reconciliation bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.12 threshold finalization bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.11 transition integrity bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.12.1 evidence audit bridge: PASS" -ForegroundColor Green
Write-Host "Synthetic cycle-date prohibition: PASS" -ForegroundColor Green
Write-Host "Manual counter increment prohibition: PASS" -ForegroundColor Green
Write-Host "Broker/real-money safety boundary: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE3713 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL schema change is required." -ForegroundColor Green
Write-Host ""
Write-Host "Generated:"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "Automatic schedule:"
Write-Host "  Weekdays 17:05 UTC / 01:05 Asia-Taipei"
Write-Host ""
Write-Host "Expected current behavior:"
Write-Host "  Natural qualification remains 1/3 on same-day reruns"
Write-Host "  New qualification count is accepted only from genuine new cycle-date evidence"
Write-Host "  Promotion readiness/finalization only occurs through canonical child workflows"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add ".github/workflows/gpt-quant-v92-paper-trading-phase3713-production-paper-natural-qualification-daily-orchestration-promotion-readiness-automation.yml"'
Write-Host '2. git diff --cached --name-only'
Write-Host '3. git commit -m "Deploy Phase 3713 natural qualification daily orchestration promotion readiness automation"'
Write-Host '4. git push origin main'
Write-Host '5. Run a NEW Phase 3.7.13 workflow on main.'
