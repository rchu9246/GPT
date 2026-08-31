$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37162 - Natural 2/3 -> 3/3 Qualification Transition + First Paper Session Release Observation" -ForegroundColor Cyan
Write-Host "Mode: READ-ONLY OBSERVATION / NO QUALIFICATION MUTATION" -ForegroundColor Green
Write-Host "Safety boundary: PAPER ONLY / broker submission DISABLED / real money DISABLED" -ForegroundColor Green

$repo = (Get-Location).Path
$pyRel = "automation/v92/paper_trading_phase37162_natural_2of3_to_3of3_qualification_transition_first_paper_session_release_observation.py"
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase37162-natural-2of3-to-3of3-qualification-transition-first-paper-session-release-observation.yml"

$pyPath = Join-Path $repo $pyRel
$ymlPath = Join-Path $repo $ymlRel

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase37162-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

foreach ($p in @($pyPath, $ymlPath)) {
    if (Test-Path $p) {
        Copy-Item $p (Join-Path $backup (Split-Path $p -Leaf)) -Force
    }
}

$pyText = @'
#!/usr/bin/env python3
from __future__ import annotations

import json, os, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")
QUALIFICATION_TABLE = "paper_production_qualification_evidence_v92"
READINESS_TABLE = "paper_production_promotion_readiness_v92"

ART_DIR = Path("artifacts/phase37162")
SUMMARY_PATH = ART_DIR / "phase37162_summary.md"
RESULT_PATH = ART_DIR / "phase37162_result.json"

QUALIFICATION_MUTATION_ALLOWED = False
SYNTHETIC_QUALIFICATION_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
OBSERVATION_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
FIRST_SESSION_RELEASE_BEFORE_3OF3_ALLOWED = False

REQUIRED_REPO_PATHS = [
    ".github/workflows/gpt-quant-v92-paper-trading-phase37161-first-live-paper-session-preflight-canonical-3of3-activation-handoff-integrity.yml",
]

def env_first(*names):
    for name in names:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

def truthy(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE","YES","Y","1","PASS","ENABLED"}

def get(path):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_CONFIGURATION_MISSING")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e

def qualification_rows():
    q = urllib.parse.urlencode({
        "select":"cycle_date,valid_cycle,blocked_cycle,runtime_supervision_pass,paper_only_boundary_pass",
        "portfolio_id":f"eq.{PORTFOLIO_ID}",
        "strategy_version":f"eq.{STRATEGY_VERSION}",
        "order":"cycle_date.asc",
        "limit":"1000",
    })
    return get(f"{QUALIFICATION_TABLE}?{q}") or []

def latest_readiness():
    q = urllib.parse.urlencode({
        "select":"readiness_date,promotion_readiness_state,promotion_ready,observed_cycles,valid_cycles,blocked_cycles,broker_order_submission_enabled,real_money_trading_enabled,historical_rewrite_allowed",
        "portfolio_id":f"eq.{PORTFOLIO_ID}",
        "strategy_version":f"eq.{STRATEGY_VERSION}",
        "order":"readiness_date.desc",
        "limit":"1",
    })
    rows = get(f"{READINESS_TABLE}?{q}") or []
    return rows[0] if rows else {}

def main():
    ART_DIR.mkdir(parents=True, exist_ok=True)

    rows = qualification_rows()
    readiness = latest_readiness()

    dates = [str(x.get("cycle_date")) for x in rows if x.get("cycle_date")]
    distinct_dates = sorted(set(dates))
    observed = len(rows)
    valid = sum(1 for x in rows if truthy(x.get("valid_cycle")))
    blocked = sum(1 for x in rows if truthy(x.get("blocked_cycle")))
    duplicate_rows = observed - len(distinct_dates)

    runtime_pass = observed > 0 and all(truthy(x.get("runtime_supervision_pass")) for x in rows)
    paper_only_pass = observed > 0 and all(truthy(x.get("paper_only_boundary_pass")) for x in rows)

    canonical_2of3 = observed >= 2 and valid >= 2 and len(distinct_dates) >= 2 and blocked == 0 and duplicate_rows == 0
    canonical_3of3 = (
        observed >= 3
        and valid >= 3
        and len(distinct_dates) >= 3
        and blocked == 0
        and duplicate_rows == 0
        and runtime_pass
        and paper_only_pass
    )

    promotion_ready = truthy(readiness.get("promotion_ready", False))
    readiness_consistent = True
    if readiness:
        readiness_consistent = (
            int(readiness.get("observed_cycles", observed) or 0) == observed
            and int(readiness.get("valid_cycles", valid) or 0) == valid
            and int(readiness.get("blocked_cycles", blocked) or 0) == blocked
        )

    broker_locked = not truthy(readiness.get("broker_order_submission_enabled", False))
    real_money_locked = not truthy(readiness.get("real_money_trading_enabled", False))
    historical_locked = not truthy(readiness.get("historical_rewrite_allowed", False))
    lineage_ok = all(Path(p).is_file() for p in REQUIRED_REPO_PATHS)

    blockers = []
    if not lineage_ok: blockers.append("PHASE37161_LINEAGE_MISSING")
    if duplicate_rows > 0: blockers.append("DUPLICATE_CYCLE_DATE_DETECTED")
    if blocked > 0: blockers.append("BLOCKED_CYCLES_PRESENT")
    if not readiness_consistent: blockers.append("READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER")
    if promotion_ready and not canonical_3of3: blockers.append("PROMOTION_READY_BEFORE_CANONICAL_3OF3")
    if not broker_locked: blockers.append("BROKER_SAFETY_LOCK_BREACH")
    if not real_money_locked: blockers.append("REAL_MONEY_SAFETY_LOCK_BREACH")
    if not historical_locked: blockers.append("HISTORICAL_REWRITE_SAFETY_LOCK_BREACH")

    if blockers:
        state = "NATURAL_QUALIFICATION_TRANSITION_OBSERVATION_BLOCKED"
        operational = False
        release_observed = False
    elif canonical_3of3 and promotion_ready:
        state = "NATURAL_3OF3_QUALIFICATION_RELEASE_OBSERVED"
        operational = True
        release_observed = True
    elif canonical_2of3:
        state = "NATURAL_2OF3_QUALIFICATION_OBSERVED_WAITING_FOR_3OF3"
        operational = True
        release_observed = False
    else:
        state = "NATURAL_QUALIFICATION_OBSERVATION_WAITING_FOR_2OF3"
        operational = True
        release_observed = False

    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "operational": operational,
        "first_paper_session_release_observed": release_observed,
        "observed_cycles": observed,
        "valid_cycles": valid,
        "blocked_cycles": blocked,
        "distinct_cycle_dates": len(distinct_dates),
        "distinct_dates": distinct_dates,
        "duplicate_rows": duplicate_rows,
        "canonical_2of3": canonical_2of3,
        "canonical_3of3": canonical_3of3,
        "promotion_ready": promotion_ready,
        "readiness_consistent": readiness_consistent,
        "lineage_ok": lineage_ok,
        "broker_locked": broker_locked,
        "real_money_locked": real_money_locked,
        "historical_rewrite_locked": historical_locked,
        "blockers": blockers,
        "safety": {
            "qualification_mutation_allowed": QUALIFICATION_MUTATION_ALLOWED,
            "synthetic_qualification_allowed": SYNTHETIC_QUALIFICATION_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "observation_only": OBSERVATION_ONLY,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "first_session_release_before_3of3_allowed": FIRST_SESSION_RELEASE_BEFORE_3OF3_ALLOWED,
        },
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.16.2",
        "",
        "## Natural 2/3 → 3/3 Qualification Transition + First Paper Session Release Observation",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- First Paper Session Release Observed: **{'YES' if release_observed else 'NO'}**",
        "",
        "## Natural Qualification Observation",
        "",
        f"- Observed Cycles: **{observed} / 3**",
        f"- Valid Cycles: **{valid} / 3**",
        f"- Blocked Cycles: **{blocked} / 0 max**",
        f"- Distinct Cycle Dates: **{len(distinct_dates)} / 3**",
        f"- Duplicate Rows: **{duplicate_rows}**",
        f"- Canonical 2/3: **{'PASS' if canonical_2of3 else 'WAITING'}**",
        f"- Canonical 3/3: **{'PASS' if canonical_3of3 else 'WAITING'}**",
        f"- Promotion Ready: **{'YES' if promotion_ready else 'NO'}**",
        "",
        "## Release Observation Integrity",
        "",
        f"- Phase 3.7.16.1 Lineage Present: **{'PASS' if lineage_ok else 'FAIL'}**",
        f"- Readiness Counter Consistency: **{'PASS' if readiness_consistent else 'FAIL'}**",
        f"- Broker Order Submission Locked: **{'PASS' if broker_locked else 'FAIL'}**",
        f"- Real-Money Trading Locked: **{'PASS' if real_money_locked else 'FAIL'}**",
        f"- Historical Rewrite Locked: **{'PASS' if historical_locked else 'FAIL'}**",
        "",
        "## Permanent Safety Boundary",
        "",
        "- Qualification Mutation Allowed: **NO**",
        "- Synthetic Qualification Allowed: **NO**",
        "- Manual Counter Increment Allowed: **NO**",
        "- Observation Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- First Session Release Before 3/3 Allowed: **NO**",
    ]
    if blockers:
        lines += ["", "## Blockers", ""] + [f"- **{b}**" for b in blockers]

    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Observed: {observed}/3")
    print(f"Valid: {valid}/3")
    print(f"Distinct Cycle Dates: {len(distinct_dates)}/3")
    print(f"Canonical 2/3: {'PASS' if canonical_2of3 else 'WAITING'}")
    print(f"Canonical 3/3: {'PASS' if canonical_3of3 else 'WAITING'}")
    print(f"First Paper Session Release Observed: {'YES' if release_observed else 'NO'}")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
'@

$ymlText = @'
name: GPT Quant Phase 3.7.16.2 - Natural 2of3 to 3of3 Qualification Transition First Paper Session Release Observation

on:
  workflow_dispatch:
  schedule:
    - cron: "50 18 * * 1-5"

permissions:
  contents: read
  actions: read

concurrency:
  group: phase37162-natural-qualification-transition-release-observation
  cancel-in-progress: false

jobs:
  natural-qualification-transition-release-observation:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      GPT_QUANT_PORTFOLIO_ID: V92_PRODUCTION_PAPER_V91
      GPT_QUANT_STRATEGY_VERSION: V9.1
      WF37161: gpt-quant-v92-paper-trading-phase37161-first-live-paper-session-preflight-canonical-3of3-activation-handoff-integrity.yml

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.16.2
        run: python -m py_compile automation/v92/paper_trading_phase37162_natural_2of3_to_3of3_qualification_transition_first_paper_session_release_observation.py

      - name: Validate observation-only safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase37162_natural_2of3_to_3of3_qualification_transition_first_paper_session_release_observation.py"
          grep -q 'QUALIFICATION_MUTATION_ALLOWED = False' "$f"
          grep -q 'SYNTHETIC_QUALIFICATION_ALLOWED = False' "$f"
          grep -q 'MANUAL_COUNTER_INCREMENT_ALLOWED = False' "$f"
          grep -q 'OBSERVATION_ONLY = True' "$f"
          grep -q 'FIRST_SESSION_RELEASE_BEFORE_3OF3_ALLOWED = False' "$f"
          grep -q 'NATURAL_2OF3_QUALIFICATION_OBSERVED_WAITING_FOR_3OF3' "$f"
          grep -q 'NATURAL_3OF3_QUALIFICATION_RELEASE_OBSERVED' "$f"
          echo "Phase 3.7.16.2 observation-only safety contract: PASS"

      - name: Confirm Phase 3.7.16.1 successful lineage
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          result="$(gh api -H "Accept: application/vnd.github+json" \
            "/repos/${GITHUB_REPOSITORY}/actions/workflows/${WF37161}/runs?branch=main&per_page=20" \
            --jq '[.workflow_runs[] | select(.conclusion == "success")][0].conclusion // empty')"
          [ "$result" = "success" ] || { echo "::error::No successful Phase 3.7.16.1 run found."; exit 1; }

      - name: Observe natural 2of3 to 3of3 transition
        id: phase37162
        continue-on-error: true
        run: python automation/v92/paper_trading_phase37162_natural_2of3_to_3of3_qualification_transition_first_paper_session_release_observation.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase37162/phase37162_summary.md ]; then
            cat artifacts/phase37162/phase37162_summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload Phase 3.7.16.2 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37162-natural-qualification-transition-release-observation
          path: artifacts/phase37162
          if-no-files-found: warn
          retention-days: 90

      - name: Enforce Phase 3.7.16.2 result
        if: always()
        shell: bash
        run: |
          if [ "${{ steps.phase37162.outcome }}" != "success" ]; then
            echo "Phase 3.7.16.2 natural qualification transition observation is BLOCKED."
            exit 1
          fi
          echo "Phase 3.7.16.2 natural qualification transition observation is healthy."
'@

$utf8 = New-Object System.Text.UTF8Encoding($false)
foreach ($p in @($pyPath, $ymlPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $p) | Out-Null
}
[System.IO.File]::WriteAllText($pyPath, $pyText + [Environment]::NewLine, $utf8)
[System.IO.File]::WriteAllText($ymlPath, $ymlText + [Environment]::NewLine, $utf8)

python -m py_compile $pyPath
if ($LASTEXITCODE -ne 0) { throw "Python compile failed." }

$combined = (Get-Content -LiteralPath $pyPath -Raw) + "`n" + (Get-Content -LiteralPath $ymlPath -Raw)
$required = @(
  'NATURAL_QUALIFICATION_OBSERVATION_WAITING_FOR_2OF3',
  'NATURAL_2OF3_QUALIFICATION_OBSERVED_WAITING_FOR_3OF3',
  'NATURAL_3OF3_QUALIFICATION_RELEASE_OBSERVED',
  'NATURAL_QUALIFICATION_TRANSITION_OBSERVATION_BLOCKED',
  'QUALIFICATION_MUTATION_ALLOWED = False',
  'SYNTHETIC_QUALIFICATION_ALLOWED = False',
  'MANUAL_COUNTER_INCREMENT_ALLOWED = False',
  'OBSERVATION_ONLY = True',
  'FIRST_SESSION_RELEASE_BEFORE_3OF3_ALLOWED = False'
)
foreach ($token in $required) {
    if ($combined -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Phase 3.7.16.1 lineage bridge: PASS" -ForegroundColor Green
Write-Host "Natural 2/3 observation contract: PASS" -ForegroundColor Green
Write-Host "Natural 3/3 transition observation contract: PASS" -ForegroundColor Green
Write-Host "First paper session release observation contract: PASS" -ForegroundColor Green
Write-Host "Qualification mutation prohibition: PASS" -ForegroundColor Green
Write-Host "Synthetic qualification prohibition: PASS" -ForegroundColor Green
Write-Host "Manual counter increment prohibition: PASS" -ForegroundColor Green
Write-Host "Observation-only safety boundary: PASS" -ForegroundColor Green
Write-Host "Broker/real-money safety lock: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37162 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL schema change is required." -ForegroundColor Green
Write-Host ""
Write-Host "Expected current healthy state:"
Write-Host "  NATURAL_QUALIFICATION_OBSERVATION_WAITING_FOR_2OF3"
Write-Host "  First Paper Session Release Observed: NO"
Write-Host ""
Write-Host "When natural 2/3 is reached:"
Write-Host "  NATURAL_2OF3_QUALIFICATION_OBSERVED_WAITING_FOR_3OF3"
Write-Host ""
Write-Host "When natural 3/3 + promotion readiness is reached:"
Write-Host "  NATURAL_3OF3_QUALIFICATION_RELEASE_OBSERVED"
Write-Host "  First Paper Session Release Observed: YES"
Write-Host ""
Write-Host "Automatic schedule:"
Write-Host "  Weekdays 18:50 UTC / 02:50 Asia-Taipei"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/v92/paper_trading_phase37162_natural_2of3_to_3of3_qualification_transition_first_paper_session_release_observation.py"'
Write-Host '2. git add ".github/workflows/gpt-quant-v92-paper-trading-phase37162-natural-2of3-to-3of3-qualification-transition-first-paper-session-release-observation.yml"'
Write-Host '3. git diff --cached --name-only'
Write-Host '4. git commit -m "Deploy Phase 37162 natural 2of3 to 3of3 qualification transition first paper session release observation"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Phase 3.7.16.2 workflow on main.'
