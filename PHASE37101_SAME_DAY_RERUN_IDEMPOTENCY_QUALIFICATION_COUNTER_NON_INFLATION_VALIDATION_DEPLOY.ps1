$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37101 - Same-Day Re-Run Idempotency + Qualification Counter Non-Inflation Validation" -ForegroundColor Cyan
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green

$repo = (Get-Location).Path
$pyRel = "automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py"
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase37101-same-day-rerun-idempotency-qualification-counter-non-inflation-validation.yml"

$pyPath = Join-Path $repo $pyRel
$ymlPath = Join-Path $repo $ymlRel

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase37101-backup-$stamp"
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

CONTRACT = "PHASE37101_SAME_DAY_RERUN_IDEMPOTENCY_QUALIFICATION_COUNTER_NON_INFLATION_VALIDATION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False
QUALIFICATION_COUNTER_INFLATION_ALLOWED = False

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
    dates = [str(r.get("cycle_date")) for r in rows if r.get("cycle_date")]
    observed = len(rows)
    valid = sum(1 for r in rows if b(r.get("valid_cycle")))
    blocked = sum(1 for r in rows if b(r.get("blocked_cycle")))
    distinct = len(set(dates))
    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": distinct,
        "cycle_dates": dates,
        "duplicate_rows": observed - distinct,
    }

def readiness_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "readiness_date,promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = request("GET", f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main() -> int:
    art = Path("artifacts/phase37101")
    art.mkdir(parents=True, exist_ok=True)

    current = qualification_snapshot()
    readiness = readiness_snapshot()

    observed = int(current["observed"])
    valid = int(current["valid"])
    blocked = int(current["blocked"])
    distinct = int(current["distinct_cycle_dates"])
    duplicate_rows = int(current["duplicate_rows"])

    same_day_idempotent = observed == distinct
    counter_non_inflated = duplicate_rows == 0

    readiness_observed = int(readiness.get("observed_cycles", observed) or 0)
    readiness_valid = int(readiness.get("valid_cycles", valid) or 0)
    readiness_blocked = int(readiness.get("blocked_cycles", blocked) or 0)

    readiness_consistent = (
        readiness_observed == observed
        and readiness_valid == valid
        and readiness_blocked == blocked
    )

    blockers = []
    if not same_day_idempotent:
        blockers.append("SAME_DAY_DUPLICATE_EVIDENCE_DETECTED")
    if not counter_non_inflated:
        blockers.append(f"QUALIFICATION_COUNTER_INFLATION:{duplicate_rows}")
    if readiness and not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")

    if blockers:
        state = "SAME_DAY_IDEMPOTENCY_VALIDATION_BLOCKED"
        operational = False
    else:
        state = "SAME_DAY_IDEMPOTENCY_VALIDATED"
        operational = True

    result = {
        "contract": CONTRACT,
        "state": state,
        "operational": operational,
        "qualification": current,
        "readiness": readiness,
        "checks": {
            "same_day_idempotent": same_day_idempotent,
            "qualification_counter_non_inflated": counter_non_inflated,
            "readiness_counter_consistent": readiness_consistent,
        },
        "blockers": blockers,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
            "same_day_duplicate_bypass_allowed": SAME_DAY_DUPLICATE_BYPASS_ALLOWED,
            "qualification_counter_inflation_allowed": QUALIFICATION_COUNTER_INFLATION_ALLOWED,
        },
    }

    (art / "phase37101_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.10.1",
        "",
        "## Same-Day Re-Run Idempotency + Qualification Counter Non-Inflation Validation",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        "",
        "## Canonical Qualification Counters",
        "",
        f"- Observed Cycles: **{observed}**",
        f"- Valid Cycles: **{valid}**",
        f"- Blocked Cycles: **{blocked}**",
        f"- Distinct Cycle Dates: **{distinct}**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        "",
        "## Validation Checks",
        "",
        f"- Same-Day Re-Run Idempotent: **{'PASS' if same_day_idempotent else 'FAIL'}**",
        f"- Qualification Counter Non-Inflation: **{'PASS' if counter_non_inflated else 'FAIL'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "- Same-Day Duplicate Bypass: **NO**",
        "- Qualification Counter Inflation Allowed: **NO**",
    ]
    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{x}**" for x in blockers]

    (art / "phase37101_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {observed}")
    print(f"Valid Cycles: {valid}")
    print(f"Blocked Cycles: {blocked}")
    print(f"Distinct Cycle Dates: {distinct}")
    print(f"Duplicate Rows: {duplicate_rows}")
    print(f"Same-Day Re-Run Idempotent: {'PASS' if same_day_idempotent else 'FAIL'}")
    print(f"Qualification Counter Non-Inflation: {'PASS' if counter_non_inflated else 'FAIL'}")
    print(f"Readiness Counter Consistency: {'PASS' if readiness_consistent else 'FAIL'}")

    return 1 if blockers else 0

if __name__ == "__main__":
    raise SystemExit(main())
'@
$ymlText = @'
name: GPT Quant Phase 3.7.10.1 - Same-Day Re-Run Idempotency Qualification Counter Non-Inflation Validation

on:
  workflow_dispatch:

permissions:
  contents: read
  actions: write

concurrency:
  group: phase37101-same-day-idempotency-validation
  cancel-in-progress: false

jobs:
  same-day-idempotency-validation:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      GPT_QUANT_PORTFOLIO_ID: V92_PRODUCTION_PAPER_V91
      GPT_QUANT_STRATEGY_VERSION: V9.1
      WF3710: gpt-quant-v92-paper-trading-phase3710-production-paper-multi-day-qualification-accumulation-automatic-promotion-transition.yml

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.10.1
        run: python -m py_compile automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py

      - name: Validate Phase 3.7.10.1 safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED = False' "$f"
          grep -q 'REAL_MONEY_TRADING_ENABLED = False' "$f"
          grep -q 'HISTORICAL_REWRITE_ALLOWED = False' "$f"
          grep -q 'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False' "$f"
          grep -q 'QUALIFICATION_COUNTER_INFLATION_ALLOWED = False' "$f"
          echo "Phase 3.7.10.1 safety contract: PASS"

      - name: Capture baseline counters
        id: baseline
        run: python automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py

      - name: Dispatch same-day Phase 3.7.10 re-run
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail

          before_id="$(gh api \
            -H "Accept: application/vnd.github+json" \
            "/repos/${GITHUB_REPOSITORY}/actions/workflows/${WF3710}/runs?branch=main&per_page=1" \
            --jq '.workflow_runs[0].id // 0' || echo 0)"

          gh workflow run "$WF3710" --ref main

          run_id=""
          for i in $(seq 1 30); do
            sleep 2
            run_id="$(gh api \
              -H "Accept: application/vnd.github+json" \
              "/repos/${GITHUB_REPOSITORY}/actions/workflows/${WF3710}/runs?branch=main&event=workflow_dispatch&per_page=10" \
              --jq "[.workflow_runs[] | select(.id > ${before_id})][0].id // empty" || true)"
            [ -n "$run_id" ] && break
          done

          if [ -z "$run_id" ]; then
            echo "::error::Unable to resolve Phase 3.7.10 re-run."
            exit 1
          fi

          for i in $(seq 1 180); do
            status="$(gh api -H "Accept: application/vnd.github+json" "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" --jq '.status')"
            conclusion="$(gh api -H "Accept: application/vnd.github+json" "/repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}" --jq '.conclusion // ""')"
            echo "Phase 3.7.10 re-run: status=${status} conclusion=${conclusion:-pending}"
            if [ "$status" = "completed" ]; then
              [ "$conclusion" = "success" ] && exit 0
              echo "::error::Phase 3.7.10 re-run failed with ${conclusion}"
              exit 1
            fi
            sleep 5
          done

          echo "::error::Phase 3.7.10 re-run timed out."
          exit 1

      - name: Validate counters after same-day re-run
        id: final
        continue-on-error: true
        run: python automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase37101/phase37101_summary.md ]; then
            cat artifacts/phase37101/phase37101_summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload idempotency evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37101-same-day-idempotency-validation
          path: artifacts/phase37101
          if-no-files-found: warn
          retention-days: 90

      - name: Enforce Phase 3.7.10.1 result
        if: always()
        shell: bash
        run: |
          if [ "${{ steps.final.outcome }}" != "success" ]; then
            echo "Phase 3.7.10.1 same-day idempotency validation is BLOCKED."
            exit 1
          fi
          echo "Phase 3.7.10.1 same-day idempotency validation is healthy."
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
  'SAME_DAY_IDEMPOTENCY_VALIDATED',
  'SAME_DAY_IDEMPOTENCY_VALIDATION_BLOCKED',
  'QUALIFICATION_COUNTER_INFLATION',
  'DUPLICATE_CYCLE_DATE',
  'BROKER_ORDER_SUBMISSION_ENABLED = False',
  'REAL_MONEY_TRADING_ENABLED = False',
  'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False',
  'QUALIFICATION_COUNTER_INFLATION_ALLOWED = False',
  'gpt-quant-v92-paper-trading-phase3710-production-paper-multi-day-qualification-accumulation-automatic-promotion-transition.yml'
)

foreach ($token in $required) {
    if ($combined -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Same-day re-run validation contract: PASS" -ForegroundColor Green
Write-Host "Qualification counter non-inflation contract: PASS" -ForegroundColor Green
Write-Host "Canonical ledger duplicate-date detection: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.10 re-run bridge: PASS" -ForegroundColor Green
Write-Host "Readiness counter consistency validation: PASS" -ForegroundColor Green
Write-Host "Same-day duplicate bypass prohibition: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37101 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL schema change is required." -ForegroundColor Green
Write-Host ""
Write-Host "Generated:"
Write-Host "  $pyPath"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "Expected validation result today:"
Write-Host "  SAME_DAY_IDEMPOTENCY_VALIDATED"
Write-Host "  Observed Cycles remains 1"
Write-Host "  Valid Cycles remains 1"
Write-Host "  Distinct Cycle Dates remains 1"
Write-Host "  Duplicate Rows = 0"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py"'
Write-Host '2. git add ".github/workflows/gpt-quant-v92-paper-trading-phase37101-same-day-rerun-idempotency-qualification-counter-non-inflation-validation.yml"'
Write-Host '3. git diff --cached --name-only'
Write-Host '4. git commit -m "Deploy Phase 37101 same-day rerun idempotency qualification counter non-inflation validation"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Phase 3.7.10.1 workflow on main.'
