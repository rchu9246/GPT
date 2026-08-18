$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.2.1"
Write-Host " Market State Persistence Fix v4"
Write-Host " Runtime Evidence Only"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase3421_market_state_persistence_fix.py"
$ymlPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase3421-market-state-persistence-fix.yml"

if (Test-Path $pyPath) {
    $backup = "$pyPath.pre_v4.bak"
    if (-not (Test-Path $backup)) {
        Copy-Item $pyPath $backup
    }
}

$python = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.2.1
Market State Persistence Fix v4
Runtime Evidence Only

Fixes:
1) Documentation/README/INSTALL_GUIDE text can NEVER become canonical market source.
2) Canonical market date must come from structured runtime JSON evidence or
   a verified Supabase source.
3) PASS-day streak is schema-tolerant and recognizes common snapshot field names.
4) Release remains LOCKED; no broker/live-money activation is possible here.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
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

DATE_KEYS = (
    "latest_market_date",
    "market_date",
    "latest_trade_date",
    "trade_date",
)

STATUS_KEYS = (
    "market_data_status",
    "market_status",
    "status",
)

RUN_DATE_KEYS = (
    "run_date",
    "snapshot_date",
    "trade_date",
    "date",
)

PASS_STATUS_KEYS = (
    "status",
    "qualification_status",
    "snapshot_status",
    "result",
)

STRATEGY_KEYS = (
    "strategy_version",
    "strategy",
)

MODE_KEYS = (
    "mode",
    "trading_mode",
)

# ONLY structured runtime/evidence directories are eligible.
RUNTIME_DIRS = [
    ROOT / "phase21_output",
    ROOT / "phase342_output",
    ROOT / "phase343_output",
    ROOT / "phase343_evidence_output",
    ROOT / "market_data_output",
    ROOT / "evidence",
    ROOT / "artifacts",
]

# Explicit filename candidates produced by runtime flows.
RUNTIME_JSON_CANDIDATES = [
    ROOT / "phase21_output" / "signal_generation.json",
    ROOT / "phase21_output" / "market_state.json",
    ROOT / "phase21_output" / "summary.json",
    ROOT / "phase21_result.json",
    ROOT / "phase21_summary.json",
    ROOT / "market_data_output" / "summary.json",
    ROOT / "market_data_output" / "market_state.json",
]

# No .md/.txt scanning in v4.
ALLOWED_RUNTIME_SUFFIXES = {".json"}

# Last-resort Supabase table candidates only.
TABLE_CANDIDATES = [
    ("gptq_market_data", "trade_date"),
    ("gptq_daily_prices", "trade_date"),
    ("gptq_market_daily", "trade_date"),
    ("gptq_prices", "trade_date"),
    ("gptq_stock_prices", "trade_date"),
    ("gpt_quant_v92_market_data", "trade_date"),
    ("gpt_quant_market_prices", "trade_date"),
    ("market_data", "trade_date"),
]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def request_get(table: str, params: dict):
    q = urllib.parse.urlencode(params, doseq=True)
    url = f"{SUPABASE_URL}/rest/v1/{table}?{q}"

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
        raise RuntimeError(
            f"Supabase GET {table}: HTTP {exc.code}: {body}"
        ) from exc

def parse_date(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None

def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def recursive_find_date(obj):
    if isinstance(obj, dict):
        for key in DATE_KEYS:
            if key in obj and parse_date(obj.get(key)):
                return str(obj.get(key))[:10], key
        for value in obj.values():
            found = recursive_find_date(value)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = recursive_find_date(item)
            if found:
                return found

    return None

def recursive_find_status(obj):
    if isinstance(obj, dict):
        for key in STATUS_KEYS:
            if key in obj and obj.get(key) is not None:
                value = str(obj.get(key))
                if value.upper() in ("FRESH", "PASS", "OK", "HEALTHY"):
                    return value, key

        for value in obj.values():
            found = recursive_find_status(value)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = recursive_find_status(item)
            if found:
                return found

    return None

def valid_runtime_path(path: Path):
    # Hard-block docs/guides/readmes and source/config directories.
    name = path.name.lower()
    rel = str(path.relative_to(ROOT)).lower()

    blocked_tokens = (
        "readme",
        "guide",
        "install",
        "setup",
        "deploy",
        "docs",
        "documentation",
        ".github/",
        "automation/",
        "supabase/",
    )

    if path.suffix.lower() not in ALLOWED_RUNTIME_SUFFIXES:
        return False

    if any(token in name for token in ("readme", "guide", "install", "setup", "deploy")):
        return False

    if any(token in rel for token in blocked_tokens):
        return False

    return True

def discover_runtime_market_state():
    attempts = []

    # First: explicit runtime files.
    for path in RUNTIME_JSON_CANDIDATES:
        if not path.exists() or not valid_runtime_path(path):
            continue

        data = load_json(path)
        if data is None:
            attempts.append(f"{path}:invalid_json")
            continue

        found = recursive_find_date(data)
        if found:
            status = recursive_find_status(data)
            return {
                "latest_market_date": found[0],
                "source": str(path.relative_to(ROOT)),
                "source_kind": "runtime_json",
                "date_key": found[1],
                "status": status[0] if status else None,
                "status_key": status[1] if status else None,
                "attempts": attempts,
            }

        attempts.append(f"{path}:no_market_date")

    # Second: only JSON inside known runtime/evidence directories.
    seen = set()

    for base in RUNTIME_DIRS:
        if not base.exists():
            continue

        for path in base.rglob("*.json"):
            try:
                rel = str(path.relative_to(ROOT))
            except Exception:
                rel = str(path)

            if rel in seen:
                continue
            seen.add(rel)

            if not valid_runtime_path(path):
                continue

            data = load_json(path)
            if data is None:
                continue

            found = recursive_find_date(data)
            if found:
                status = recursive_find_status(data)
                return {
                    "latest_market_date": found[0],
                    "source": rel,
                    "source_kind": "discovered_runtime_json",
                    "date_key": found[1],
                    "status": status[0] if status else None,
                    "status_key": status[1] if status else None,
                    "attempts": attempts,
                }

    return None

def discover_supabase_market_state():
    errors = []

    for table, field in TABLE_CANDIDATES:
        try:
            rows = request_get(
                table,
                {
                    "select": field,
                    "order": f"{field}.desc",
                    "limit": "1",
                },
            )

            if isinstance(rows, list) and rows:
                row = rows[0]
                if isinstance(row, dict) and parse_date(row.get(field)):
                    return {
                        "latest_market_date": str(row[field])[:10],
                        "source": f"{table}.{field}",
                        "source_kind": "verified_supabase",
                        "date_key": field,
                        "status": None,
                        "status_key": None,
                        "attempts": errors,
                    }

        except Exception as exc:
            errors.append(f"{table}.{field}: {exc}")

    return {
        "latest_market_date": None,
        "source": None,
        "source_kind": "supabase_failed",
        "date_key": None,
        "status": None,
        "status_key": None,
        "attempts": errors,
    }

def get_value(row, keys):
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None

def load_snapshot_rows():
    # v4 tries progressively smaller selects for schema compatibility.
    select_candidates = [
        "run_date,status,strategy_version,mode",
        "run_date,status,strategy_version",
        "run_date,status",
        "*",
    ]

    last_error = None

    for select in select_candidates:
        params = {
            "select": select,
            "order": "run_date.desc",
            "limit": "60",
        }

        if select != "*":
            params["strategy_version"] = f"eq.{STRATEGY}"

        try:
            rows = request_get(SNAPSHOT_TABLE, params)
            if isinstance(rows, list):
                return rows, select
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Unable to read snapshot rows: {last_error}")

def normalize_snapshot(row):
    if not isinstance(row, dict):
        return None

    run_date = get_value(row, RUN_DATE_KEYS)
    status = get_value(row, PASS_STATUS_KEYS)
    strategy = get_value(row, STRATEGY_KEYS)
    mode = get_value(row, MODE_KEYS)

    if not run_date:
        return None

    return {
        "run_date": str(run_date)[:10],
        "status": None if status is None else str(status).upper(),
        "strategy_version": None if strategy is None else str(strategy),
        "mode": None if mode is None else str(mode),
    }

def consecutive_pass_days(rows):
    normalized = []

    for row in rows:
        n = normalize_snapshot(row)
        if n:
            normalized.append(n)

    # newest-first distinct run_date
    normalized.sort(key=lambda x: x["run_date"], reverse=True)

    seen = set()
    distinct = []

    for row in normalized:
        rd = row["run_date"]
        if rd in seen:
            continue
        seen.add(rd)
        distinct.append(row)

    streak = 0
    dates = []
    debug = []

    for row in distinct:
        debug.append(row)

        if row["strategy_version"] not in (None, STRATEGY):
            break

        if row["mode"] not in (None, MODE):
            break

        if row["status"] != "PASS":
            break

        streak += 1
        dates.append(row["run_date"])

    return streak, dates, debug

def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    # Canonical source priority: runtime structured evidence first.
    market = discover_runtime_market_state()

    if not market:
        market = discover_supabase_market_state()

    market_date = market.get("latest_market_date") if market else None

    if not market_date:
        details = market.get("attempts", []) if market else []
        raise RuntimeError(
            "Unable to resolve latest market date from runtime JSON evidence "
            "or verified Supabase source. "
            + " | ".join(details)
        )

    market_dt = parse_date(market_date)
    if market_dt is None:
        raise RuntimeError(f"Invalid latest_market_date: {market_date}")

    stale_days = (date.today() - market_dt).days

    rows, snapshot_select = load_snapshot_rows()
    pass_days, streak_dates, normalized_rows = consecutive_pass_days(rows)

    result = {
        "version": "3.4.2.1-v4",
        "checked_at": now_iso(),
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "pass_day_source": "distinct_run_date_snapshot_status",
        "snapshot_table": SNAPSHOT_TABLE,
        "snapshot_select_used": snapshot_select,
        "snapshot_rows_scanned": len(rows),
        "normalized_snapshot_rows": normalized_rows,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "remaining_pass_days": max(REQUIRED_PASS_DAYS - pass_days, 0),
        "streak_dates": streak_dates,
        "latest_market_date": market_date,
        "market_stale_days": stale_days,
        "market_source": market.get("source"),
        "market_source_kind": market.get("source_kind"),
        "market_status": market.get("status"),
        "market_discovery_attempts": market.get("attempts", []),
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

    compat = ROOT / "phase342_output"
    compat.mkdir(exist_ok=True)

    (compat / "phase342_market_state.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.2.1 v4",
        "",
        "## Runtime Evidence Only",
        "",
        f"- Status: **{result['status']}**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- PASS-day Source: `{result['pass_day_source']}`",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Remaining PASS days: **{result['remaining_pass_days']}**",
        f"- Latest market date: `{market_date}`",
        f"- Market stale days: `{stale_days}`",
        f"- Market source: `{result['market_source']}`",
        f"- Market source kind: `{result['market_source_kind']}`",
        f"- Market status: `{result['market_status']}`",
        f"- Snapshot rows scanned: **{len(rows)}**",
        f"- Snapshot select used: `{snapshot_select}`",
        "",
        "### Safety Locks",
        "",
        "- Release State: **LOCKED**",
        "- Human approval required: **YES**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Documentation/example dates are **NOT CANONICAL**",
        "- Missing/inconsistent source data => **BLOCKED / FAIL-CLOSED**",
    ]

    (OUT / "market_state.md").write_text(
        "\n".join(summary) + "\n",
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
name: GPT Quant Phase 3.4.2.1 - Market State Persistence Fix v4

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase3421-market-state-persistence-v4
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

      - name: Validate v4 safety boundary
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q SHADOW_ONLY_NO_BROKER automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q '"automatic_approval": False' automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q '"broker_trading_enabled": False' automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q '"real_money_trading_enabled": False' automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q 'Documentation/example dates are' automation/v92/paper_trading_phase3421_market_state_persistence_fix.py

      - name: Run Phase 3.4.2.1 v4 Runtime Evidence Only
        run: python automation/v92/paper_trading_phase3421_market_state_persistence_fix.py

      - name: Upload v4 market-state evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3421-market-state-v4-${{ github.run_id }}
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
Write-Host " PHASE 3.4.2.1 v4 READY"
Write-Host "============================================================"
Write-Host "Overwritten:"
Write-Host "  automation/v92/paper_trading_phase3421_market_state_persistence_fix.py"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3421-market-state-persistence-fix.yml"
Write-Host ""
Write-Host "v4 changes:"
Write-Host "  Documentation/README/GUIDE dates are BLOCKED as canonical sources"
Write-Host "  Structured runtime JSON evidence only"
Write-Host "  Supabase is fallback only"
Write-Host "  Snapshot streak reader is schema-tolerant"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Release LOCKED"
Write-Host "  Human approval REQUIRED"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
