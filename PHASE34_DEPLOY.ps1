$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host " GPT Quant V9.2 Phase 3.4 Deployment"
Write-Host " Human Approval + Production Paper Release Control"
Write-Host "============================================================"
Write-Host ""

$Root = (Get-Location).Path
$AutomationDir = Join-Path $Root "automation\v92"
$WorkflowDir = Join-Path $Root ".github\workflows"

New-Item -ItemType Directory -Force -Path $AutomationDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkflowDir | Out-Null

$PythonTarget = Join-Path $AutomationDir "paper_trading_phase34_human_approval_release.py"
$WorkflowTarget = Join-Path $WorkflowDir "gpt-quant-v92-paper-trading-phase34.yml"

$PythonContent = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4
Human Approval + Production Paper Release Control

This phase:
- independently revalidates Phase 3.3.1 qualification from daily snapshots
- requires 5 distinct PASS days
- requires explicit human approval for release
- creates a Production PAPER release manifest
- supports explicit release revocation
- NEVER enables broker or real-money trading
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = os.getenv("PAPER_TRADING_MODE", "SHADOW_ONLY_NO_BROKER")
ACTION = os.getenv("PHASE34_ACTION", "evaluate").strip()
APPROVAL_TEXT = os.getenv("PHASE34_APPROVAL_TEXT", "").strip()
APPROVER = os.getenv("PHASE34_APPROVER", "").strip()

REQUIRED_PASS_DAYS = max(1, int(os.getenv("PHASE34_REQUIRED_PASS_DAYS", "5")))
MAX_STALE_DAYS = max(0, int(os.getenv("PHASE34_MAX_MARKET_STALE_DAYS", "3")))
MAX_DAILY_DRAWDOWN = float(os.getenv("PHASE34_MAX_DAILY_DRAWDOWN", "0.03"))
MAX_OPEN_POSITIONS = max(0, int(os.getenv("PHASE34_MAX_OPEN_POSITIONS", "10")))
SNAPSHOT_TABLE = os.getenv("PHASE34_SNAPSHOT_TABLE", "gptq_paper_daily_snapshots")

ALLOWED_ACTIONS = {"evaluate", "approve_production_paper", "revoke_production_paper"}
APPROVAL_PHRASE = "APPROVE PRODUCTION PAPER"


def utc_now():
    return datetime.now(timezone.utc)


def now_iso():
    return utc_now().isoformat()


def rest_get(table: str, params: dict):
    query = urllib.parse.urlencode(params)
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    req = urllib.request.Request(
        url,
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
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase GET {table}: HTTP {exc.code}: {body}") from exc


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def snapshot_pass(row):
    status = str(
        row.get("status")
        or row.get("pipeline_status")
        or row.get("pipeline")
        or ""
    ).upper()
    return status in {"COMPLETED", "PASS", "PASSED", "SUCCESS"}


def load_snapshots(limit=60):
    rows = rest_get(
        SNAPSHOT_TABLE,
        {
            "strategy_version": f"eq.{STRATEGY_VERSION}",
            "mode": f"eq.{MODE}",
            "order": "run_date.desc,completed_at.desc",
            "limit": str(limit),
        },
    )
    return rows if isinstance(rows, list) else []


def distinct_daily(rows):
    output = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = str(row.get("run_date") or "")[:10]
        if not d or d in seen:
            continue
        seen.add(d)
        output.append(row)
    return output


def consecutive_pass_days(rows):
    count = 0
    dates = []
    for row in distinct_daily(rows):
        if not snapshot_pass(row):
            break
        count += 1
        dates.append(str(row.get("run_date"))[:10])
    return count, dates


def stale_days(row):
    run_day = parse_date(row.get("run_date"))
    market_day = parse_date(row.get("latest_market_date"))
    if not run_day or not market_day:
        return None
    return max(0, (run_day - market_day).days)


def daily_drawdown(rows):
    daily = distinct_daily(rows)
    if len(daily) < 2:
        return 0.0
    current = as_float(daily[0].get("equity"))
    previous = as_float(daily[1].get("equity"))
    if previous <= 0:
        return 0.0
    return max(0.0, (previous - current) / previous)


def current_checks(row, drawdown):
    stale = stale_days(row)
    return {
        "latest_snapshot_pass": snapshot_pass(row),
        "latest_market_date_present": parse_date(row.get("latest_market_date")) is not None,
        "market_data_fresh": stale is not None and stale <= MAX_STALE_DAYS,
        "equity_non_negative": as_float(row.get("equity")) >= 0,
        "positions_within_limit": 0 <= as_int(row.get("positions_open")) <= MAX_OPEN_POSITIONS,
        "drawdown_within_limit": drawdown <= MAX_DAILY_DRAWDOWN,
        "safety_mode_locked": MODE == "SHADOW_ONLY_NO_BROKER",
    }


def approval_valid():
    return (
        ACTION == "approve_production_paper"
        and APPROVAL_TEXT == APPROVAL_PHRASE
        and len(APPROVER) >= 2
    )


def fingerprint(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def evaluate():
    rows = load_snapshots()
    daily = distinct_daily(rows)

    if not daily:
        return {
            "version": "3.4",
            "checked_at": now_iso(),
            "status": "FAIL",
            "qualification_state": "BLOCKED",
            "release_state": "LOCKED",
            "reason": "NO_DAILY_SNAPSHOTS",
            "checks": {},
        }

    current = daily[0]
    streak, streak_dates = consecutive_pass_days(rows)
    dd = daily_drawdown(rows)

    checks = current_checks(current, dd)
    checks["consecutive_pass_requirement"] = streak >= REQUIRED_PASS_DAYS

    qualified = all(checks.values())
    qualification_state = "QUALIFIED" if qualified else "OBSERVATION"
    release_state = "AWAITING_HUMAN_APPROVAL" if qualified else "LOCKED"
    status = "PASS"
    reason = "QUALIFIED_AWAITING_HUMAN_APPROVAL" if qualified else "OBSERVATION_CONTINUES"

    if ACTION == "approve_production_paper":
        if not qualified:
            status = "FAIL"
            release_state = "LOCKED"
            reason = "NOT_QUALIFIED_FOR_RELEASE"
        elif not approval_valid():
            status = "FAIL"
            release_state = "AWAITING_HUMAN_APPROVAL"
            reason = "EXPLICIT_HUMAN_APPROVAL_INVALID"
        else:
            release_state = "PRODUCTION_PAPER_APPROVED"
            reason = "HUMAN_APPROVAL_ACCEPTED"

    elif ACTION == "revoke_production_paper":
        release_state = "PRODUCTION_PAPER_REVOKED"
        reason = "HUMAN_REVOCATION_RECORDED"

    result = {
        "version": "3.4",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY_VERSION,
        "mode": MODE,
        "requested_action": ACTION,
        "status": status,
        "qualification_state": qualification_state,
        "release_state": release_state,
        "reason": reason,
        "pass_day_source": "distinct_run_date_snapshot_status",
        "required_consecutive_pass_days": REQUIRED_PASS_DAYS,
        "consecutive_pass_days": streak,
        "streak_dates": streak_dates,
        "latest_market_date": current.get("latest_market_date"),
        "market_stale_days": stale_days(current),
        "daily_drawdown": round(dd, 6),
        "checks": checks,
        "approval": {
            "required": True,
            "approver_present": bool(APPROVER),
            "approval_phrase_valid": APPROVAL_TEXT == APPROVAL_PHRASE,
        },
        "safety": {
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "automatic_live_switch_enabled": False,
            "paper_release_only": True,
            "kill_switch": "ARMED",
            "fail_closed": True,
        },
        "current_snapshot": {
            "run_key": current.get("run_key"),
            "run_date": current.get("run_date"),
            "equity": current.get("equity"),
            "cash": current.get("cash"),
            "market_value": current.get("market_value"),
            "positions_open": current.get("positions_open"),
            "orders_created": current.get("orders_created"),
        },
    }
    result["audit_fingerprint"] = fingerprint(result)
    return result


def write_files(result):
    (ROOT / "phase34_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checks = result.get("checks") or {}
    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.4",
        "",
        "## Human Approval + Production Paper Release Control",
        "",
        f"- Status: **{result.get('status')}**",
        f"- Qualification State: **{result.get('qualification_state')}**",
        f"- Release State: **{result.get('release_state')}**",
        f"- Requested Action: `{result.get('requested_action')}`",
        f"- Strategy: `{result.get('strategy_version', STRATEGY_VERSION)}`",
        f"- Trading Mode: `{result.get('mode', MODE)}`",
        f"- PASS-day Source: `{result.get('pass_day_source', '-')}`",
        f"- Consecutive PASS days: **{result.get('consecutive_pass_days', 0)} / {result.get('required_consecutive_pass_days', REQUIRED_PASS_DAYS)}**",
        f"- Latest market date: `{result.get('latest_market_date')}`",
        f"- Market stale days: `{result.get('market_stale_days')}`",
        f"- Daily drawdown: `{result.get('daily_drawdown')}`",
        "",
        "### Release Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| `{name}` | {'✅ PASS' if ok else '🟡 WAIT / ❌ FAIL'} |")

    lines += [
        "",
        "### Safety Lock",
        "",
        "- Production PAPER only: **YES**",
        "- Broker execution: **DISABLED**",
        "- Real-money execution: **DISABLED**",
        "- Automatic live switch: **DISABLED**",
        "- Kill switch: **ARMED**",
        "",
        f"- Audit fingerprint: `{result.get('audit_fingerprint', '-')}`",
    ]

    (ROOT / "phase34_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    if result.get("release_state") == "PRODUCTION_PAPER_APPROVED":
        manifest = {
            "release_id": f"phase34-{utc_now().strftime('%Y%m%dT%H%M%SZ')}",
            "approved_at": now_iso(),
            "approved_by": APPROVER,
            "strategy_version": STRATEGY_VERSION,
            "release_state": "PRODUCTION_PAPER_APPROVED",
            "mode": MODE,
            "consecutive_pass_days": result.get("consecutive_pass_days"),
            "latest_market_date": result.get("latest_market_date"),
            "audit_fingerprint": result.get("audit_fingerprint"),
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "automatic_live_switch_enabled": False,
        }
        (ROOT / "phase34_production_paper_release.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if result.get("release_state") == "PRODUCTION_PAPER_REVOKED":
        revocation = {
            "revoked_at": now_iso(),
            "revoked_by": APPROVER or "workflow_operator",
            "strategy_version": STRATEGY_VERSION,
            "release_state": "PRODUCTION_PAPER_REVOKED",
            "broker_execution_enabled": False,
            "real_money_enabled": False,
        }
        (ROOT / "phase34_release_revocation.json").write_text(
            json.dumps(revocation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main():
    if ACTION not in ALLOWED_ACTIONS:
        raise RuntimeError(f"Unsupported PHASE34_ACTION: {ACTION}")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety lock: Phase 3.4 requires SHADOW_ONLY_NO_BROKER"
        )

    result = evaluate()
    write_files(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
'@

$WorkflowContent = @'
name: GPT Quant V9.2 Paper Trading Phase 3.4 - Human Approval + Production Paper Release Control

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: "Strategy"
        required: true
        default: "V9.1"
        type: choice
        options:
          - V9
          - V9.1

      action:
        description: "Release-control action"
        required: true
        default: "evaluate"
        type: choice
        options:
          - evaluate
          - approve_production_paper
          - revoke_production_paper

      approver:
        description: "Human approver name/identifier (required for approval)"
        required: false
        default: ""
        type: string

      approval_text:
        description: "For approval enter exactly: APPROVE PRODUCTION PAPER"
        required: false
        default: ""
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-v92-paper-trading-phase34
  cancel-in-progress: false

jobs:
  human-approval-production-paper-release:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE34_ACTION: ${{ inputs.action || 'evaluate' }}
      PHASE34_APPROVER: ${{ inputs.approver || '' }}
      PHASE34_APPROVAL_TEXT: ${{ inputs.approval_text || '' }}

      PHASE34_REQUIRED_PASS_DAYS: "5"
      PHASE34_MAX_MARKET_STALE_DAYS: "3"
      PHASE34_MAX_DAILY_DRAWDOWN: "0.03"
      PHASE34_MAX_OPEN_POSITIONS: "10"
      PHASE34_SNAPSHOT_TABLE: gptq_paper_daily_snapshots

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Validate Phase 3.4 safety environment
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}" || {
            echo "::error::Missing SUPABASE_URL"
            exit 1
          }

          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}" || {
            echo "::error::Missing SUPABASE_SERVICE_ROLE_KEY"
            exit 1
          }

          test -f automation/v92/paper_trading_phase34_human_approval_release.py || {
            echo "::error::Missing Phase 3.4 Python file"
            exit 1
          }

          if [ "${PAPER_TRADING_MODE}" != "SHADOW_ONLY_NO_BROKER" ]; then
            echo "::error::Safety mode violation"
            exit 1
          fi

      - name: Validate explicit approval input
        if: ${{ inputs.action == 'approve_production_paper' }}
        shell: bash
        run: |
          set -euo pipefail

          if [ "${PHASE34_APPROVAL_TEXT}" != "APPROVE PRODUCTION PAPER" ]; then
            echo "::error::Approval phrase does not match."
            exit 1
          fi

          if [ -z "${PHASE34_APPROVER}" ]; then
            echo "::error::Approver is required."
            exit 1
          fi

      - name: Run Phase 3.4 release control
        shell: bash
        run: |
          set +e

          python automation/v92/paper_trading_phase34_human_approval_release.py
          RC=$?

          if [ -f phase34_summary.md ]; then
            cat phase34_summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

          exit "$RC"

      - name: Upload Phase 3.4 audit artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase34-production-paper-release-${{ github.run_id }}
          if-no-files-found: ignore
          retention-days: 90
          path: |
            phase34_result.json
            phase34_summary.md
            phase34_production_paper_release.json
            phase34_release_revocation.json
'@

[System.IO.File]::WriteAllText(
    $PythonTarget,
    $PythonContent,
    [System.Text.UTF8Encoding]::new($false)
)

[System.IO.File]::WriteAllText(
    $WorkflowTarget,
    $WorkflowContent,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Created:"
Write-Host "  $PythonTarget"
Write-Host "  $WorkflowTarget"
Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 3.4 DEPLOYMENT READY"
Write-Host "============================================================"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Open GitHub Desktop"
Write-Host "  2. Confirm the two new Phase 3.4 files"
Write-Host "  3. Commit to main"
Write-Host "  4. Push origin"
Write-Host "  5. GitHub Actions -> Phase 3.4 -> Run workflow"
Write-Host "  6. First run: V9.1 + evaluate"
Write-Host ""
Write-Host "Safety:"
Write-Host "  Production PAPER only"
Write-Host "  Broker trading DISABLED"
Write-Host "  Real-money trading DISABLED"
