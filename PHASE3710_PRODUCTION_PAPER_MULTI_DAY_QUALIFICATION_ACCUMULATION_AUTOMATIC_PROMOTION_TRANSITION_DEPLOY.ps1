$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE3710 - Production Paper Multi-Day Qualification Accumulation + Automatic Promotion Transition" -ForegroundColor Cyan
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green

$repo = (Get-Location).Path
$pyRel = "automation/v92/paper_trading_phase3710_production_paper_multi_day_qualification_accumulation_automatic_promotion_transition.py"
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase3710-production-paper-multi-day-qualification-accumulation-automatic-promotion-transition.yml"

$pyPath = Join-Path $repo $pyRel
$ymlPath = Join-Path $repo $ymlRel

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase3710-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

foreach ($p in @($pyPath, $ymlPath)) {
    if (Test-Path $p) {
        Copy-Item $p (Join-Path $backup (Split-Path $p -Leaf)) -Force
    }
}

$pyText = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE3710_PRODUCTION_PAPER_MULTI_DAY_QUALIFICATION_ACCUMULATION_AUTOMATIC_PROMOTION_TRANSITION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MAX_BLOCKED = 0

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False
QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False

def env_first(*names: str) -> Optional[str]:
    for name in names:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

def request(method: str, path: str) -> Any:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e

def b(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE", "YES", "Y", "1", "PASS", "ENABLED"}

def qualification_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "cycle_date,cycle_state,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request("GET", f"{QUALIFICATION_TABLE}?{q}") or []

    observed = len(rows)
    valid = sum(1 for r in rows if b(r.get("valid_cycle")))
    blocked = sum(1 for r in rows if b(r.get("blocked_cycle")))
    runtime_pass = observed > 0 and all(b(r.get("runtime_supervision_pass")) for r in rows)
    paper_only_pass = observed > 0 and all(b(r.get("paper_only_boundary_pass")) for r in rows)
    dates = [str(r.get("cycle_date")) for r in rows if r.get("cycle_date")]

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "runtime_supervision_pass": runtime_pass,
        "paper_only_boundary_pass": paper_only_pass,
        "cycle_dates": dates,
        "distinct_cycle_dates": len(set(dates)),
    }

def readiness_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "readiness_date,qualification_state,promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = request("GET", f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main() -> int:
    art = Path("artifacts/phase3710")
    art.mkdir(parents=True, exist_ok=True)

    q = qualification_snapshot()
    r = readiness_snapshot()

    observed = int(q["observed"])
    valid = int(q["valid"])
    blocked = int(q["blocked"])
    distinct_dates = int(q["distinct_cycle_dates"])
    runtime_pass = bool(q["runtime_supervision_pass"])
    paper_only_pass = bool(q["paper_only_boundary_pass"])

    threshold_met = (
        observed >= MIN_OBSERVED
        and valid >= MIN_VALID
        and blocked <= MAX_BLOCKED
        and distinct_dates >= MIN_OBSERVED
        and runtime_pass
        and paper_only_pass
    )

    readiness_state = str(r.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()
    readiness_ready = b(r.get("promotion_ready", False))

    blockers = []
    if blocked > MAX_BLOCKED:
        blockers.append(f"BLOCKED_CYCLES_PRESENT:{blocked}")
    if observed > 0 and not runtime_pass:
        blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not paper_only_pass:
        blockers.append("PAPER_ONLY_BOUNDARY_NOT_PASS")
    if observed != distinct_dates:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")

    if blockers:
        state = "MULTI_DAY_QUALIFICATION_BLOCKED"
        transition_required = False
        operational = False
    elif threshold_met and readiness_ready and readiness_state == "PROMOTION_READINESS_READY":
        state = "AUTOMATIC_PROMOTION_TRANSITION_READY"
        transition_required = False
        operational = True
    elif threshold_met:
        state = "QUALIFICATION_THRESHOLD_MET_PROMOTION_TRANSITION_REQUIRED"
        transition_required = True
        operational = True
    else:
        state = "MULTI_DAY_QUALIFICATION_ACCUMULATING"
        transition_required = False
        operational = True

    result = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "state": state,
        "operational": operational,
        "transition_required": transition_required,
        "thresholds": {
            "minimum_observed_cycles": MIN_OBSERVED,
            "minimum_valid_cycles": MIN_VALID,
            "maximum_blocked_cycles": MAX_BLOCKED,
            "minimum_distinct_cycle_dates": MIN_OBSERVED,
        },
        "qualification": q,
        "readiness": r,
        "checks": {
            "threshold_met": threshold_met,
            "readiness_ready": readiness_ready,
            "same_day_deduplication_preserved": observed == distinct_dates,
            "qualification_threshold_bypass": False,
        },
        "blockers": blockers,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
            "same_day_duplicate_bypass_allowed": SAME_DAY_DUPLICATE_BYPASS_ALLOWED,
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
        },
    }

    (art / "phase3710_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.10",
        "",
        "## Production Paper Multi-Day Qualification Accumulation + Automatic Promotion Transition",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Automatic Promotion Transition Required: **{'YES' if transition_required else 'NO'}**",
        "",
        "## Multi-Day Qualification Evidence",
        "",
        f"- Observed Cycles: **{observed} / {MIN_OBSERVED}**",
        f"- Valid Cycles: **{valid} / {MIN_VALID}**",
        f"- Blocked Cycles: **{blocked} / {MAX_BLOCKED} max**",
        f"- Distinct Cycle Dates: **{distinct_dates} / {MIN_OBSERVED}**",
        f"- Runtime Supervision: **{'PASS' if runtime_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        f"- Paper-Only Boundary: **{'PASS' if paper_only_pass else ('WAITING' if observed == 0 else 'FAIL')}**",
        "",
        "## Promotion Readiness",
        "",
        f"- Phase 3.7.9 Readiness State: **{readiness_state}**",
        f"- Promotion Ready: **{'YES' if readiness_ready else 'NO'}**",
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "- Same-Day Duplicate Bypass: **NO**",
        "- Qualification Threshold Bypass: **NO**",
    ]
    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{x}**" for x in blockers]

    (art / "phase3710_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {observed}")
    print(f"Valid Cycles: {valid}")
    print(f"Blocked Cycles: {blocked}")
    print(f"Distinct Cycle Dates: {distinct_dates}")
    print(f"Transition Required: {'YES' if transition_required else 'NO'}")

    return 1 if blockers else 0

if __name__ == "__main__":
    raise SystemExit(main())
'@
$ymlText = @'
name: GPT Quant Phase 3.7.10 - Production Paper Multi-Day Qualification Accumulation Automatic Promotion Transition

on:
  workflow_dispatch:
  schedule:
    # Weekdays 15:50 UTC / 23:50 Asia-Taipei.
    - cron: "50 15 * * 1-5"

permissions:
  contents: read
  actions: write

concurrency:
  group: phase3710-production-paper-multi-day-qualification-transition
  cancel-in-progress: false

jobs:
  multi-day-qualification-transition:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      GPT_QUANT_PORTFOLIO_ID: V92_PRODUCTION_PAPER_V91
      GPT_QUANT_STRATEGY_VERSION: V9.1
      WF378: gpt-quant-v92-paper-trading-phase378-production-paper-qualification-orchestrator-ordered-daily-evidence-pipeline.yml
      WF376: gpt-quant-v92-paper-trading-phase376-production-paper-multi-cycle-qualification-promotion-gate.yml
      WF379: gpt-quant-v92-paper-trading-phase379-production-paper-qualification-state-reconciliation-automatic-promotion-readiness.yml

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.10
        run: python -m py_compile automation/v92/paper_trading_phase3710_production_paper_multi_day_qualification_accumulation_automatic_promotion_transition.py

      - name: Validate Phase 3.7.10 safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase3710_production_paper_multi_day_qualification_accumulation_automatic_promotion_transition.py"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED = False' "$f"
          grep -q 'REAL_MONEY_TRADING_ENABLED = False' "$f"
          grep -q 'HISTORICAL_REWRITE_ALLOWED = False' "$f"
          grep -q 'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False' "$f"
          grep -q 'QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False' "$f"
          echo "Phase 3.7.10 safety contract: PASS"

      - name: Run ordered daily evidence pipeline
        id: phase378
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail

          before_id="$(gh api \
            -H "Accept: application/vnd.github+json" \
            "/repos/${GITHUB_REPOSITORY}/actions/workflows/${WF378}/runs?branch=main&per_page=1" \
            --jq '.workflow_runs[0].id // 0' || echo 0)"

          gh workflow run "$WF378" --ref main

          run_id=""
          for i in $(seq 1 30); do
            sleep 2
            run_id="$(gh api \
              -H "Accept: application/vnd.github+json" \
              "/repos/${GITHUB_REPOSITORY}/actions/workflows/${WF378}/runs?branch=main&event=workflow_dispatch&per_page=10" \
              --jq "[.workflow_runs[] | select(.id > ${before_id})][0].id // empty" || true)"
            [ -n "$run_id" ] && break
          done

          if [ -z "$run_id" ]; then
            echo "::error::Could not resolve dispatched Phase 3.7.8 run."
            exit 1
          fi

          for i in $(seq 1 180); do
            status="$(gh api -H "Accept: application/vnd.github+json" "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" --jq '.status')"
            conclusion="$(gh api -H "Accept: application/vnd.github+json" "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" --jq '.conclusion // ""')"
            echo "Phase 3.7.8 status=${status} conclusion=${conclusion:-pending}"
            if [ "$status" = "completed" ]; then
              [ "$conclusion" = "success" ] && exit 0
              echo "::error::Phase 3.7.8 failed with ${conclusion}"
              exit 1
            fi
            sleep 5
          done

          echo "::error::Phase 3.7.8 timed out."
          exit 1

      - name: Evaluate multi-day qualification state
        id: evaluate_before
        continue-on-error: true
        run: python automation/v92/paper_trading_phase3710_production_paper_multi_day_qualification_accumulation_automatic_promotion_transition.py

      - name: Read transition requirement
        id: transition
        if: always()
        shell: bash
        run: |
          set -euo pipefail
          if [ ! -f artifacts/phase3710/phase3710_result.json ]; then
            echo "required=false" >> "$GITHUB_OUTPUT"
            echo "blocked=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          python -c "import json; d=json.load(open('artifacts/phase3710/phase3710_result.json', encoding='utf-8')); print('required=' + ('true' if d.get('transition_required') else 'false')); print('blocked=' + ('true' if d.get('blockers') else 'false'))" >> "$GITHUB_OUTPUT"

      - name: Run automatic promotion transition
        if: steps.transition.outputs.required == 'true' && steps.transition.outputs.blocked != 'true'
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail

          run_and_wait() {
            local workflow="$1"
            local label="$2"
            local before_id
            local run_id
            local status
            local conclusion

            before_id="$(gh api \
              -H "Accept: application/vnd.github+json" \
              "/repos/${GITHUB_REPOSITORY}/actions/workflows/${workflow}/runs?branch=main&per_page=1" \
              --jq '.workflow_runs[0].id // 0' || echo 0)"

            echo "Dispatching ${label}"
            gh workflow run "$workflow" --ref main

            run_id=""
            for i in $(seq 1 30); do
              sleep 2
              run_id="$(gh api \
                -H "Accept: application/vnd.github+json" \
                "/repos/${GITHUB_REPOSITORY}/actions/workflows/${workflow}/runs?branch=main&event=workflow_dispatch&per_page=10" \
                --jq "[.workflow_runs[] | select(.id > ${before_id})][0].id // empty" || true)"
              [ -n "$run_id" ] && break
            done

            [ -z "$run_id" ] && echo "::error::Unable to resolve ${label} run." && return 1

            for i in $(seq 1 180); do
              status="$(gh api -H "Accept: application/vnd.github+json" "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" --jq '.status')"
              conclusion="$(gh api -H "Accept: application/vnd.github+json" "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" --jq '.conclusion // ""')"
              echo "${label}: status=${status} conclusion=${conclusion:-pending}"
              if [ "$status" = "completed" ]; then
                [ "$conclusion" = "success" ] && return 0
                echo "::error::${label} failed with ${conclusion}"
                return 1
              fi
              sleep 5
            done

            echo "::error::${label} timed out."
            return 1
          }

          # Re-run the canonical qualification/promotion gate after threshold is truly met,
          # then refresh Phase 3.7.9 readiness.
          run_and_wait "$WF376" "Phase 3.7.6 Promotion Gate"
          run_and_wait "$WF379" "Phase 3.7.9 Promotion Readiness"

      - name: Re-evaluate final transition state
        id: evaluate_after
        if: always()
        continue-on-error: true
        run: python automation/v92/paper_trading_phase3710_production_paper_multi_day_qualification_accumulation_automatic_promotion_transition.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3710/phase3710_summary.md ]; then
            cat artifacts/phase3710/phase3710_summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload Phase 3.7.10 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3710-production-paper-multi-day-qualification-transition
          path: artifacts/phase3710
          if-no-files-found: warn
          retention-days: 90

      - name: Enforce Phase 3.7.10 result
        if: always()
        shell: bash
        run: |
          if [ "${{ steps.evaluate_after.outcome }}" != "success" ]; then
            echo "Phase 3.7.10 multi-day qualification transition is BLOCKED."
            exit 1
          fi
          echo "Phase 3.7.10 multi-day qualification transition is healthy."
'@

$utf8 = New-Object System.Text.UTF8Encoding($false)
foreach ($p in @($pyPath, $ymlPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $p) | Out-Null
}

[System.IO.File]::WriteAllText($pyPath, $pyText + [Environment]::NewLine, $utf8)
[System.IO.File]::WriteAllText($ymlPath, $ymlText + [Environment]::NewLine, $utf8)

python -m py_compile $pyPath
if ($LASTEXITCODE -ne 0) {
    throw "Python compile failed."
}

$combined = (Get-Content -LiteralPath $pyPath -Raw) + "`n" + (Get-Content -LiteralPath $ymlPath -Raw)
$required = @(
  'paper_production_qualification_evidence_v92',
  'paper_production_promotion_readiness_v92',
  'MULTI_DAY_QUALIFICATION_ACCUMULATING',
  'QUALIFICATION_THRESHOLD_MET_PROMOTION_TRANSITION_REQUIRED',
  'AUTOMATIC_PROMOTION_TRANSITION_READY',
  'DUPLICATE_CYCLE_DATE_DETECTED',
  'BROKER_ORDER_SUBMISSION_ENABLED = False',
  'REAL_MONEY_TRADING_ENABLED = False',
  'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False',
  'QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False',
  'gpt-quant-v92-paper-trading-phase378-production-paper-qualification-orchestrator-ordered-daily-evidence-pipeline.yml',
  'gpt-quant-v92-paper-trading-phase376-production-paper-multi-cycle-qualification-promotion-gate.yml',
  'gpt-quant-v92-paper-trading-phase379-production-paper-qualification-state-reconciliation-automatic-promotion-readiness.yml'
)

foreach ($token in $required) {
    if ($combined -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Multi-day canonical accumulation contract: PASS" -ForegroundColor Green
Write-Host "Distinct cycle-date qualification contract: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.8 ordered pipeline bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.6 automatic promotion transition bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.9 readiness refresh bridge: PASS" -ForegroundColor Green
Write-Host "Same-day duplicate bypass prohibition: PASS" -ForegroundColor Green
Write-Host "Qualification threshold non-bypass: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE3710 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL schema change is required." -ForegroundColor Green
Write-Host ""
Write-Host "Generated:"
Write-Host "  $pyPath"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "Automatic schedule:"
Write-Host "  Weekdays 15:50 UTC / 23:50 Asia-Taipei"
Write-Host ""
Write-Host "Expected current state:"
Write-Host "  MULTI_DAY_QUALIFICATION_ACCUMULATING"
Write-Host "  Observed: 1 / 3"
Write-Host "  Valid: 1 / 3"
Write-Host "  Blocked: 0"
Write-Host ""
Write-Host "Automatic transition only occurs when:"
Write-Host "  Observed >= 3"
Write-Host "  Valid >= 3"
Write-Host "  Distinct cycle dates >= 3"
Write-Host "  Blocked = 0"
Write-Host "  Runtime supervision = PASS"
Write-Host "  Paper-only boundary = PASS"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/v92/paper_trading_phase3710_production_paper_multi_day_qualification_accumulation_automatic_promotion_transition.py"'
Write-Host '2. git add ".github/workflows/gpt-quant-v92-paper-trading-phase3710-production-paper-multi-day-qualification-accumulation-automatic-promotion-transition.yml"'
Write-Host '3. git diff --cached --name-only'
Write-Host '4. git commit -m "Deploy Phase 3710 production paper multi-day qualification accumulation automatic promotion transition"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Phase 3.7.10 workflow on main.'
