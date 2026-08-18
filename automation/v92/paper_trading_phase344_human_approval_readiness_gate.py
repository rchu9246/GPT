#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase344_output"
OUT.mkdir(exist_ok=True)

STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE344_REQUIRED_PASS_DAYS", "5"))

PHASE3421 = ROOT / "automation/v92/paper_trading_phase3421_market_state_persistence_fix.py"
PHASE3421_SUMMARY = ROOT / "phase3421_output/market_state.json"
PHASE343 = ROOT / "automation/v92/paper_trading_phase343_approval_readiness.py"
PHASE343_SUMMARY = ROOT / "phase343_output/phase343_summary.json"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run_python(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing required engine: {path}")

    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PAPER_TRADING_MODE"] = MODE
    env["PHASE3421_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE343_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE344_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    p = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)

    if p.returncode != 0:
        raise RuntimeError(f"{path.name} failed with exit code {p.returncode}")

def load_json(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing summary: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON object: {path}")
    return data

def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    # Refresh canonical market + pass-day evidence first.
    run_python(PHASE3421)
    market_state = load_json(PHASE3421_SUMMARY)

    # Reuse existing Phase 3.4.3 readiness logic if present.
    if PHASE343.exists():
        run_python(PHASE343)
        readiness = load_json(PHASE343_SUMMARY)
    else:
        readiness = {}

    pass_days = int(
        readiness.get(
            "consecutive_pass_days",
            market_state.get("consecutive_pass_days", 0),
        )
    )

    latest_market_date = (
        readiness.get("latest_market_date")
        or market_state.get("latest_market_date")
    )

    market_stale_days = (
        readiness.get("market_stale_days")
        if readiness.get("market_stale_days") is not None
        else market_state.get("market_stale_days")
    )

    pass_source = (
        readiness.get("pass_day_source")
        or market_state.get("pass_day_source")
        or "distinct_run_date_snapshot_status"
    )

    canonical_valid = (
        market_state.get("status") == "PASS"
        and latest_market_date is not None
        and market_stale_days is not None
        and pass_source == "distinct_run_date_snapshot_status"
    )

    qualified = canonical_valid and pass_days >= REQUIRED_PASS_DAYS

    approval_readiness = (
        "READY_FOR_HUMAN_APPROVAL"
        if qualified
        else "NOT_READY"
    )

    qualification_state = (
        "QUALIFIED"
        if qualified
        else "OBSERVATION"
    )

    gate_state = (
        "OPEN_FOR_HUMAN_REVIEW"
        if qualified
        else "CLOSED_WAITING_FOR_QUALIFICATION"
    )

    result = {
        "version": "3.4.4",
        "checked_at": now_iso(),
        "status": "PASS" if canonical_valid else "BLOCKED",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,

        "qualification_state": qualification_state,
        "approval_readiness": approval_readiness,
        "human_approval_gate_state": gate_state,

        "pass_day_source": pass_source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "remaining_pass_days": max(REQUIRED_PASS_DAYS - pass_days, 0),

        "latest_market_date": latest_market_date,
        "market_stale_days": market_stale_days,
        "canonical_source_valid": canonical_valid,

        "release_state": "LOCKED",
        "release_authorized": False,
        "human_approval_required": True,
        "human_approval_recorded": False,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "fail_closed": True,
    }

    (OUT / "phase344_readiness.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.4",
        "",
        "## Human Approval Readiness Gate",
        "",
        f"- Status: **{result['status']}**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- Qualification State: **{qualification_state}**",
        f"- Approval Readiness: **{approval_readiness}**",
        f"- Human Approval Gate: **{gate_state}**",
        f"- PASS-day Source: `{pass_source}`",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Remaining PASS days: **{result['remaining_pass_days']}**",
        f"- Latest market date: `{latest_market_date}`",
        f"- Market stale days: `{market_stale_days}`",
        f"- Canonical source valid: **{'YES' if canonical_valid else 'NO'}**",
        "",
        "### Release Safety",
        "",
        "- Release State: **LOCKED**",
        "- Release authorized: **NO**",
        "- Human approval required: **YES**",
        "- Human approval recorded: **NO**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Missing/inconsistent evidence => **BLOCKED / FAIL-CLOSED**",
        "",
        "### Gate Semantics",
        "",
        "- `< 5 PASS days` => **NOT_READY / CLOSED_WAITING_FOR_QUALIFICATION**",
        "- `>= 5 PASS days` => **READY_FOR_HUMAN_APPROVAL / OPEN_FOR_HUMAN_REVIEW**",
        "- This phase **NEVER** authorizes release or enables broker/live-money trading.",
    ]

    (OUT / "phase344_readiness.md").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Observation is valid. Only invalid canonical evidence fails the workflow.
    return 0 if canonical_valid else 1

if __name__ == "__main__":
    raise SystemExit(main())