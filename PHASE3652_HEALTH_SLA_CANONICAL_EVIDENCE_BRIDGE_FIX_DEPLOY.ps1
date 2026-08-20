#requires -Version 5.1
<#
PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.6.5.2 — Health + SLA Canonical Evidence Bridge Fix

Root cause addressed
--------------------
Phase 3.6.5 / 3.6.5.1 was reading non-canonical table names:
  paper_health_monitoring_v92
  paper_observability_sla_v92

But the actual upstream canonical persistence created by:
  Phase 3.6.2 -> paper_system_health_v92
  Phase 3.6.3 -> paper_observability_daily_v92 / paper_sla_audit_v92

This package:
  1) patches Phase 3.6.5.1 to prefer the real canonical tables;
  2) adds safe fallback aliases for compatibility;
  3) creates compatibility views only when those aliases do not already exist;
  4) adds a dedicated Phase 3.6.5.2 diagnostic workflow;
  5) preserves fail-closed / paper-only safety.

Created/overwritten
-------------------
  supabase/PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX.sql
  automation/v92/paper_trading_phase3652_health_sla_canonical_evidence_bridge_fix.py
  .github/workflows/gpt-quant-v92-paper-trading-phase3652-health-sla-canonical-evidence-bridge-fix.yml

Patched
-------
  automation/v92/paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py
#>

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
    Write-Host "DEPLOY FAILED: $Text" -ForegroundColor Red
    exit 1
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

Section "GPT Quant V9.2 — Phase 3.6.5.2 Health + SLA Canonical Evidence Bridge Fix"

$repo = $null
try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = $null
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this package from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$phase3651 = Join-Path $repo "automation\v92\paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py"

if (-not (Test-Path $phase3651)) {
    Fail "Phase 3.6.5.1 Python file not found: $phase3651"
}

$sqlTarget = Join-Path $repo "supabase\PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX.sql"
$pyTarget = Join-Path $repo "automation\v92\paper_trading_phase3652_health_sla_canonical_evidence_bridge_fix.py"
$ymlTarget = Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase3652-health-sla-canonical-evidence-bridge-fix.yml"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase3652-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

Copy-Item $phase3651 (Join-Path $backupRoot "paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py") -Force

foreach ($target in @($sqlTarget, $pyTarget, $ymlTarget)) {
    if (Test-Path $target) {
        Copy-Item $target (Join-Path $backupRoot ([IO.Path]::GetFileName($target))) -Force
    }
}

Section "Patching Phase 3.6.5.1 canonical source table names"

$src = Get-Content -LiteralPath $phase3651 -Raw

$replacements = @{
    '"paper_health_monitoring_v92"' = '"paper_system_health_v92"'
    '"paper_observability_sla_v92"' = '"paper_observability_daily_v92"'
}

$changed = $false
foreach ($old in $replacements.Keys) {
    if ($src.Contains($old)) {
        $src = $src.Replace($old, $replacements[$old])
        $changed = $true
        Write-Host "Patched: $old -> $($replacements[$old])" -ForegroundColor Green
    }
}

if (-not $changed) {
    Write-Host "Primary wrong-table literals were not found; continuing with bridge compatibility layer." -ForegroundColor Yellow
}

Write-Utf8NoBom $phase3651 $src

Section "Writing Supabase compatibility bridge"

$sql = @'
begin;

-- Canonical source created by Phase 3.6.2:
--   public.paper_system_health_v92
--
-- Compatibility alias expected by older qualification readers:
--   public.paper_health_monitoring_v92

do $$
begin
    if to_regclass('public.paper_health_monitoring_v92') is null then
        execute $v$
            create view public.paper_health_monitoring_v92 as
            select
                health_id,
                portfolio_id,
                strategy_version,
                health_date,
                health_status,
                health_score,
                incident_required,
                autonomous_operation_status,
                recovery_state,
                master_final_state,
                market_data_status,
                latest_market_date,
                eligible_signals,
                sized_candidates,
                order_intents_created,
                simulated_fills_created,
                fills_settled,
                cash,
                market_value,
                nav,
                realized_pnl,
                unrealized_pnl,
                open_positions,
                checks_passed,
                checks_failed,
                check_details,
                synthetic_market_data,
                synthetic_signals,
                fake_prices_allowed,
                broker_api_used,
                broker_credentials_used,
                broker_order_submission_enabled,
                real_money_trading_enabled,
                live_money_release_authorized,
                fail_closed_policy,
                evidence_sha256,
                created_at,
                updated_at
            from public.paper_system_health_v92
        $v$;
    end if;
end
$$;

-- Canonical source created by Phase 3.6.3:
--   public.paper_observability_daily_v92
--
-- Compatibility alias expected by older qualification readers:
--   public.paper_observability_sla_v92

do $$
begin
    if to_regclass('public.paper_observability_sla_v92') is null then
        execute $v$
            create view public.paper_observability_sla_v92 as
            select
                observability_id,
                portfolio_id,
                strategy_version,
                observation_date as sla_date,
                observation_date,
                health_status,
                autonomous_operation_status,
                recovery_state,
                master_final_state,
                end_to_end_duration_seconds,
                stage_duration_seconds,
                success_rate_7d,
                recovery_rate_7d,
                incident_count_7d,
                successful_streak_days,
                sla_status,
                sla_score,
                sla_details,
                cash,
                market_value,
                nav,
                open_positions,
                synthetic_market_data,
                synthetic_signals,
                fake_prices_allowed,
                broker_api_used,
                broker_credentials_used,
                broker_order_submission_enabled,
                real_money_trading_enabled,
                live_money_release_authorized,
                fail_closed_policy,
                evidence_sha256,
                created_at,
                updated_at
            from public.paper_observability_daily_v92
        $v$;
    end if;
end
$$;

comment on view public.paper_health_monitoring_v92 is
'Phase 3.6.5.2 compatibility bridge to canonical public.paper_system_health_v92.';

comment on view public.paper_observability_sla_v92 is
'Phase 3.6.5.2 compatibility bridge to canonical public.paper_observability_daily_v92.';

commit;
'@

Write-Utf8NoBom $sqlTarget $sql
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.6.5.2 bridge diagnostic"

$py = @'
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"

def env_first(*names: str) -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return ""

class SB:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def get(self, table: str, query: str) -> List[Dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/{table}?{query}"
        req = urllib.request.Request(
            endpoint,
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8")
                data = json.loads(body) if body.strip() else []
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc

def latest(sb: SB, table: str, portfolio_id: str, order_col: str) -> Optional[Dict[str, Any]]:
    q = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_col}.desc&limit=1"
    )
    rows = sb.get(table, q)
    return rows[0] if rows else None

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    args = ap.parse_args()

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = SB(url, key)

    health = latest(sb, "paper_system_health_v92", args.portfolio_id, "health_date")
    sla = latest(sb, "paper_observability_daily_v92", args.portfolio_id, "observation_date")

    health_alias = latest(sb, "paper_health_monitoring_v92", args.portfolio_id, "health_date")
    sla_alias = latest(sb, "paper_observability_sla_v92", args.portfolio_id, "sla_date")

    result = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "canonical_health_found": health is not None,
        "canonical_health_state": (health or {}).get("health_status"),
        "canonical_health_score": (health or {}).get("health_score"),
        "compat_health_found": health_alias is not None,
        "canonical_sla_found": sla is not None,
        "canonical_sla_state": (sla or {}).get("sla_status"),
        "canonical_sla_score": (sla or {}).get("sla_score"),
        "compat_sla_found": sla_alias is not None,
        "bridge_status": "PASS",
        "paper_only": True,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
    }

    if health is None or sla is None:
        result["bridge_status"] = "FAIL_CLOSED"

    if health_alias is None or sla_alias is None:
        result["bridge_status"] = "FAIL_CLOSED"

    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.5.2")
    print()
    print("## Health + SLA Canonical Evidence Bridge Fix")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Canonical Health Found: **{'YES' if result['canonical_health_found'] else 'NO'}**")
    print(f"- Canonical Health: `{result['canonical_health_state']}` / `{result['canonical_health_score']}`")
    print(f"- Compatibility Health Bridge: **{'PASS' if result['compat_health_found'] else 'MISSING'}**")
    print(f"- Canonical SLA Found: **{'YES' if result['canonical_sla_found'] else 'NO'}**")
    print(f"- Canonical SLA: `{result['canonical_sla_state']}` / `{result['canonical_sla_score']}`")
    print(f"- Compatibility SLA Bridge: **{'PASS' if result['compat_sla_found'] else 'MISSING'}**")
    print(f"- Bridge Status: **{result['bridge_status']}**")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3652")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "bridge_evidence.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return 0 if result["bridge_status"] == "PASS" else 1

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3652_FATAL: {exc}", file=sys.stderr)
        raise
'@

Write-Utf8NoBom $pyTarget $py
Write-Host "Wrote: $pyTarget" -ForegroundColor Green

Section "Writing Phase 3.6.5.2 GitHub Actions workflow"

$yml = @'
name: GPT Quant Phase 3.6.5.2 - Health SLA Canonical Evidence Bridge Fix

on:
  workflow_dispatch:
    inputs:
      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

permissions:
  contents: read

jobs:
  health-sla-canonical-evidence-bridge:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Compile Phase 3.6.5.1 and 3.6.5.2
        shell: bash
        run: |
          python -m py_compile automation/v92/paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py
          python -m py_compile automation/v92/paper_trading_phase3652_health_sla_canonical_evidence_bridge_fix.py

      - name: Validate patched canonical source names
        shell: bash
        run: |
          set -euo pipefail

          grep -q 'paper_system_health_v92' \
            automation/v92/paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py

          grep -q 'paper_observability_daily_v92' \
            automation/v92/paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py

          echo "Canonical source-name alignment: PASS"

      - name: Run Phase 3.6.5.2 bridge diagnostic
        shell: bash
        run: |
          mkdir -p artifacts/phase3652

          python automation/v92/paper_trading_phase3652_health_sla_canonical_evidence_bridge_fix.py \
            --portfolio-id "$PORTFOLIO_ID" \
            | tee artifacts/phase3652/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase3652/summary.md ]; then
            cat artifacts/phase3652/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3652-health-sla-canonical-bridge
          path: artifacts/phase3652/
          if-no-files-found: warn
          retention-days: 30
'@

Write-Utf8NoBom $ymlTarget $yml
Write-Host "Wrote: $ymlTarget" -ForegroundColor Green

Section "Static validation"

$pythonExe = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} else {
    Fail "Python not found in PATH."
}

if ($pythonExe -eq "py") {
    & py -3 -m py_compile $phase3651
    if ($LASTEXITCODE -ne 0) { Fail "Phase 3.6.5.1 compile failed after patch." }

    & py -3 -m py_compile $pyTarget
    if ($LASTEXITCODE -ne 0) { Fail "Phase 3.6.5.2 compile failed." }
} else {
    & python -m py_compile $phase3651
    if ($LASTEXITCODE -ne 0) { Fail "Phase 3.6.5.1 compile failed after patch." }

    & python -m py_compile $pyTarget
    if ($LASTEXITCODE -ne 0) { Fail "Phase 3.6.5.2 compile failed." }
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$phase3651Now = Get-Content -LiteralPath $phase3651 -Raw

if (-not $phase3651Now.Contains("paper_system_health_v92")) {
    Fail "Patched Phase 3.6.5.1 does not reference canonical Health table."
}

if (-not $phase3651Now.Contains("paper_observability_daily_v92")) {
    Fail "Patched Phase 3.6.5.1 does not reference canonical SLA/Observability table."
}

$combined = (Get-Content -LiteralPath $pyTarget -Raw) + "`n" + (Get-Content -LiteralPath $ymlTarget -Raw)

foreach ($token in @(
    "PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX",
    "paper_system_health_v92",
    "paper_observability_daily_v92",
    "paper_health_monitoring_v92",
    "paper_observability_sla_v92",
    "FAIL_CLOSED"
)) {
    if (-not $combined.Contains($token)) {
        Fail "Phase 3.6.5.2 contract token missing: $token"
    }
}

foreach ($forbidden in @(
    "broker_order_submission_enabled = True",
    "real_money_trading_enabled = True",
    "live_money_release_authorized = True"
)) {
    if ($combined.Contains($forbidden)) {
        Fail "Forbidden safety capability detected: $forbidden"
    }
}

Write-Host "Canonical Health source alignment: PASS" -ForegroundColor Green
Write-Host "Canonical SLA source alignment: PASS" -ForegroundColor Green
Write-Host "Safety boundary scan: PASS" -ForegroundColor Green

Section "DEPLOY COMPLETE"

Write-Host "Generated/updated:" -ForegroundColor Green
Write-Host "  automation/v92/paper_trading_phase3651_continuous_qualification_canonical_input_alignment_fix.py"
Write-Host "  automation/v92/paper_trading_phase3652_health_sla_canonical_evidence_bridge_fix.py"
Write-Host "  supabase/PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX.sql"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3652-health-sla-canonical-evidence-bridge-fix.yml"
Write-Host ""
Write-Host "Canonical source mapping:" -ForegroundColor Cyan
Write-Host "  Health: paper_system_health_v92"
Write-Host "  SLA:    paper_observability_daily_v92"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX.sql once in Supabase."
Write-Host "  2) Commit and Push generated changes."
Write-Host "  3) Run Phase 3.6.5.2 GitHub Action."
Write-Host "  4) Confirm Canonical Health Found=YES, Canonical SLA Found=YES, Bridge Status=PASS."
Write-Host "  5) Then rerun Phase 3.6.5.1."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
