$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " GPT Quant Phase 3.4.2.1"
Write-Host " Market State Persistence Fix v5"
Write-Host " Phase 2.1 Canonical Evidence Bridge"
Write-Host "============================================================"

$root = (Get-Location).Path
$automationDir = Join-Path $root "automation\v92"
$workflowDir = Join-Path $root ".github\workflows"

New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
New-Item -ItemType Directory -Force -Path $workflowDir | Out-Null

$pyPath = Join-Path $automationDir "paper_trading_phase3421_market_state_persistence_fix.py"
$ymlPath = Join-Path $workflowDir "gpt-quant-v92-paper-trading-phase3421-market-state-persistence-fix.yml"

if (Test-Path $pyPath) {
    $backup = "$pyPath.pre_v5.bak"
    if (-not (Test-Path $backup)) { Copy-Item $pyPath $backup }
}

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase3421_output"
OUT.mkdir(exist_ok=True)

STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE3421_REQUIRED_PASS_DAYS", "5"))

PHASE21_WORKFLOW = ROOT / ".github/workflows/gpt-quant-v92-paper-trading-phase21.yml"
PHASE342_GUARD = ROOT / "automation/v92/paper_trading_phase342_qualification_state_fix.py"
PHASE342_SUMMARY = ROOT / "phase342_output/phase342_summary.json"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None

def recursive_find(obj, keys):
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj.get(key) is not None:
                return obj.get(key), key
        for value in obj.values():
            found = recursive_find(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = recursive_find(item, keys)
            if found:
                return found
    return None

def json_objects_from_text(text):
    decoder = json.JSONDecoder()
    found = []
    for i, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            value, end = decoder.raw_decode(text[i:])
            if isinstance(value, (dict, list)):
                found.append((i, end, value))
        except Exception:
            pass
    found.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in found]

def find_phase21_python_command():
    if not PHASE21_WORKFLOW.exists():
        raise RuntimeError(f"Missing Phase 2.1 workflow: {PHASE21_WORKFLOW}")

    text = PHASE21_WORKFLOW.read_text(encoding="utf-8", errors="ignore")
    candidates = []

    for line in text.splitlines():
        stripped = line.strip()
        if "python " not in stripped and "python3 " not in stripped:
            continue
        if ".py" not in stripped:
            continue

        try:
            parts = shlex.split(stripped)
        except Exception:
            continue

        py_idx = None
        for idx, part in enumerate(parts):
            if part in ("python", "python3"):
                py_idx = idx
                break

        if py_idx is None or py_idx + 1 >= len(parts):
            continue

        script = parts[py_idx + 1]
        args = parts[py_idx + 2:]

        low = script.lower()
        if "phase21" in low or "signal" in low or "market" in low:
            candidates.append((script, args))

    if not candidates:
        raise RuntimeError(
            "Could not discover Phase 2.1 Python command from "
            ".github/workflows/gpt-quant-v92-paper-trading-phase21.yml"
        )

    script, args = candidates[0]
    script_path = ROOT / script.replace("/", os.sep)

    if not script_path.exists():
        raise RuntimeError(f"Discovered Phase 2.1 script does not exist: {script_path}")

    clean_args = []
    for token in args:
        if token in ("|", "||", "&&", ">", ">>", "2>&1"):
            break
        if "${{" in token:
            continue
        clean_args.append(token)

    return script_path, clean_args

def run_phase21():
    script, args = find_phase21_python_command()

    env = os.environ.copy()
    env["STRATEGY_VERSION"] = STRATEGY
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["PAPER_TRADING_MODE"] = MODE

    cmd = [sys.executable, str(script)] + args

    p = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    raw = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    (OUT / "phase21_bridge_raw.log").write_text(raw, encoding="utf-8")

    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)

    if p.returncode != 0:
        raise RuntimeError(
            f"Authoritative Phase 2.1 execution failed with exit code {p.returncode}"
        )

    for obj in json_objects_from_text(p.stdout or ""):
        d = recursive_find(obj, ("latest_market_date", "market_date", "latest_trade_date"))
        if d and parse_date(d[0]):
            status = recursive_find(obj, ("market_data_status", "market_status"))
            return {
                "latest_market_date": str(d[0])[:10],
                "market_status": str(status[0]) if status else None,
                "market_date_key": d[1],
                "source": str(script.relative_to(ROOT)),
                "source_kind": "phase21_runtime_stdout_json",
                "command": cmd,
            }

    date_match = re.search(
        r"Latest\s+market\s+date\s*[:=]\s*`?(\d{4}-\d{2}-\d{2})",
        p.stdout or "",
        flags=re.IGNORECASE,
    )
    status_match = re.search(
        r"Market\s+data\s+status\s*[:=]\s*`?([A-Za-z_]+)",
        p.stdout or "",
        flags=re.IGNORECASE,
    )

    if date_match:
        return {
            "latest_market_date": date_match.group(1),
            "market_status": status_match.group(1) if status_match else None,
            "market_date_key": "phase21_summary_text",
            "source": str(script.relative_to(ROOT)),
            "source_kind": "phase21_runtime_stdout_summary",
            "command": cmd,
        }

    raise RuntimeError(
        "Phase 2.1 completed successfully but emitted no authoritative latest_market_date."
    )

def run_phase342_canonical_guard():
    if not PHASE342_GUARD.exists():
        raise RuntimeError(f"Missing Phase 3.4.2 guard: {PHASE342_GUARD}")

    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PAPER_TRADING_MODE"] = MODE

    p = subprocess.run(
        [sys.executable, str(PHASE342_GUARD)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    raw = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    (OUT / "phase342_guard_raw.log").write_text(raw, encoding="utf-8")

    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)

    if p.returncode != 0:
        raise RuntimeError(
            f"Phase 3.4.2 canonical guard failed with exit code {p.returncode}"
        )

    if not PHASE342_SUMMARY.exists():
        raise RuntimeError(f"Missing canonical summary: {PHASE342_SUMMARY}")

    data = json.loads(PHASE342_SUMMARY.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Phase 3.4.2 canonical summary is not a JSON object")
    return data

def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    market = run_phase21()

    market_date = market["latest_market_date"]
    market_dt = parse_date(market_date)
    if market_dt is None:
        raise RuntimeError(f"Invalid Phase 2.1 latest_market_date: {market_date}")

    stale_days = (date.today() - market_dt).days

    q = run_phase342_canonical_guard()

    source_valid = q.get("source_valid")
    if source_valid is None:
        source_valid = q.get("canonical_source_valid")

    if source_valid is False:
        raise RuntimeError("Phase 3.4.2 canonical qualification source is invalid")

    pass_days = q.get("consecutive_pass_days")
    if pass_days is None:
        raise RuntimeError("Canonical guard returned no consecutive_pass_days")

    pass_days = int(pass_days)
    pass_source = q.get("pass_day_source") or "distinct_run_date_snapshot_status"

    result = {
        "version": "3.4.2.1-v5",
        "checked_at": now_iso(),
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "market_contract": "PHASE21_RUNTIME_EVIDENCE",
        "latest_market_date": market_date,
        "market_stale_days": stale_days,
        "market_status": market.get("market_status"),
        "market_source": market.get("source"),
        "market_source_kind": market.get("source_kind"),
        "qualification_contract": "PHASE342_CANONICAL_GUARD",
        "pass_day_source": pass_source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "remaining_pass_days": max(REQUIRED_PASS_DAYS - pass_days, 0),
        "release_state": "LOCKED",
        "human_approval_required": True,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
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
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.2.1 v5",
        "",
        "## Phase 2.1 Canonical Evidence Bridge",
        "",
        "- Status: **PASS**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        "",
        "### Market Contract",
        "",
        "- Contract: **PHASE21_RUNTIME_EVIDENCE**",
        f"- Latest market date: `{market_date}`",
        f"- Market stale days: `{stale_days}`",
        f"- Market status: `{market.get('market_status')}`",
        f"- Market source: `{market.get('source')}`",
        f"- Market source kind: `{market.get('source_kind')}`",
        "",
        "### Qualification Contract",
        "",
        "- Contract: **PHASE342_CANONICAL_GUARD**",
        f"- PASS-day Source: `{pass_source}`",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Remaining PASS days: **{max(REQUIRED_PASS_DAYS - pass_days, 0)}**",
        "",
        "### Safety Locks",
        "",
        "- Release State: **LOCKED**",
        "- Human approval required: **YES**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- README/GUIDE/table-name guessing: **DISABLED**",
        "- Missing/inconsistent authoritative evidence => **BLOCKED / FAIL-CLOSED**",
    ]

    (OUT / "market_state.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
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
name: GPT Quant Phase 3.4.2.1 - Market State Persistence Fix v5

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
  group: gpt-quant-phase3421-market-state-persistence-v5
  cancel-in-progress: false

jobs:
  market-state-persistence:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PHASE3421_REQUIRED_PASS_DAYS: "5"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependency
        run: python -m pip install --upgrade pip requests

      - name: Validate v5 authoritative contracts
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f .github/workflows/gpt-quant-v92-paper-trading-phase21.yml
          test -f automation/v92/paper_trading_phase342_qualification_state_fix.py
          test -f automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q PHASE21_RUNTIME_EVIDENCE automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q PHASE342_CANONICAL_GUARD automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q SHADOW_ONLY_NO_BROKER automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q '"automatic_approval": False' automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q '"broker_trading_enabled": False' automation/v92/paper_trading_phase3421_market_state_persistence_fix.py
          grep -q '"real_money_trading_enabled": False' automation/v92/paper_trading_phase3421_market_state_persistence_fix.py

      - name: Run Phase 3.4.2.1 v5 Phase 2.1 Canonical Evidence Bridge
        run: python automation/v92/paper_trading_phase3421_market_state_persistence_fix.py

      - name: Upload v5 canonical bridge evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3421-market-state-v5-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
          if-no-files-found: warn
          retention-days: 30
'@

[System.IO.File]::WriteAllText($pyPath, $python, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($ymlPath, $workflow, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4.2.1 v5 READY"
Write-Host "============================================================"
Write-Host "Overwritten:"
Write-Host "  automation/v92/paper_trading_phase3421_market_state_persistence_fix.py"
Write-Host "  .github/workflows/gpt-quant-v92-paper-trading-phase3421-market-state-persistence-fix.yml"
Write-Host ""
Write-Host "v5 contracts:"
Write-Host "  Market state = actual Phase 2.1 runtime execution"
Write-Host "  PASS days    = existing Phase 3.4.2 canonical guard"
Write-Host "  README/GUIDE discovery = DISABLED"
Write-Host "  guessed Supabase market tables = DISABLED"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Release LOCKED"
Write-Host "  Human approval REQUIRED"
Write-Host "  Automatic approval DISABLED"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
