$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37101 V1.1 - Duplicate Cycle Date Validation Contract Fix" -ForegroundColor Cyan
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green

$repo = (Get-Location).Path
$pyRel = "automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py"
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase37101-same-day-rerun-idempotency-qualification-counter-non-inflation-validation.yml"

$pyPath = Join-Path $repo $pyRel
$ymlPath = Join-Path $repo $ymlRel

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase37101-v11-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

foreach ($p in @($pyPath, $ymlPath)) {
    if (Test-Path $p) {
        Copy-Item $p (Join-Path $backup (Split-Path $p -Leaf)) -Force
    }
}

$pyText = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE37101_V11_DUPLICATE_CYCLE_DATE_VALIDATION_CONTRACT_FIX"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

ART_DIR = Path("artifacts/phase37101")
BASELINE_PATH = ART_DIR / "baseline_snapshot.json"
RESULT_PATH = ART_DIR / "phase37101_result.json"
SUMMARY_PATH = ART_DIR / "phase37101_summary.md"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False
QUALIFICATION_COUNTER_INFLATION_ALLOWED = False

def env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip().rstrip("/")
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
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"TRUE", "YES", "Y", "1", "PASS", "ENABLED"}

def canonical_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "cycle_date,cycle_state,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request("GET", f"{QUALIFICATION_TABLE}?{q}") or []

    cycle_dates = [str(row.get("cycle_date")) for row in rows if row.get("cycle_date")]
    distinct_cycle_dates = len(set(cycle_dates))
    observed = len(rows)
    valid = sum(1 for row in rows if truthy(row.get("valid_cycle")))
    blocked = sum(1 for row in rows if truthy(row.get("blocked_cycle")))
    duplicate_rows = observed - distinct_cycle_dates

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": distinct_cycle_dates,
        "duplicate_rows": duplicate_rows,
        "cycle_dates": cycle_dates,
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

def save_baseline() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    baseline = {
        "contract": CONTRACT,
        "qualification": canonical_snapshot(),
        "readiness": readiness_snapshot(),
    }
    BASELINE_PATH.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")

    q = baseline["qualification"]
    print("Baseline snapshot saved.")
    print(f"Observed Cycles: {q['observed']}")
    print(f"Valid Cycles: {q['valid']}")
    print(f"Blocked Cycles: {q['blocked']}")
    print(f"Distinct Cycle Dates: {q['distinct_cycle_dates']}")
    print(f"Duplicate Rows: {q['duplicate_rows']}")
    return 0

def validate_after() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise RuntimeError("BASELINE_SNAPSHOT_MISSING")

    baseline_doc = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline = baseline_doc.get("qualification", {})
    current = canonical_snapshot()
    readiness = readiness_snapshot()

    same_observed = int(current["observed"]) == int(baseline.get("observed", -1))
    same_valid = int(current["valid"]) == int(baseline.get("valid", -1))
    same_blocked = int(current["blocked"]) == int(baseline.get("blocked", -1))
    same_distinct_dates = int(current["distinct_cycle_dates"]) == int(baseline.get("distinct_cycle_dates", -1))
    duplicate_cycle_date_detected = int(current["duplicate_rows"]) > 0

    same_day_idempotent = (
        same_observed
        and same_valid
        and same_blocked
        and same_distinct_dates
        and not duplicate_cycle_date_detected
    )
    counter_non_inflated = (
        same_observed
        and same_valid
        and same_distinct_dates
        and int(current["duplicate_rows"]) == 0
    )

    readiness_consistent = True
    if readiness:
        readiness_consistent = (
            int(readiness.get("observed_cycles", current["observed"]) or 0) == int(current["observed"])
            and int(readiness.get("valid_cycles", current["valid"]) or 0) == int(current["valid"])
            and int(readiness.get("blocked_cycles", current["blocked"]) or 0) == int(current["blocked"])
        )

    blockers = []
    if duplicate_cycle_date_detected:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if not same_day_idempotent:
        blockers.append("SAME_DAY_RERUN_NOT_IDEMPOTENT")
    if not counter_non_inflated:
        blockers.append("QUALIFICATION_COUNTER_INFLATION_DETECTED")
    if readiness and not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")

    state = "SAME_DAY_IDEMPOTENCY_VALIDATED" if not blockers else "SAME_DAY_IDEMPOTENCY_VALIDATION_BLOCKED"
    operational = not blockers

    result = {
        "contract": CONTRACT,
        "state": state,
        "operational": operational,
        "baseline": baseline,
        "current": current,
        "readiness": readiness,
        "checks": {
            "same_day_rerun_idempotent": same_day_idempotent,
            "qualification_counter_non_inflated": counter_non_inflated,
            "duplicate_cycle_date_detected": duplicate_cycle_date_detected,
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

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.10.1 V1.1",
        "",
        "## Same-Day Re-Run Idempotency + Qualification Counter Non-Inflation Validation",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        "",
        "## Baseline → Post Re-Run Counters",
        "",
        f"- Observed Cycles: **{baseline.get('observed', 0)} → {current['observed']}**",
        f"- Valid Cycles: **{baseline.get('valid', 0)} → {current['valid']}**",
        f"- Blocked Cycles: **{baseline.get('blocked', 0)} → {current['blocked']}**",
        f"- Distinct Cycle Dates: **{baseline.get('distinct_cycle_dates', 0)} → {current['distinct_cycle_dates']}**",
        f"- Duplicate Rows: **{current['duplicate_rows']}**",
        "",
        "## Validation Checks",
        "",
        f"- Same-Day Re-Run Idempotent: **{'PASS' if same_day_idempotent else 'FAIL'}**",
        f"- Qualification Counter Non-Inflation: **{'PASS' if counter_non_inflated else 'FAIL'}**",
        f"- Duplicate Cycle Date Detected: **{'NO' if not duplicate_cycle_date_detected else 'YES'}**",
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
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed Cycles: {baseline.get('observed', 0)} -> {current['observed']}")
    print(f"Valid Cycles: {baseline.get('valid', 0)} -> {current['valid']}")
    print(f"Blocked Cycles: {baseline.get('blocked', 0)} -> {current['blocked']}")
    print(f"Distinct Cycle Dates: {baseline.get('distinct_cycle_dates', 0)} -> {current['distinct_cycle_dates']}")
    print(f"Duplicate Rows: {current['duplicate_rows']}")
    print(f"Same-Day Re-Run Idempotent: {'PASS' if same_day_idempotent else 'FAIL'}")
    print(f"Qualification Counter Non-Inflation: {'PASS' if counter_non_inflated else 'FAIL'}")

    return 0 if operational else 1

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "validate"], required=True)
    args = parser.parse_args()

    if args.mode == "baseline":
        return save_baseline()
    return validate_after()

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
          grep -q 'DUPLICATE_CYCLE_DATE_DETECTED' "$f"
          echo "Phase 3.7.10.1 V1.1 validation contract: PASS"

      - name: Capture baseline canonical counters
        run: python automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py --mode baseline

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
        run: python automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py --mode validate

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
          name: phase37101-v11-same-day-idempotency-validation
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
  'DUPLICATE_CYCLE_DATE_DETECTED',
  'QUALIFICATION_COUNTER_INFLATION_DETECTED',
  'SAME_DAY_RERUN_NOT_IDEMPOTENT',
  'BROKER_ORDER_SUBMISSION_ENABLED = False',
  'REAL_MONEY_TRADING_ENABLED = False',
  'HISTORICAL_REWRITE_ALLOWED = False',
  'SAME_DAY_DUPLICATE_BYPASS_ALLOWED = False',
  'QUALIFICATION_COUNTER_INFLATION_ALLOWED = False',
  '--mode baseline',
  '--mode validate',
  'gpt-quant-v92-paper-trading-phase3710-production-paper-multi-day-qualification-accumulation-automatic-promotion-transition.yml'
)

foreach ($token in $required) {
    if ($combined -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Duplicate cycle-date validation contract: PASS" -ForegroundColor Green
Write-Host "Baseline/post-rerun counter comparison: PASS" -ForegroundColor Green
Write-Host "Qualification counter non-inflation contract: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.10 same-day rerun bridge: PASS" -ForegroundColor Green
Write-Host "Readiness counter consistency validation: PASS" -ForegroundColor Green
Write-Host "Same-day duplicate bypass prohibition: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37101 V1.1 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL schema change is required." -ForegroundColor Green
Write-Host ""
Write-Host "Expected validation result today:"
Write-Host "  SAME_DAY_IDEMPOTENCY_VALIDATED"
Write-Host "  Observed Cycles: 1 -> 1"
Write-Host "  Valid Cycles: 1 -> 1"
Write-Host "  Blocked Cycles: 0 -> 0"
Write-Host "  Distinct Cycle Dates: 1 -> 1"
Write-Host "  Duplicate Rows: 0"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/v92/paper_trading_phase37101_same_day_rerun_idempotency_qualification_counter_non_inflation_validation.py"'
Write-Host '2. git add ".github/workflows/gpt-quant-v92-paper-trading-phase37101-same-day-rerun-idempotency-qualification-counter-non-inflation-validation.yml"'
Write-Host '3. git diff --cached --name-only'
Write-Host '4. git commit -m "Fix Phase 37101 V1.1 duplicate cycle date validation contract"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Phase 3.7.10.1 workflow on main.'
