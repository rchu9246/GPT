$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.2.1"
Write-Host " Market State Persistence Fix"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase3421_market_state_persistence_fix.py"
$ymlPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase3421-market-state-persistence-fix.yml"

$python = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.2.1
Market State Persistence Fix

Purpose:
- Persist fresh market-state evidence from current Supabase canonical tables.
- Repair N/A propagation seen in Phase 3.4.2 daily operations.
- Never changes release/broker/live-money state.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase3421_output"
OUT.mkdir(exist_ok=True)

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE3421_REQUIRED_PASS_DAYS", "5"))

SNAPSHOT_TABLE = os.getenv("PHASE3421_SNAPSHOT_TABLE", "gptq_paper_daily_snapshots")
MARKET_TABLE = os.getenv("PHASE3421_MARKET_TABLE", "gpt_quant_v9_market_data")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get(table: str, params: dict):
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase GET {table}: HTTP {exc.code}: {body}") from exc

def first_dict(rows):
    if isinstance(rows, dict):
        return rows
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                return row
    return None

def parse_date(s):
    if not s:
        return None
    return date.fromisoformat(str(s)[:10])

def latest_market_date():
    # Prefer current V9 market table if available.
    candidates = [
        (MARKET_TABLE, {"select": "trade_date", "order": "trade_date.desc", "limit": "1"}),
        ("gptq_market_prices", {"select": "trade_date", "order": "trade_date.desc", "limit": "1"}),
        ("market_prices", {"select": "trade_date", "order": "trade_date.desc", "limit": "1"}),
    ]
    errors = []
    for table, params in candidates:
        try:
            row = first_dict(get(table, params))
            if row and row.get("trade_date"):
                return str(row["trade_date"])[:10], table, errors
        except Exception as exc:
            errors.append(f"{table}:{exc}")
    return None, None, errors

def snapshot_rows():
    params = {
        "select": "run_date,status,latest_market_date,market_stale_days,strategy_version,mode",
        "strategy_version": f"eq.{STRATEGY}",
        "order": "run_date.desc",
        "limit": "30",
    }
    rows = get(SNAPSHOT_TABLE, params)
    return rows if isinstance(rows, list) else []

def consecutive_pass_days(rows):
    # distinct run_date only, newest first
    seen = set()
    ordered = []
    for row in rows:
        rd = str(row.get("run_date") or "")[:10]
        if not rd or rd in seen:
            continue
        seen.add(rd)
        ordered.append(row)

    streak = 0
    streak_dates = []
    for row in ordered:
        if str(row.get("status", "")).upper() != "PASS":
            break
        streak += 1
        streak_dates.append(str(row.get("run_date"))[:10])
    return streak, streak_dates

def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    market_date, market_source, market_errors = latest_market_date()
    rows = snapshot_rows()
    pass_days, streak_dates = consecutive_pass_days(rows)

    if not market_date:
        raise RuntimeError("Unable to resolve latest_market_date from canonical market tables")

    md = parse_date(market_date)
    stale_days = (date.today() - md).days if md else None

    if stale_days is None:
        raise RuntimeError("Unable to calculate market stale days")

    result = {
        "version": "3.4.2.1",
        "checked_at": now_iso(),
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "pass_day_source": "distinct_run_date_snapshot_status",
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "remaining_pass_days": max(REQUIRED_PASS_DAYS - pass_days, 0),
        "streak_dates": streak_dates,
        "latest_market_date": market_date,
        "market_stale_days": stale_days,
        "market_source_table": market_source,
        "market_source_errors": market_errors,
        "human_approval_required": True,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "release_state": "LOCKED",
        "fail_closed": True,
    }

    (OUT / "market_state.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.2.1",
        "",
        "## Market State Persistence Fix",
        "",
        f"- Status: **{result['status']}**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- PASS-day Source: `{result['pass_day_source']}`",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Remaining PASS days: **{result['remaining_pass_days']}**",
        f"- Latest market date: `{market_date}`",
        f"- Market stale days: `{stale_days}`",
        f"- Market source table: `{market_source}`",
        "",
        "### Safety Locks",
        "",
        "- Human approval required: **YES**",
        "- Automatic approval: **DISABLED**",
        "- Release State: **LOCKED**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Missing market state => **BLOCKED / FAIL-CLOSED**",
    ]

    (OUT / "market_state.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    # Compatibility exports for downstream phases.
    compat342 = ROOT / "phase342_output"
    compat342.mkdir(exist_ok=True)
    (compat342 / "phase342_market_state.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
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
name: GPT Quant Phase 3.4.2.1 - Market State Persistence Fix

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
  schedule:
    # 09:17 UTC = 17:17 Taiwan time, weekdays.
    # Runs after Phase 3.4.2 Daily Operations.
    - cron: "17 9 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase3421-market-state-persistence
  cancel-in-progress: false

jobs:
  market-state-persistence:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PHASE3421_REQUIRED_PASS_DAYS: "5"
      PHASE3421_SNAPSHOT_TABLE: gptq_paper_daily_snapshots

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Validate environment
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q SHADOW_ONLY_NO_BROKER automation/v92/paper_trading_phase3421_market_state_persistence_fix.py

      - name: Run Phase 3.4.2.1 Market State Persistence Fix
        run: python automation/v92/paper_trading_phase3421_market_state_persistence_fix.py

      - name: Upload market-state evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3421-market-state-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/phase342_market_state.json
          if-no-files-found: warn
          retention-days: 30
'@

[System.IO.File]::WriteAllText($pyPath, $python, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($ymlPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.2.1 READY"
Write-Host "============================================================"
Write-Host "Created automation/v92/paper_trading_phase3421_market_state_persistence_fix.py"
Write-Host "Created .github/workflows/gpt-quant-v92-paper-trading-phase3421-market-state-persistence-fix.yml"
Write-Host ""
Write-Host "Purpose:"
Write-Host "  Repairs N/A latest_market_date / market_stale_days propagation"
Write-Host "  Recomputes distinct PASS-day streak from canonical snapshots"
Write-Host "  Persists compatibility state into phase342_output"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Release LOCKED"
Write-Host "  Human approval REQUIRED"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
Write-Host ""
Write-Host "Next:"
Write-Host "  GitHub Desktop -> Commit -> Push origin"
Write-Host "  GitHub Actions -> Phase 3.4.2.1 -> Run workflow"
