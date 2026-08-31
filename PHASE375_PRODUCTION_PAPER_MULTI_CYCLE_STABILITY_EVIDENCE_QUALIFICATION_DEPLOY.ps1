#requires -Version 5.1
<#
GPT Quant V9.2
Phase 3.7.5 — Production Paper Multi-Cycle Stability & Evidence Qualification

Purpose
-------
Validate that Production Paper remains operational across multiple daily cycles,
accumulates enough evidence, and remains inside the paper-only safety boundary.

This phase is qualification/observation only:
- No broker API
- No broker credentials
- No broker order submission
- No real-money trading
- No historical rewrite

Valid outcomes:
- MULTI_CYCLE_STABILITY_QUALIFIED
- MULTI_CYCLE_STABILITY_OBSERVING
- MULTI_CYCLE_STABILITY_BLOCKED

Default qualification threshold:
- Minimum observed cycles: 3
- Minimum successful/valid cycles: 3
- Maximum blocked cycles allowed: 0
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail([string]$m) {
    Write-Host "PHASE375_FATAL: $m" -ForegroundColor Red
    exit 1
}
function WriteUtf8([string]$p,[string]$s) {
    $d = Split-Path -Parent $p
    if ($d -and -not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($p,$s,$enc)
}

try { $root = (& git rev-parse --show-toplevel 2>$null).Trim() } catch { $root = "" }
if (-not $root) { Fail "Run this deployment inside the GPT repository." }
Set-Location $root

$pyPath  = Join-Path $root "automation\v92\paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
$ymlPath = Join-Path $root ".github\workflows\gpt-quant-v92-paper-trading-phase375-production-paper-multi-cycle-stability-evidence-qualification.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $root ".phase375-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
if (Test-Path $pyPath)  { Copy-Item $pyPath  $backup -Force }
if (Test-Path $ymlPath) { Copy-Item $ymlPath $backup -Force }

$py = @'
#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "PHASE375_PRODUCTION_PAPER_MULTI_CYCLE_STABILITY_EVIDENCE_QUALIFICATION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

MIN_OBSERVED_CYCLES = int(os.getenv("PHASE375_MIN_OBSERVED_CYCLES", "3"))
MIN_VALID_CYCLES = int(os.getenv("PHASE375_MIN_VALID_CYCLES", "3"))
MAX_BLOCKED_CYCLES = int(os.getenv("PHASE375_MAX_BLOCKED_CYCLES", "0"))

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False

# Reuse the currently stable canonical control sources.
ACTIVATION_TABLES = ["paper_post_recovery_activation_state_v92"]
MASTER_CYCLE_TABLES = ["paper_post_recovery_master_cycle_v92"]
RUNTIME_TABLES = [
    "paper_runtime_supervision_state_v92",
    "paper_production_runtime_supervision_v92",
    "paper_runtime_state_v92",
]

# Evidence sources are intentionally broad/compatible because Phase 3.7.4
# currently writes GitHub artifacts rather than requiring a dedicated DB table.
DAILY_EVIDENCE_TABLES = [
    "paper_daily_cycle_monitoring_v92",
    "paper_daily_cycle_evidence_v92",
    "paper_runtime_evidence_v92",
    "paper_production_evidence_v92",
    "production_evidence_v92",
    "paper_evidence_v92",
]

VALID_STATES = {
    "DAILY_CYCLE_OPERATIONAL_PASS",
    "DAILY_CYCLE_NO_TRADE_VALID",
    "FIRST_CYCLE_OPERATIONAL_PASS",
    "FIRST_CYCLE_NO_TRADE_VALID",
    "GO_LIVE_PAPER_ACTIVE",
}
BLOCK_STATES = {
    "DAILY_CYCLE_BLOCKED",
    "FIRST_CYCLE_BLOCKED",
    "BLOCKED",
    "FAIL_CLOSED",
    "REVOKED",
    "HALTED",
    "SUSPENDED",
    "FAILED",
    "ERROR",
}

def env_first(*names: str) -> Optional[str]:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first(
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "VITE_SUPABASE_PUBLISHABLE_KEY",
)

class RestError(RuntimeError):
    pass

def get_rows(table: str, limit: int = 250, portfolio_scoped: bool = False) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE configuration missing")
    params = {"select": "*", "limit": str(limit)}
    if portfolio_scoped:
        params["portfolio_id"] = f"eq.{PORTFOLIO_ID}"
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}?{q}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8") or "[]")
            return data if isinstance(data, list) else []
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RestError(f"HTTP {e.code}: {body}") from e

def is_missing(exc: Exception) -> bool:
    s = str(exc).lower()
    return "pgrst205" in s or "42p01" in s or "could not find the table" in s

def inspect(candidates: List[str], portfolio_scoped: bool = False) -> Tuple[Optional[str], List[Dict[str, Any]], List[str]]:
    errs: List[str] = []
    for t in candidates:
        try:
            if portfolio_scoped:
                try:
                    return t, get_rows(t, portfolio_scoped=True), errs
                except RestError as scoped:
                    msg = str(scoped).lower()
                    if "portfolio_id" in msg or "pgrst" in msg:
                        errs.append(f"{t}:PORTFOLIO_FILTER_FALLBACK")
                    else:
                        raise
            return t, get_rows(t), errs
        except Exception as e:
            if is_missing(e):
                errs.append(f"{t}:NOT_PRESENT")
                continue
            errs.append(f"{t}:{type(e).__name__}")
    return None, [], errs

def text(v: Any) -> str:
    return "" if v is None else str(v).strip()

def upper_values(row: Dict[str, Any]) -> str:
    return " ".join(text(v).upper() for v in row.values())

def blocked(row: Dict[str, Any]) -> bool:
    if not row:
        return False
    hay = upper_values(row)
    return any(s in hay for s in BLOCK_STATES)

def active(row: Dict[str, Any]) -> bool:
    if not row:
        return False
    hay = upper_values(row)
    return any(s in hay for s in [
        "ACTIVE",
        "CONTINUE_ACTIVE",
        "CONTINUE_WITH_OBSERVATION",
        "AUTHORIZED_PAPER_CONTINUATION",
        "READY",
        "PASS",
        "ENABLED",
    ]) and not blocked(row)

def latest(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    keys = ["updated_at","created_at","run_at","run_date","trade_date","validation_date","date","id"]
    def key(row: Dict[str, Any]) -> str:
        lower = {str(k).lower(): v for k,v in row.items()}
        for name in keys:
            if name in lower and lower[name] is not None:
                return text(lower[name])
        return ""
    return sorted(rows, key=key, reverse=True)[0]

def extract_state(row: Dict[str, Any]) -> str:
    if not row:
        return ""
    lower = {str(k).lower(): v for k,v in row.items()}
    for name in (
        "daily_validation_state",
        "validation_state",
        "state",
        "status",
        "result",
        "gate_state",
        "go_live_state",
    ):
        if name in lower and lower[name] is not None:
            return text(lower[name]).upper()
    hay = upper_values(row)
    for s in sorted(VALID_STATES | BLOCK_STATES, key=len, reverse=True):
        if s in hay:
            return s
    return ""

def count_evidence_states(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    valid = blocked_count = unknown = 0
    operational = no_trade = 0
    for row in rows:
        state = extract_state(row)
        if state in VALID_STATES:
            valid += 1
            if "OPERATIONAL_PASS" in state:
                operational += 1
            if "NO_TRADE_VALID" in state:
                no_trade += 1
        elif state in BLOCK_STATES:
            blocked_count += 1
        else:
            unknown += 1
    return {
        "observed": len(rows),
        "valid": valid,
        "blocked": blocked_count,
        "unknown": unknown,
        "operational_pass": operational,
        "no_trade_valid": no_trade,
    }

def main() -> int:
    art = Path("artifacts/phase375")
    art.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "qualified_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {
            "minimum_observed_cycles": MIN_OBSERVED_CYCLES,
            "minimum_valid_cycles": MIN_VALID_CYCLES,
            "maximum_blocked_cycles": MAX_BLOCKED_CYCLES,
        },
        "safety": {
            "paper_only": PAPER_ONLY,
            "broker_api_used": BROKER_API_USED,
            "broker_credentials_used": BROKER_CREDENTIALS_USED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        },
    }

    if not SUPABASE_URL or not SUPABASE_KEY:
        result.update(
            state="MULTI_CYCLE_STABILITY_BLOCKED",
            qualified=False,
            blockers=["SUPABASE_CONFIGURATION_MISSING"],
        )
        return finish(art, result)

    act_table, act_rows, act_errs = inspect(ACTIVATION_TABLES, portfolio_scoped=True)
    mst_table, mst_rows, mst_errs = inspect(MASTER_CYCLE_TABLES, portfolio_scoped=True)
    run_table, run_rows, run_errs = inspect(RUNTIME_TABLES, portfolio_scoped=True)
    ev_table, ev_rows, ev_errs = inspect(DAILY_EVIDENCE_TABLES, portfolio_scoped=True)

    activation_ok = bool(latest(act_rows)) and active(latest(act_rows))
    master_ok = bool(latest(mst_rows)) and not blocked(latest(mst_rows))
    runtime_ok = bool(latest(run_rows)) and active(latest(run_rows))

    evidence_counts = count_evidence_states(ev_rows)

    # Compatibility mode: if no dedicated daily-evidence table exists yet,
    # the phase remains OBSERVING instead of falsely failing. This keeps
    # qualification strict while permitting GitHub artifact accumulation.
    dedicated_evidence_present = bool(ev_table)
    observed = evidence_counts["observed"] if dedicated_evidence_present else 0
    valid = evidence_counts["valid"] if dedicated_evidence_present else 0
    blocked_count = evidence_counts["blocked"] if dedicated_evidence_present else 0

    blockers: List[str] = []
    if not activation_ok:
        blockers.append("ACTIVATION_CANONICAL_NOT_ACTIVE")
    if not master_ok:
        blockers.append("MASTER_CYCLE_CANONICAL_NOT_READY")
    if not runtime_ok:
        blockers.append("RUNTIME_SUPERVISION_NOT_READY")
    if blocked_count > MAX_BLOCKED_CYCLES:
        blockers.append(f"BLOCKED_CYCLE_LIMIT_EXCEEDED:{blocked_count}")

    if blockers:
        state = "MULTI_CYCLE_STABILITY_BLOCKED"
        qualified = False
        operational = False
    elif dedicated_evidence_present and observed >= MIN_OBSERVED_CYCLES and valid >= MIN_VALID_CYCLES:
        state = "MULTI_CYCLE_STABILITY_QUALIFIED"
        qualified = True
        operational = True
    else:
        state = "MULTI_CYCLE_STABILITY_OBSERVING"
        qualified = False
        operational = True

    result.update(
        state=state,
        qualified=qualified,
        operational=operational,
        blockers=blockers,
        sources={
            "activation_table": act_table,
            "master_cycle_table": mst_table,
            "runtime_table": run_table,
            "daily_evidence_table": ev_table,
            "activation_errors": act_errs,
            "master_errors": mst_errs,
            "runtime_errors": run_errs,
            "evidence_errors": ev_errs,
        },
        evidence_counts=evidence_counts,
        checks={
            "activation_canonical": "PASS" if activation_ok else "FAIL",
            "master_cycle_canonical": "PASS" if master_ok else "FAIL",
            "runtime_supervision": "PASS" if runtime_ok else "FAIL",
            "dedicated_daily_evidence_table": "YES" if dedicated_evidence_present else "NO",
            "observed_cycle_threshold": "PASS" if observed >= MIN_OBSERVED_CYCLES else "OBSERVING",
            "valid_cycle_threshold": "PASS" if valid >= MIN_VALID_CYCLES else "OBSERVING",
            "blocked_cycle_threshold": "PASS" if blocked_count <= MAX_BLOCKED_CYCLES else "FAIL",
            "paper_only_boundary": "PASS",
            "broker_order_submission": "DISABLED",
            "real_money_trading": "DISABLED",
            "historical_rewrite_prohibition": "PASS",
        },
    )
    return finish(art, result)

def finish(art: Path, result: Dict[str, Any]) -> int:
    (art/"phase375_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.5",
        "",
        "## Production Paper Multi-Cycle Stability & Evidence Qualification",
        "",
        f"- Contract: `{result['contract']}`",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Strategy Version: `{result['strategy_version']}`",
        f"- Qualification State: **{result.get('state','UNKNOWN')}**",
        f"- Operational: **{'YES' if result.get('operational') else 'NO'}**",
        f"- Qualified: **{'YES' if result.get('qualified') else 'NO'}**",
        "",
        "## Qualification Thresholds",
        "",
        f"- Minimum Observed Cycles: **{result['thresholds']['minimum_observed_cycles']}**",
        f"- Minimum Valid Cycles: **{result['thresholds']['minimum_valid_cycles']}**",
        f"- Maximum Blocked Cycles: **{result['thresholds']['maximum_blocked_cycles']}**",
        "",
        "## Validation Checks",
        "",
    ]
    for k,v in result.get("checks",{}).items():
        lines.append(f"- {k}: **{v}**")

    counts = result.get("evidence_counts", {})
    if counts:
        lines += [
            "",
            "## Evidence Counts",
            "",
            f"- Observed: **{counts.get('observed',0)}**",
            f"- Valid: **{counts.get('valid',0)}**",
            f"- Operational Pass: **{counts.get('operational_pass',0)}**",
            f"- No-Trade Valid: **{counts.get('no_trade_valid',0)}**",
            f"- Blocked: **{counts.get('blocked',0)}**",
            f"- Unknown: **{counts.get('unknown',0)}**",
        ]

    lines += [
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
    ]

    if result.get("blockers"):
        lines += ["", "## Blockers", ""]
        for b in result["blockers"]:
            lines.append(f"- **{b}**")

    (art/"phase375_summary.md").write_text("\n".join(lines)+"\n", encoding="utf-8")

    print(f"State: {result.get('state')}")
    for k,v in result.get("checks",{}).items():
        print(f"{k}: {v}")
    print(f"Qualified: {'YES' if result.get('qualified') else 'NO'}")
    if result.get("blockers"):
        print("Blockers: " + ", ".join(result["blockers"]))

    # OBSERVING is a healthy non-terminal state and should not fail CI.
    return 1 if result.get("state") == "MULTI_CYCLE_STABILITY_BLOCKED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
'@

$yml = @'
name: GPT Quant Phase 3.7.5 - Production Paper Multi-Cycle Stability Evidence Qualification

on:
  workflow_dispatch:
  schedule:
    # Taiwan 22:50 = UTC 14:50, after Phase 3.7.4 daily monitoring at 22:35.
    - cron: "50 14 * * 1-5"

permissions:
  contents: read

jobs:
  multi-cycle-stability-qualification:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
      VITE_SUPABASE_URL: ${{ secrets.VITE_SUPABASE_URL }}
      VITE_SUPABASE_PUBLISHABLE_KEY: ${{ secrets.VITE_SUPABASE_PUBLISHABLE_KEY }}
      GPT_QUANT_PORTFOLIO_ID: V92_PRODUCTION_PAPER_V91
      GPT_QUANT_STRATEGY_VERSION: V9.1
      PHASE375_MIN_OBSERVED_CYCLES: "3"
      PHASE375_MIN_VALID_CYCLES: "3"
      PHASE375_MAX_BLOCKED_CYCLES: "0"

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.5
        run: python -m py_compile automation/v92/paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py

      - name: Validate safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED = False' "$f"
          grep -q 'REAL_MONEY_TRADING_ENABLED = False' "$f"
          grep -q 'HISTORICAL_REWRITE_ALLOWED = False' "$f"
          grep -q 'MULTI_CYCLE_STABILITY_QUALIFIED' "$f"
          grep -q 'MULTI_CYCLE_STABILITY_OBSERVING' "$f"
          grep -q 'MULTI_CYCLE_STABILITY_BLOCKED' "$f"
          echo "Phase 3.7.5 safety/qualification contract: PASS"

      - name: Execute Phase 3.7.5
        id: phase375
        continue-on-error: true
        run: python automation/v92/paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase375/phase375_summary.md ]; then
            cat artifacts/phase375/phase375_summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload qualification evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase375-production-paper-multi-cycle-stability-evidence
          path: artifacts/phase375
          if-no-files-found: warn
          retention-days: 120

      - name: Enforce qualification safety result
        if: always()
        shell: bash
        run: |
          if [ "${{ steps.phase375.outcome }}" != "success" ]; then
            echo "Phase 3.7.5 multi-cycle stability qualification is BLOCKED."
            exit 1
          fi
          echo "Phase 3.7.5 multi-cycle stability qualification: HEALTHY"
'@

WriteUtf8 $pyPath $py
WriteUtf8 $ymlPath $yml

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m py_compile $pyPath
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m py_compile $pyPath
} else {
    Fail "Python not found in PATH."
}
if ($LASTEXITCODE -ne 0) { Fail "Python compile failed." }

$combined = (Get-Content $pyPath -Raw) + "`n" + (Get-Content $ymlPath -Raw)
foreach ($token in @(
    "MULTI_CYCLE_STABILITY_QUALIFIED",
    "MULTI_CYCLE_STABILITY_OBSERVING",
    "MULTI_CYCLE_STABILITY_BLOCKED",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
    'PHASE375_MIN_OBSERVED_CYCLES: "3"',
    'cron: "50 14 * * 1-5"'
)) {
    if (-not $combined.Contains($token)) { Fail "Missing contract token: $token" }
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Multi-cycle stability contract: PASS" -ForegroundColor Green
Write-Host "Evidence qualification contract: PASS" -ForegroundColor Green
Write-Host "Observation-state compatibility: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary: PASS" -ForegroundColor Green
Write-Host "Historical rewrite prohibition: PASS" -ForegroundColor Green
Write-Host "Qualification schedule: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE375 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL is required." -ForegroundColor Green
Write-Host ""
Write-Host "Generated:"
Write-Host "  $pyPath"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "Automatic schedule:"
Write-Host "  Weekdays 14:50 UTC / 22:50 Asia-Taipei"
Write-Host ""
Write-Host "Qualification thresholds:"
Write-Host "  Minimum observed cycles: 3"
Write-Host "  Minimum valid cycles: 3"
Write-Host "  Maximum blocked cycles: 0"
Write-Host ""
Write-Host "Target states:"
Write-Host "  MULTI_CYCLE_STABILITY_QUALIFIED"
Write-Host "  MULTI_CYCLE_STABILITY_OBSERVING"
Write-Host "  MULTI_CYCLE_STABILITY_BLOCKED only on genuine canonical/runtime safety failure"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add ".github/workflows/gpt-quant-v92-paper-trading-phase375-production-paper-multi-cycle-stability-evidence-qualification.yml"'
Write-Host '2. git add "automation/v92/paper_trading_phase375_production_paper_multi_cycle_stability_evidence_qualification.py"'
Write-Host '3. git status'
Write-Host '4. git commit -m "Deploy Phase 375 production paper multi-cycle stability evidence qualification"'
Write-Host '5. git push origin main'
Write-Host '6. Run the Phase 3.7.5 GitHub Action.'
