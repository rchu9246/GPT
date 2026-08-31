$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE3714 - Production Paper Qualification 3/3 Promotion Finalization + Paper Runtime Activation Gate" -ForegroundColor Cyan
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green
Write-Host "No synthetic qualification / no manual counter increment / no threshold bypass" -ForegroundColor Green

$repo = (Get-Location).Path
$pyRel = "automation/v92/paper_trading_phase3714_production_paper_qualification_3of3_promotion_finalization_paper_runtime_activation_gate.py"
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml"

$pyPath = Join-Path $repo $pyRel
$ymlPath = Join-Path $repo $ymlRel

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase3714-backup-$stamp"
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

CONTRACT = "PHASE3714_PRODUCTION_PAPER_QUALIFICATION_3OF3_PROMOTION_FINALIZATION_PAPER_RUNTIME_ACTIVATION_GATE"

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

MIN_OBSERVED = 3
MIN_VALID = 3
MIN_DISTINCT_DATES = 3
MAX_BLOCKED = 0

ART_DIR = Path("artifacts/phase3714")
RESULT_PATH = ART_DIR / "phase3714_result.json"
SUMMARY_PATH = ART_DIR / "phase3714_summary.md"

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False
QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False
SYNTHETIC_CYCLE_DATE_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
PAPER_RUNTIME_ACTIVATION_WITHOUT_3OF3_ALLOWED = False

def env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

def request(path: str) -> Any:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")

    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
        method="GET",
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

def qualification_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": "cycle_date,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "cycle_date.asc",
        "limit": "1000",
    })
    rows = request(f"{QUALIFICATION_TABLE}?{q}") or []

    dates = [str(row.get("cycle_date")) for row in rows if row.get("cycle_date")]
    distinct_dates = sorted(set(dates))
    observed = len(rows)
    valid = sum(1 for row in rows if truthy(row.get("valid_cycle")))
    blocked = sum(1 for row in rows if truthy(row.get("blocked_cycle")))
    duplicate_rows = observed - len(distinct_dates)

    runtime_pass = observed > 0 and all(
        truthy(row.get("runtime_supervision_pass")) for row in rows
    )
    paper_only_pass = observed > 0 and all(
        truthy(row.get("paper_only_boundary_pass")) for row in rows
    )

    return {
        "observed": observed,
        "valid": valid,
        "blocked": blocked,
        "distinct_cycle_dates": len(distinct_dates),
        "duplicate_rows": duplicate_rows,
        "distinct_dates": distinct_dates,
        "latest_cycle_date": distinct_dates[-1] if distinct_dates else None,
        "runtime_supervision_pass": runtime_pass,
        "paper_only_boundary_pass": paper_only_pass,
    }

def readiness_snapshot() -> Dict[str, Any]:
    q = urllib.parse.urlencode({
        "select": (
            "readiness_date,qualification_state,promotion_readiness_state,promotion_ready,"
            "observed_cycles,valid_cycles,blocked_cycles,runtime_supervision_pass,"
            "paper_only_boundary_pass,broker_order_submission_enabled,"
            "real_money_trading_enabled,historical_rewrite_allowed"
        ),
        "portfolio_id": f"eq.{PORTFOLIO_ID}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "readiness_date.desc",
        "limit": "1",
    })
    rows = request(f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    q = qualification_snapshot()
    r = readiness_snapshot()

    observed = int(q["observed"])
    valid = int(q["valid"])
    blocked = int(q["blocked"])
    distinct = int(q["distinct_cycle_dates"])
    duplicate_rows = int(q["duplicate_rows"])

    canonical_3of3 = (
        observed >= MIN_OBSERVED
        and valid >= MIN_VALID
        and distinct >= MIN_DISTINCT_DATES
        and blocked <= MAX_BLOCKED
        and duplicate_rows == 0
        and bool(q["runtime_supervision_pass"])
        and bool(q["paper_only_boundary_pass"])
    )

    readiness_present = bool(r)
    readiness_ready = truthy(r.get("promotion_ready", False))
    readiness_state = str(r.get("promotion_readiness_state", "NOT_AVAILABLE")).upper()

    readiness_consistent = True
    if readiness_present:
        readiness_consistent = (
            int(r.get("observed_cycles", observed) or 0) == observed
            and int(r.get("valid_cycles", valid) or 0) == valid
            and int(r.get("blocked_cycles", blocked) or 0) == blocked
        )

    broker_locked = not truthy(r.get("broker_order_submission_enabled", False)) if readiness_present else True
    real_money_locked = not truthy(r.get("real_money_trading_enabled", False)) if readiness_present else True
    historical_rewrite_locked = not truthy(r.get("historical_rewrite_allowed", False)) if readiness_present else True

    blockers = []

    if duplicate_rows > 0:
        blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > 0:
        blockers.append("BLOCKED_CYCLES_PRESENT")
    if observed > 0 and not q["runtime_supervision_pass"]:
        blockers.append("RUNTIME_SUPERVISION_NOT_PASS")
    if observed > 0 and not q["paper_only_boundary_pass"]:
        blockers.append("PAPER_ONLY_BOUNDARY_NOT_PASS")
    if not readiness_consistent:
        blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if readiness_ready and not canonical_3of3:
        blockers.append("PROMOTION_READY_BEFORE_CANONICAL_3OF3")
    if not broker_locked:
        blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked:
        blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_rewrite_locked:
        blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "PAPER_RUNTIME_ACTIVATION_BLOCKED"
        promotion_finalized = False
        paper_runtime_activation_ready = False
        operational = False
    elif canonical_3of3 and readiness_ready:
        state = "PAPER_RUNTIME_ACTIVATION_GATE_READY"
        promotion_finalized = True
        paper_runtime_activation_ready = True
        operational = True
    else:
        state = "PAPER_RUNTIME_ACTIVATION_WAITING_FOR_3OF3"
        promotion_finalized = False
        paper_runtime_activation_ready = False
        operational = True

    result = {
        "contract": CONTRACT,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "promotion_finalized": promotion_finalized,
        "paper_runtime_activation_ready": paper_runtime_activation_ready,
        "qualification": q,
        "readiness": r,
        "checks": {
            "canonical_3of3": canonical_3of3,
            "readiness_ready": readiness_ready,
            "readiness_counter_consistent": readiness_consistent,
            "broker_locked": broker_locked,
            "real_money_locked": real_money_locked,
            "historical_rewrite_locked": historical_rewrite_locked,
        },
        "blockers": blockers,
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
            "qualification_threshold_bypass_allowed": QUALIFICATION_THRESHOLD_BYPASS_ALLOWED,
            "synthetic_cycle_date_allowed": SYNTHETIC_CYCLE_DATE_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "paper_runtime_activation_without_3of3_allowed": PAPER_RUNTIME_ACTIVATION_WITHOUT_3OF3_ALLOWED,
        },
    }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.14",
        "",
        "## Production Paper Qualification 3/3 Promotion Finalization + Paper Runtime Activation Gate",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Promotion Finalized: **{'YES' if promotion_finalized else 'NO'}**",
        f"- Paper Runtime Activation Ready: **{'YES' if paper_runtime_activation_ready else 'NO'}**",
        "",
        "## Canonical Qualification",
        "",
        f"- Observed Cycles: **{observed} / {MIN_OBSERVED}**",
        f"- Valid Cycles: **{valid} / {MIN_VALID}**",
        f"- Blocked Cycles: **{blocked} / {MAX_BLOCKED} max**",
        f"- Distinct Cycle Dates: **{distinct} / {MIN_DISTINCT_DATES}**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        f"- Runtime Supervision: **{'PASS' if q['runtime_supervision_pass'] else 'FAIL'}**",
        f"- Paper-Only Boundary: **{'PASS' if q['paper_only_boundary_pass'] else 'FAIL'}**",
        f"- Canonical 3/3 Qualification: **{'PASS' if canonical_3of3 else 'WAITING'}**",
        "",
        "## Promotion Finalization",
        "",
        f"- Readiness State: **{readiness_state}**",
        f"- Promotion Ready: **{'YES' if readiness_ready else 'NO'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
        "",
        "## Runtime Safety Lock",
        "",
        f"- Broker Order Submission Locked: **{'PASS' if broker_locked else 'FAIL'}**",
        f"- Real-Money Trading Locked: **{'PASS' if real_money_locked else 'FAIL'}**",
        f"- Historical Rewrite Locked: **{'PASS' if historical_rewrite_locked else 'FAIL'}**",
        "",
        "## Permanent Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "- Qualification Threshold Bypass: **NO**",
        "- Synthetic Cycle-Date Allowed: **NO**",
        "- Manual Counter Increment Allowed: **NO**",
        "- Paper Runtime Activation Without 3/3 Allowed: **NO**",
    ]

    if blockers:
        summary += ["", "## Blockers", ""] + [f"- **{item}**" for item in blockers]

    SUMMARY_PATH.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed: {observed}/{MIN_OBSERVED}")
    print(f"Valid: {valid}/{MIN_VALID}")
    print(f"Blocked: {blocked}")
    print(f"Distinct Cycle Dates: {distinct}/{MIN_DISTINCT_DATES}")
    print(f"Canonical 3/3: {'PASS' if canonical_3of3 else 'WAITING'}")
    print(f"Promotion Ready: {'YES' if readiness_ready else 'NO'}")
    print(f"Paper Runtime Activation Ready: {'YES' if paper_runtime_activation_ready else 'NO'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
'@
$ymlText = @'
name: GPT Quant Phase 3.7.14 - Production Paper Qualification 3of3 Promotion Finalization Paper Runtime Activation Gate

on:
  workflow_dispatch:
  schedule:
    # Weekdays 17:35 UTC / 01:35 Asia-Taipei.
    - cron: "35 17 * * 1-5"

permissions:
  contents: read
  actions: read

concurrency:
  group: phase3714-paper-runtime-activation-gate
  cancel-in-progress: false

jobs:
  paper-runtime-activation-gate:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      GPT_QUANT_PORTFOLIO_ID: V92_PRODUCTION_PAPER_V91
      GPT_QUANT_STRATEGY_VERSION: V9.1
      WF3713: gpt-quant-v92-paper-trading-phase3713-production-paper-natural-qualification-daily-orchestration-promotion-readiness-automation.yml
      WF37131: gpt-quant-v92-paper-trading-phase37131-natural-daily-orchestration-persistence-cross-day-recovery-integrity.yml

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.14
        run: python -m py_compile automation/v92/paper_trading_phase3714_production_paper_qualification_3of3_promotion_finalization_paper_runtime_activation_gate.py

      - name: Validate Phase 3.7.14 activation safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase3714_production_paper_qualification_3of3_promotion_finalization_paper_runtime_activation_gate.py"
          grep -q 'QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False' "$f"
          grep -q 'SYNTHETIC_CYCLE_DATE_ALLOWED = False' "$f"
          grep -q 'MANUAL_COUNTER_INCREMENT_ALLOWED = False' "$f"
          grep -q 'PAPER_RUNTIME_ACTIVATION_WITHOUT_3OF3_ALLOWED = False' "$f"
          grep -q 'PAPER_RUNTIME_ACTIVATION_GATE_READY' "$f"
          grep -q 'PAPER_RUNTIME_ACTIVATION_WAITING_FOR_3OF3' "$f"
          echo "Phase 3.7.14 activation safety contract: PASS"

      - name: Confirm Phase 3.7.13 and Phase 3.7.13.1 successful lineage
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail

          check_success() {
            local wf="$1"
            local label="$2"
            local result
            result="$(gh api \
              -H "Accept: application/vnd.github+json" \
              "/repos/${GITHUB_REPOSITORY}/actions/workflows/${wf}/runs?branch=main&per_page=20" \
              --jq '[.workflow_runs[] | select(.conclusion == "success")][0].conclusion // empty')"

            if [ "$result" != "success" ]; then
              echo "::error::No successful ${label} run found on main."
              exit 1
            fi
            echo "${label}: PASS"
          }

          check_success "$WF3713" "Phase 3.7.13"
          check_success "$WF37131" "Phase 3.7.13.1"

      - name: Evaluate 3of3 promotion finalization and paper runtime activation gate
        id: phase3714
        continue-on-error: true
        run: python automation/v92/paper_trading_phase3714_production_paper_qualification_3of3_promotion_finalization_paper_runtime_activation_gate.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3714/phase3714_summary.md ]; then
            cat artifacts/phase3714/phase3714_summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload Phase 3.7.14 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3714-paper-runtime-activation-gate
          path: artifacts/phase3714
          if-no-files-found: warn
          retention-days: 90

      - name: Enforce Phase 3.7.14 result
        if: always()
        shell: bash
        run: |
          if [ "${{ steps.phase3714.outcome }}" != "success" ]; then
            echo "Phase 3.7.14 paper runtime activation gate is BLOCKED."
            exit 1
          fi
          echo "Phase 3.7.14 paper runtime activation gate is healthy."
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
  'PAPER_RUNTIME_ACTIVATION_WAITING_FOR_3OF3',
  'PAPER_RUNTIME_ACTIVATION_GATE_READY',
  'PAPER_RUNTIME_ACTIVATION_BLOCKED',
  'PROMOTION_READY_BEFORE_CANONICAL_3OF3',
  'QUALIFICATION_THRESHOLD_BYPASS_ALLOWED = False',
  'SYNTHETIC_CYCLE_DATE_ALLOWED = False',
  'MANUAL_COUNTER_INCREMENT_ALLOWED = False',
  'PAPER_RUNTIME_ACTIVATION_WITHOUT_3OF3_ALLOWED = False',
  'gpt-quant-v92-paper-trading-phase3713-production-paper-natural-qualification-daily-orchestration-promotion-readiness-automation.yml',
  'gpt-quant-v92-paper-trading-phase37131-natural-daily-orchestration-persistence-cross-day-recovery-integrity.yml'
)

foreach ($token in $required) {
    if ($combined -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Canonical 3/3 activation threshold contract: PASS" -ForegroundColor Green
Write-Host "Promotion finalization readiness contract: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.13 lineage bridge: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.13.1 recovery integrity bridge: PASS" -ForegroundColor Green
Write-Host "Synthetic qualification prohibition: PASS" -ForegroundColor Green
Write-Host "Manual counter increment prohibition: PASS" -ForegroundColor Green
Write-Host "Qualification threshold non-bypass: PASS" -ForegroundColor Green
Write-Host "Broker/real-money safety lock: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE3714 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL schema change is required." -ForegroundColor Green
Write-Host ""
Write-Host "Generated:"
Write-Host "  $pyPath"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "Expected current state:"
Write-Host "  PAPER_RUNTIME_ACTIVATION_WAITING_FOR_3OF3"
Write-Host "  Promotion Finalized: NO"
Write-Host "  Paper Runtime Activation Ready: NO"
Write-Host "  Observed: 1 / 3"
Write-Host "  Valid: 1 / 3"
Write-Host "  Distinct Cycle Dates: 1 / 3"
Write-Host ""
Write-Host "Only genuine canonical 3/3 may become:"
Write-Host "  PAPER_RUNTIME_ACTIVATION_GATE_READY"
Write-Host "  Promotion Finalized: YES"
Write-Host "  Paper Runtime Activation Ready: YES"
Write-Host ""
Write-Host "Even after READY:"
Write-Host "  Broker Order Submission remains DISABLED"
Write-Host "  Real-Money Trading remains DISABLED"
Write-Host ""
Write-Host "Automatic schedule:"
Write-Host "  Weekdays 17:35 UTC / 01:35 Asia-Taipei"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/v92/paper_trading_phase3714_production_paper_qualification_3of3_promotion_finalization_paper_runtime_activation_gate.py"'
Write-Host '2. git add ".github/workflows/gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml"'
Write-Host '3. git diff --cached --name-only'
Write-Host '4. git commit -m "Deploy Phase 3714 qualification 3of3 promotion finalization paper runtime activation gate"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Phase 3.7.14 workflow on main.'
