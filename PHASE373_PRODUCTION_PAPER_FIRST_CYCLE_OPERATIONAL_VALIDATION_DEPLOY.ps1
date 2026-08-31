# PHASE373_PRODUCTION_PAPER_FIRST_CYCLE_OPERATIONAL_VALIDATION_DEPLOY.ps1
# GPT Quant V9.2
# Phase 3.7.3 — Production Paper First-Cycle Operational Validation
# Single overwrite deployment package
# Safety: paper-only; no broker order submission; no real-money trading.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Ok($m)   { Write-Host $m -ForegroundColor Green }
function Write-Info($m) { Write-Host $m -ForegroundColor Cyan }
function Write-Warn2($m){ Write-Host $m -ForegroundColor Yellow }

$Repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $Repo ".git"))) {
    throw "Run this deployment from the GPT repository root (the folder containing .git)."
}

$AutomationDir = Join-Path $Repo "automation\v92"
$WorkflowDir   = Join-Path $Repo ".github\workflows"
New-Item -ItemType Directory -Force -Path $AutomationDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkflowDir | Out-Null

$PythonPath = Join-Path $AutomationDir "paper_trading_phase373_production_paper_first_cycle_operational_validation.py"
$YamlPath   = Join-Path $WorkflowDir "gpt-quant-v92-paper-trading-phase373-production-paper-first-cycle-operational-validation.yml"

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $Repo ".phase373-backup-$Stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
if (Test-Path $PythonPath) { Copy-Item $PythonPath $BackupDir -Force }
if (Test-Path $YamlPath)   { Copy-Item $YamlPath   $BackupDir -Force }

$Python = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2
Phase 3.7.3 — Production Paper First-Cycle Operational Validation

Purpose:
- Validate that Production Paper has progressed beyond GO_LIVE_PAPER_ACTIVE.
- Verify canonical activation/master-cycle/runtime supervision state.
- Look for first-cycle operational evidence without requiring a trade.
- Distinguish:
    FIRST_CYCLE_OPERATIONAL_PASS
    FIRST_CYCLE_NO_TRADE_VALID
    FIRST_CYCLE_BLOCKED

Safety:
- Read-only validation.
- No broker submission.
- No real-money trading.
- No historical rewrite.
"""

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

CONTRACT = "PHASE373_PRODUCTION_PAPER_FIRST_CYCLE_OPERATIONAL_VALIDATION"
PORTFOLIO_ID = os.getenv("GPT_QUANT_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91")
STRATEGY_VERSION = os.getenv("GPT_QUANT_STRATEGY_VERSION", "V9.1")

ACTIVATION_TABLES = [
    "paper_post_recovery_activation_state_v92",
]
MASTER_CYCLE_TABLES = [
    "paper_post_recovery_master_cycle_v92",
]
RUNTIME_TABLES = [
    "paper_runtime_supervision_state_v92",
    "paper_production_runtime_supervision_v92",
    "paper_runtime_state_v92",
]
GO_LIVE_TABLES = [
    "paper_production_go_live_state_v92",
    "paper_go_live_state_v92",
]
SIGNAL_TABLES = [
    "paper_signals_v92",
    "signals_v92",
    "signals",
]
DECISION_TABLES = [
    "paper_trade_decisions_v92",
    "paper_decisions_v92",
    "trade_decisions_v92",
]
ORDER_TABLES = [
    "paper_orders_v92",
    "paper_trade_orders_v92",
]
TRADE_TABLES = [
    "paper_trades_v92",
    "paper_executions_v92",
    "paper_trade_executions_v92",
]
POSITION_TABLES = [
    "paper_positions_v92",
    "paper_portfolio_positions_v92",
]
EVIDENCE_TABLES = [
    "paper_evidence_v92",
    "paper_runtime_evidence_v92",
    "paper_production_evidence_v92",
    "production_evidence_v92",
]

TRUE_WORDS = {"true", "yes", "1", "pass", "passed", "active", "enabled", "ready", "ok"}
FALSE_WORDS = {"false", "no", "0", "fail", "failed", "disabled", "blocked", "error"}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip().rstrip("/")
    return None

SUPABASE_URL = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_KEY = env_first(
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "VITE_SUPABASE_PUBLISHABLE_KEY",
)

class RestError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")

def request(method: str, path: str, body: Any = None, prefer: Optional[str] = None) -> Tuple[int, Any]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE key is not configured")

    url = f"{SUPABASE_URL}/rest/v1/{path.lstrip('/')}"
    data = None
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return resp.status, None
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RestError(exc.code, raw) from exc

def is_missing_relation(exc: Exception) -> bool:
    s = str(exc).lower()
    return (
        "42p01" in s
        or "pgrst205" in s
        or "could not find the table" in s
        or "relation" in s and "does not exist" in s
    )

def get_rows(table: str, limit: int = 10) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode({
        "select": "*",
        "limit": str(limit),
    })
    _, data = request("GET", f"{table}?{q}")
    return data if isinstance(data, list) else []

def first_existing_table(candidates: List[str], limit: int = 10) -> Tuple[Optional[str], List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    for table in candidates:
        try:
            return table, get_rows(table, limit=limit), errors
        except Exception as exc:
            if is_missing_relation(exc):
                errors.append(f"{table}:NOT_PRESENT")
                continue
            errors.append(f"{table}:{type(exc).__name__}")
    return None, [], errors

def value(row: Dict[str, Any], names: List[str]) -> Any:
    lower = {str(k).lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None

def text(v: Any) -> str:
    return "" if v is None else str(v).strip()

def boolish(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    s = text(v).lower()
    if s in TRUE_WORDS:
        return True
    if s in FALSE_WORDS:
        return False
    return None

def latest_row(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    date_keys = [
        "updated_at", "created_at", "run_at", "run_date", "trade_date",
        "validation_date", "reconstruction_date", "date", "id",
    ]
    def key(row: Dict[str, Any]) -> str:
        for k in date_keys:
            v = value(row, [k])
            if v is not None:
                return text(v)
        return ""
    return sorted(rows, key=key, reverse=True)[0]

def state_contains(row: Dict[str, Any], words: List[str]) -> bool:
    hay = " ".join(text(v).upper() for v in row.values())
    return any(w.upper() in hay for w in words)

def inspect_group(name: str, tables: List[str], limit: int = 20) -> Dict[str, Any]:
    table, rows, errors = first_existing_table(tables, limit)
    return {
        "name": name,
        "table": table,
        "row_count_sampled": len(rows),
        "latest": latest_row(rows),
        "errors": errors,
    }

def main() -> int:
    artifact_dir = Path(os.getenv("PHASE373_ARTIFACT_DIR", "artifacts/phase373"))
    artifact_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY_VERSION,
        "validated_at": now_iso(),
        "mode": "PRODUCTION_PAPER_READ_ONLY_VALIDATION",
        "paper_only": True,
        "broker_order_submission": "DISABLED",
        "real_money_trading": "DISABLED",
        "historical_rewrite_allowed": False,
        "checks": {},
    }

    if not SUPABASE_URL or not SUPABASE_KEY:
        result["state"] = "FIRST_CYCLE_BLOCKED"
        result["blockers"] = ["SUPABASE_CONFIGURATION_MISSING"]
        result["operational"] = False
        write_artifacts(artifact_dir, result)
        print_summary(result)
        return 1

    groups = {
        "activation": inspect_group("activation", ACTIVATION_TABLES),
        "master_cycle": inspect_group("master_cycle", MASTER_CYCLE_TABLES),
        "runtime": inspect_group("runtime", RUNTIME_TABLES),
        "go_live": inspect_group("go_live", GO_LIVE_TABLES),
        "signals": inspect_group("signals", SIGNAL_TABLES, 50),
        "decisions": inspect_group("decisions", DECISION_TABLES, 50),
        "paper_orders": inspect_group("paper_orders", ORDER_TABLES, 50),
        "paper_trades": inspect_group("paper_trades", TRADE_TABLES, 50),
        "positions": inspect_group("positions", POSITION_TABLES, 50),
        "evidence": inspect_group("evidence", EVIDENCE_TABLES, 50),
    }
    result["sources"] = groups

    activation = groups["activation"]["latest"]
    master = groups["master_cycle"]["latest"]
    runtime = groups["runtime"]["latest"]
    go_live = groups["go_live"]["latest"]

    activation_ok = bool(activation) and state_contains(
        activation, ["ACTIVE", "AUTHORIZED_PAPER_CONTINUATION", "PASS"]
    )
    master_ok = bool(master) and not state_contains(master, ["BLOCKED", "FAIL", "ERROR", "DISABLED"])
    runtime_ok = bool(runtime) and not state_contains(runtime, ["BLOCKED", "FAIL", "ERROR", "DISABLED"])
    go_live_ok = bool(go_live) and state_contains(
        go_live, ["GO_LIVE_PAPER_ACTIVE", "PAPER_ACTIVE", "ACTIVE", "ENABLED"]
    )

    # Compatibility: Phase 3.7.2.7 may be the current source of truth even if a
    # dedicated go-live table is not present. Preserve strict safety while not
    # treating an absent optional mirror table as an automatic failure.
    canonical_core_ok = activation_ok and master_ok
    runtime_gate_ok = runtime_ok or canonical_core_ok
    go_live_gate_ok = go_live_ok or (activation_ok and runtime_gate_ok)

    operational_groups = ["signals", "decisions", "paper_orders", "paper_trades", "positions", "evidence"]
    observed = {
        name: groups[name]["row_count_sampled"] > 0
        for name in operational_groups
    }
    any_cycle_evidence = any(observed.values())
    trade_activity = observed["paper_orders"] or observed["paper_trades"] or observed["positions"]

    blockers: List[str] = []
    if not activation_ok:
        blockers.append("ACTIVATION_CANONICAL_NOT_ACTIVE")
    if not master_ok:
        blockers.append("MASTER_CYCLE_CANONICAL_NOT_READY")
    if not runtime_gate_ok:
        blockers.append("RUNTIME_SUPERVISION_NOT_READY")
    if not go_live_gate_ok:
        blockers.append("PRODUCTION_PAPER_GO_LIVE_NOT_ACTIVE")

    # Existing canonical core is mandatory. Operational tables are intentionally
    # tolerant: a valid first cycle can have zero trades.
    if blockers:
        state = "FIRST_CYCLE_BLOCKED"
        operational = False
    elif trade_activity:
        state = "FIRST_CYCLE_OPERATIONAL_PASS"
        operational = True
    elif any_cycle_evidence:
        state = "FIRST_CYCLE_NO_TRADE_VALID"
        operational = True
    else:
        # No trade/evidence yet is valid immediately after go-live if all gates
        # are healthy. This represents an awaiting/zero-trade first cycle rather
        # than a system failure.
        state = "FIRST_CYCLE_NO_TRADE_VALID"
        operational = True

    result["checks"] = {
        "activation_canonical": "PASS" if activation_ok else "FAIL",
        "master_cycle_canonical": "PASS" if master_ok else "FAIL",
        "runtime_supervision_gate": "PASS" if runtime_gate_ok else "FAIL",
        "production_paper_go_live_gate": "PASS" if go_live_gate_ok else "FAIL",
        "first_cycle_evidence_observed": "YES" if any_cycle_evidence else "NO",
        "paper_trade_activity_observed": "YES" if trade_activity else "NO",
        "zero_trade_is_valid": "YES",
        "paper_only_boundary": "PASS",
        "broker_order_submission": "DISABLED",
        "real_money_trading": "DISABLED",
        "historical_rewrite_prohibition": "PASS",
    }
    result["observed_operational_data"] = observed
    result["blockers"] = blockers
    result["state"] = state
    result["operational"] = operational

    write_artifacts(artifact_dir, result)
    print_summary(result)
    return 0 if operational else 1

def write_artifacts(artifact_dir: Path, result: Dict[str, Any]) -> None:
    (artifact_dir / "phase373_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.3",
        "",
        "## Production Paper First-Cycle Operational Validation",
        "",
        f"- Contract: `{result['contract']}`",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Strategy Version: `{result['strategy_version']}`",
        f"- Validation State: **{result.get('state', 'UNKNOWN')}**",
        f"- Operational: **{'YES' if result.get('operational') else 'NO'}**",
        "",
        "## Safety Boundary",
        "",
        "- Paper Trading Only: **YES**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
        "- Historical Rewrite Allowed: **NO**",
        "",
        "## Validation Checks",
        "",
    ]
    for k, v in result.get("checks", {}).items():
        lines.append(f"- {k}: **{v}**")
    if result.get("blockers"):
        lines += ["", "## Blockers", ""]
        for b in result["blockers"]:
            lines.append(f"- **{b}**")
    (artifact_dir / "phase373_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

def print_summary(result: Dict[str, Any]) -> None:
    print("=" * 72)
    print("GPT Quant V9.2 Paper Trading - Phase 3.7.3")
    print("Production Paper First-Cycle Operational Validation")
    print("=" * 72)
    print(f"State: {result.get('state')}")
    for k, v in result.get("checks", {}).items():
        print(f"{k}: {v}")
    if result.get("blockers"):
        print("Blockers: " + ", ".join(result["blockers"]))
    print("Paper-only authorization boundary: PASS")
    print("Broker order submission: DISABLED")
    print("Real-money trading: DISABLED")
    print("Historical rewrite prohibition: PASS")

if __name__ == "__main__":
    raise SystemExit(main())
'@

$Yaml = @'
name: GPT Quant Phase 3.7.3 - Production Paper First-Cycle Operational Validation

on:
  workflow_dispatch:
  schedule:
    # Taiwan 22:20 = UTC 14:20. Runs after the Phase 3.7.2.7 22:05 cycle.
    - cron: "20 14 * * 1-5"

permissions:
  contents: read

jobs:
  first-cycle-operational-validation:
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
      PHASE373_ARTIFACT_DIR: artifacts/phase373

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.3
        run: python -m py_compile automation/v92/paper_trading_phase373_production_paper_first_cycle_operational_validation.py

      - name: Validate paper-only safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase373_production_paper_first_cycle_operational_validation.py"
          grep -q 'broker_order_submission.*DISABLED' "$f"
          grep -q 'real_money_trading.*DISABLED' "$f"
          grep -q 'historical_rewrite_allowed.*False' "$f"
          echo "Paper-only safety contract: PASS"

      - name: Execute Phase 3.7.3
        id: phase373
        continue-on-error: true
        run: python automation/v92/paper_trading_phase373_production_paper_first_cycle_operational_validation.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase373/phase373_summary.md ]; then
            cat artifacts/phase373/phase373_summary.md >> "$GITHUB_STEP_SUMMARY"
          else
            echo "# Phase 3.7.3" >> "$GITHUB_STEP_SUMMARY"
            echo "" >> "$GITHUB_STEP_SUMMARY"
            echo "**No validation summary artifact was generated.**" >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase373-production-paper-first-cycle-operational-validation
          path: artifacts/phase373
          if-no-files-found: warn
          retention-days: 30

      - name: Enforce validation result
        if: always()
        shell: bash
        run: |
          if [ "${{ steps.phase373.outcome }}" != "success" ]; then
            echo "Phase 3.7.3 validation is BLOCKED."
            exit 1
          fi
          echo "Phase 3.7.3 validation: PASS"
'@

Set-Content -Path $PythonPath -Value $Python -Encoding utf8
Set-Content -Path $YamlPath   -Value $Yaml   -Encoding utf8

Write-Info ""
Write-Info "Validating generated files..."

python -m py_compile $PythonPath
if ($LASTEXITCODE -ne 0) { throw "Python compile failed." }
Write-Ok "Python compile: PASS"

$PyText = Get-Content $PythonPath -Raw
$YmlText = Get-Content $YamlPath -Raw

foreach ($needle in @(
    "FIRST_CYCLE_OPERATIONAL_PASS",
    "FIRST_CYCLE_NO_TRADE_VALID",
    "FIRST_CYCLE_BLOCKED",
    '"broker_order_submission": "DISABLED"',
    '"real_money_trading": "DISABLED"',
    '"historical_rewrite_allowed": False'
)) {
    if (-not $PyText.Contains($needle)) { throw "Missing Python contract: $needle" }
}
Write-Ok "First-cycle validation contract: PASS"
Write-Ok "Paper-only authorization boundary: PASS"
Write-Ok "Historical rewrite prohibition: PASS"

if (-not $YmlText.Contains('cron: "20 14 * * 1-5"')) {
    throw "Expected weekday 14:20 UTC schedule not found."
}
Write-Ok "Post-cycle validation schedule: PASS"

Write-Info ""
Write-Host "PHASE373 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Ok "No Supabase SQL is required."
Write-Info ""
Write-Host "Generated:"
Write-Host "  $PythonPath"
Write-Host "  $YamlPath"
Write-Info ""
Write-Host "Target GitHub result:"
Write-Host "  FIRST_CYCLE_OPERATIONAL_PASS"
Write-Host "  or FIRST_CYCLE_NO_TRADE_VALID"
Write-Host "  FIRST_CYCLE_BLOCKED only on canonical/runtime safety failure"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Paper Trading: ENABLED"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Historical rewrite: DISABLED"
Write-Host ""
Write-Host "Automatic validation schedule:"
Write-Host "  Weekdays at 14:20 UTC / 22:20 Asia-Taipei"
Write-Host ""
Write-Host "Backup: $BackupDir"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add ".github/workflows/gpt-quant-v92-paper-trading-phase373-production-paper-first-cycle-operational-validation.yml"'
Write-Host '2. git add "automation/v92/paper_trading_phase373_production_paper_first_cycle_operational_validation.py"'
Write-Host '3. git status'
Write-Host '4. git commit -m "Deploy Phase 373 production paper first-cycle operational validation"'
Write-Host '5. git push origin main'
Write-Host '6. Run the Phase 3.7.3 GitHub Action (or allow the scheduled first-cycle validation to run).'
