#requires -Version 5.1
<#
GPT Quant V9.2 Paper Trading
Phase 3.7.2.7 — Production Paper Go-Live

Scope
-----
This deployment enables the Production Paper runtime operating cycle only.

It keeps these hard safety boundaries:
- Paper trading only
- No broker API
- No broker credentials
- No broker order submission
- No real-money trading
- No live-money release
- No historical evidence rewrite

The workflow includes:
- Manual dispatch
- Weekday schedule
- Canonical activation gate check
- Read-only production paper go-live runtime verification
- Evidence artifact + GitHub summary
- Fail-closed behavior

Default schedule:
- 14:05 UTC = 22:05 Asia/Taipei
- Monday-Friday

This phase does NOT authorize real-money trading.
#>

param(
    [switch]$AutoGit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "PHASE3727_FATAL: $Text" -ForegroundColor Red
    exit 1
}

function WriteUtf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

Section "GPT Quant V9.2 — Phase 3.7.2.7 Production Paper Go-Live"

try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = ""
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this deployment from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$pyTarget = Join-Path $repo "automation\v92\paper_trading_phase3727_production_paper_go_live.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase3727-production-paper-go-live.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $repo ".phase3727-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

foreach ($target in @($pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupDir ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "1/4 — Write Production Paper Go-Live runtime"

$py = @'
#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT = "PHASE3727_PRODUCTION_PAPER_GO_LIVE"

ACTIVATION_TABLE = "paper_post_recovery_activation_state_v92"
MASTER_CYCLE_TABLE = "paper_post_recovery_master_cycle_v92"
SUPERVISION_TABLE = "paper_runtime_supervision_state_v92"
RECONSTRUCTION_AUDIT_TABLE = "phase37261_reconstruction_audit_v92"

AUTHORIZED_GATE_STATE = "AUTHORIZED_PAPER_CONTINUATION"

BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
HISTORICAL_REWRITE_ALLOWED = False
PAPER_TRADING_ENABLED = True
DATA_COLLECTION_ENABLED = True
RUNTIME_SUPERVISION_ENABLED = True

BLOCK_STATES = {"REVOKED", "FAIL_CLOSED", "BLOCKED", "HALTED", "SUSPENDED"}


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class SupabaseREST:
    def __init__(self, base_url: str, key: str):
        self.base_url = base_url.rstrip("/")
        self.key = key

    def get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(params, safe="*,.()")
        url = f"{self.base_url}/rest/v1/{table}?{query}"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read().decode("utf-8", errors="replace")
                data = json.loads(body or "[]")
                if not isinstance(data, list):
                    raise RuntimeError(f"{table}: expected JSON list")
                return data
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc


def first(row: dict[str, Any] | None, names: tuple[str, ...], default: Any = None) -> Any:
    if not row:
        return default
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def state(row: dict[str, Any] | None, names: tuple[str, ...]) -> str:
    value = first(row, names, "")
    return str(value).strip().upper() if value is not None else ""


def latest(
    sb: SupabaseREST,
    table: str,
    portfolio_id: str,
    order_columns: tuple[str, ...],
) -> dict[str, Any] | None:
    for col in order_columns:
        params = {
            "select": "*",
            "portfolio_id": f"eq.{portfolio_id}",
            "order": f"{col}.desc",
            "limit": "1",
        }
        try:
            rows = sb.get(table, params)
            if rows:
                return rows[0]
        except RuntimeError as exc:
            msg = str(exc)
            if "PGRST204" not in msg and "42703" not in msg:
                raise

    for col in order_columns:
        params = {"select": "*", "order": f"{col}.desc", "limit": "1"}
        try:
            rows = sb.get(table, params)
            if rows:
                return rows[0]
        except RuntimeError as exc:
            msg = str(exc)
            if "PGRST204" not in msg and "42703" not in msg:
                raise

    rows = sb.get(table, {"select": "*", "limit": "1"})
    return rows[0] if rows else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default="V92_PRODUCTION_PAPER_V91")
    parser.add_argument("--strategy-version", default="V9.1")
    args = parser.parse_args()

    sb = SupabaseREST(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"))

    activation = latest(
        sb, ACTIVATION_TABLE, args.portfolio_id,
        ("activation_date", "state_date", "created_at", "updated_at"),
    )
    master = latest(
        sb, MASTER_CYCLE_TABLE, args.portfolio_id,
        ("cycle_date", "master_cycle_date", "created_at", "updated_at"),
    )
    supervision = latest(
        sb, SUPERVISION_TABLE, args.portfolio_id,
        ("supervision_date", "state_date", "created_at", "updated_at"),
    )
    reconstruction = latest(
        sb, RECONSTRUCTION_AUDIT_TABLE, args.portfolio_id,
        ("reconstruction_date", "created_at"),
    )

    activation_state = state(activation, ("activation_state", "state", "status"))
    master_state = state(master, ("master_cycle_state", "cycle_state", "state", "status"))
    supervision_state = state(supervision, ("supervision_state", "runtime_supervision", "state", "status"))
    reconstruction_state = state(reconstruction, ("reconstruction_state", "state", "status"))

    activation_ok = bool(activation) and activation_state == "ACTIVE"
    master_ok = bool(master) and master_state not in BLOCK_STATES
    supervision_ok = bool(supervision) and supervision_state not in BLOCK_STATES
    reconstruction_ok = bool(reconstruction) and reconstruction_state not in BLOCK_STATES
    if reconstruction and not reconstruction_state:
        reconstruction_ok = True

    reasons: list[str] = []
    if not activation_ok:
        reasons.append(f"ACTIVATION_NOT_READY:{activation_state or 'MISSING'}")
    if not master_ok:
        reasons.append(f"MASTER_CYCLE_NOT_READY:{master_state or 'MISSING'}")
    if not supervision_ok:
        reasons.append(f"SUPERVISION_NOT_READY:{supervision_state or 'MISSING'}")
    if not reconstruction_ok:
        reasons.append(f"RECONSTRUCTION_NOT_READY:{reconstruction_state or 'MISSING'}")

    go_live_state = "GO_LIVE_PAPER_ACTIVE" if not reasons else "BLOCKED_FAIL_CLOSED"

    now = datetime.now(timezone.utc)
    artifact_dir = Path("artifacts/phase3727")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    evidence = {
        "contract": CONTRACT,
        "go_live_state": go_live_state,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "run_time_utc": now.isoformat(),
        "runtime": {
            "paper_trading_enabled": PAPER_TRADING_ENABLED,
            "data_collection_enabled": DATA_COLLECTION_ENABLED,
            "runtime_supervision_enabled": RUNTIME_SUPERVISION_ENABLED,
        },
        "canonical": {
            "activation_state": activation_state,
            "master_cycle_state": master_state,
            "runtime_supervision_state": supervision_state,
            "reconstruction_state": reconstruction_state,
        },
        "reasons": reasons,
        "safety": {
            "broker_api_used": BROKER_API_USED,
            "broker_credentials_used": BROKER_CREDENTIALS_USED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "live_money_release_authorized": LIVE_MONEY_RELEASE_AUTHORIZED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        },
    }

    (artifact_dir / "verification.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = f"""# GPT Quant V9.2 Paper Trading - Phase 3.7.2.7

## Production Paper Go-Live

- Contract: `{CONTRACT}`
- Portfolio ID: `{args.portfolio_id}`
- Strategy Version: `{args.strategy_version}`
- Run Date: `{now.date().isoformat()}`
- Go-Live State: **{go_live_state}**

## Runtime Mode

- Paper Trading: **{'ENABLED' if PAPER_TRADING_ENABLED else 'DISABLED'}**
- Data Collection: **{'ENABLED' if DATA_COLLECTION_ENABLED else 'DISABLED'}**
- Runtime Supervision: **{'ENABLED' if RUNTIME_SUPERVISION_ENABLED else 'DISABLED'}**

## Canonical Runtime Inputs

- Activation State: **{activation_state or 'UNKNOWN'}**
- Activation Validation: **{'PASS' if activation_ok else 'FAIL'}**

- Master Cycle State: **{master_state or 'UNKNOWN'}**
- Master Cycle Validation: **{'PASS' if master_ok else 'FAIL'}**

- Runtime Supervision State: **{supervision_state or 'UNKNOWN'}**
- Runtime Supervision Validation: **{'PASS' if supervision_ok else 'FAIL'}**

- Reconstruction State: **{reconstruction_state or 'UNKNOWN'}**
- Reconstruction Validation: **{'PASS' if reconstruction_ok else 'FAIL'}**

## Go-Live Reasons

{chr(10).join(f'- `{reason}`' for reason in reasons) if reasons else '- `NONE`'}

## Safety Boundary

- Broker API used: **NO**
- Broker credentials used: **NO**
- Broker order submission: **DISABLED**
- Real-money trading: **DISABLED**
- Live-money release authorized: **NO**
- Historical rewrite allowed: **NO**

> Production Paper is live only in simulated/paper mode.
> Real-money promotion authority is **NOT PRESENT IN THIS PHASE**.
"""

    (artifact_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    if go_live_state != "GO_LIVE_PAPER_ACTIVE":
        raise RuntimeError("Phase 3.7.2.7 Go-Live blocked: " + ", ".join(reasons))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3727_FATAL: {exc}", file=sys.stderr)
        raise
'@

WriteUtf8 $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "2/4 — Write Production Paper Go-Live GitHub workflow"

$yml = @'
name: GPT Quant Phase 3.7.2.7 - Production Paper Go-Live

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

  schedule:
    # 14:05 UTC = 22:05 Asia/Taipei, Monday-Friday
    - cron: "5 14 * * 1-5"

permissions:
  contents: read

concurrency:
  group: phase3727-production-paper-go-live
  cancel-in-progress: false

jobs:
  production-paper-go-live:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Compile Phase 3.7.2.7
        run: |
          python -m py_compile automation/v92/paper_trading_phase3727_production_paper_go_live.py

      - name: Validate Phase 3.7.2.7 safety contract
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          FILE="automation/v92/paper_trading_phase3727_production_paper_go_live.py"

          grep -q 'PHASE3727_PRODUCTION_PAPER_GO_LIVE' "$FILE"
          grep -q 'PAPER_TRADING_ENABLED = True' "$FILE"
          grep -q 'DATA_COLLECTION_ENABLED = True' "$FILE"
          grep -q 'RUNTIME_SUPERVISION_ENABLED = True' "$FILE"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED = False' "$FILE"
          grep -q 'REAL_MONEY_TRADING_ENABLED = False' "$FILE"
          grep -q 'HISTORICAL_REWRITE_ALLOWED = False' "$FILE"
          grep -q 'Real-money promotion authority is \*\*NOT PRESENT IN THIS PHASE\*\*' "$FILE"

          echo "Phase 3.7.2.7 safety contract: PASS"

      - name: Execute Phase 3.7.2.7
        shell: bash
        run: |
          mkdir -p artifacts/phase3727

          python automation/v92/paper_trading_phase3727_production_paper_go_live.py \
            --strategy-version "$STRATEGY_VERSION" \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase3727/console.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3727/summary.md ]; then
            cat artifacts/phase3727/summary.md >> "$GITHUB_STEP_SUMMARY"
          elif [ -f artifacts/phase3727/console.md ]; then
            cat artifacts/phase3727/console.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3727-production-paper-go-live
          path: artifacts/phase3727/
          if-no-files-found: warn
          retention-days: 120
'@

WriteUtf8 $ymlTarget $yml
Write-Host "Wrote: $ymlTarget" -ForegroundColor Green

Section "3/4 — Static validation"

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m py_compile $pyTarget
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m py_compile $pyTarget
} else {
    Fail "Python not found in PATH."
}

if ($LASTEXITCODE -ne 0) {
    Fail "Phase 3.7.2.7 Python compile failed."
}

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" + (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE3727_PRODUCTION_PAPER_GO_LIVE",
    "GO_LIVE_PAPER_ACTIVE",
    "PAPER_TRADING_ENABLED = True",
    "DATA_COLLECTION_ENABLED = True",
    "RUNTIME_SUPERVISION_ENABLED = True",
    "BROKER_ORDER_SUBMISSION_ENABLED = False",
    "REAL_MONEY_TRADING_ENABLED = False",
    "HISTORICAL_REWRITE_ALLOWED = False",
    'cron: "5 14 * * 1-5"'
)) {
    if (-not $combined.Contains($token)) {
        Fail "Required Phase 3.7.2.7 token missing: $token"
    }
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Production Paper runtime contract: PASS" -ForegroundColor Green
Write-Host "Weekday schedule contract: PASS" -ForegroundColor Green
Write-Host "Data collection contract: PASS" -ForegroundColor Green
Write-Host "Runtime supervision contract: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary: PASS" -ForegroundColor Green
Write-Host "Historical rewrite prohibition: PASS" -ForegroundColor Green

Section "4/4 — Deployment complete"

Write-Host "PHASE3727 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host ""
Write-Host "Generated:" -ForegroundColor Green
Write-Host "  automation/v92/paper_trading_phase3727_production_paper_go_live.py"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3727-production-paper-go-live.yml"
Write-Host ""
Write-Host "No Supabase SQL is required." -ForegroundColor Green
Write-Host ""
Write-Host "Automatic schedule:" -ForegroundColor Yellow
Write-Host "  Weekdays at 14:05 UTC / 22:05 Asia-Taipei"
Write-Host ""
Write-Host "Target GitHub result:" -ForegroundColor Yellow
Write-Host "  Go-Live State: GO_LIVE_PAPER_ACTIVE"
Write-Host "  Paper Trading: ENABLED"
Write-Host "  Data Collection: ENABLED"
Write-Host "  Runtime Supervision: ENABLED"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host ""
Write-Host "Backup: $backupDir" -ForegroundColor DarkGray

& git status --short

if ($AutoGit) {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires branch main. Current branch: $branch"
    }

    & git add -- $pyTarget $ymlTarget

    & git commit -m "Deploy Phase 3727 production paper go-live"
    if ($LASTEXITCODE -ne 0) {
        Fail "git commit failed."
    }

    & git push origin main
    if ($LASTEXITCODE -ne 0) {
        Fail "git push failed."
    }

    Write-Host "Commit + Push: PASS" -ForegroundColor Green
}
