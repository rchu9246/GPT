#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
REQUIRED_PASS_DAYS = int(os.getenv("PHASE343_REQUIRED_PASS_DAYS", "5"))

PHASE342_GUARD = ROOT / "automation/v92/paper_trading_phase342_qualification_state_fix.py"
PHASE343_READINESS = ROOT / "automation/v92/paper_trading_phase343_approval_readiness.py"

PHASE342_SUMMARY = ROOT / "phase342_output/phase342_summary.json"
PHASE343_SUMMARY = ROOT / "phase343_output/phase343_summary.json"

OUT = ROOT / "phase343_evidence_output"
OUT.mkdir(exist_ok=True)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run_script(path):
    if not path.exists():
        raise RuntimeError(f"Missing required engine: {path}")
    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["PAPER_TRADING_MODE"] = MODE
    env["PHASE342_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE343_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

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

def load_json(path):
    if not path.exists():
        raise RuntimeError(f"Missing evidence file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} is not a JSON object")
    return data

def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    # First refresh canonical qualification state.
    run_script(PHASE342_GUARD)

    # Then compute completion/readiness from that canonical source.
    run_script(PHASE343_READINESS)

    q = load_json(PHASE342_SUMMARY)
    r = load_json(PHASE343_SUMMARY)

    pass_days = r.get("consecutive_pass_days")
    remaining = r.get("remaining_pass_days")
    latest_market_date = r.get("latest_market_date")
    stale_days = r.get("market_stale_days")
    source = r.get("pass_day_source")
    source_valid = bool(r.get("canonical_source_valid"))

    if pass_days is None:
        raise RuntimeError("Missing consecutive_pass_days")
    if source != "distinct_run_date_snapshot_status":
        raise RuntimeError("Canonical PASS-day source mismatch")
    if not source_valid:
        raise RuntimeError("Canonical qualification source invalid")

    pass_days = int(pass_days)
    if remaining is None:
        remaining = max(REQUIRED_PASS_DAYS - pass_days, 0)

    qualified = (
        str(r.get("qualification_state")).upper() == "QUALIFIED"
        and pass_days >= REQUIRED_PASS_DAYS
    )

    evidence = {
        "phase": "3.4.3",
        "checked_at": now_iso(),
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "pass_day_source": source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "remaining_pass_days": int(remaining),
        "latest_market_date": latest_market_date,
        "market_stale_days": stale_days,
        "qualification_state": r.get("qualification_state"),
        "approval_readiness": r.get("approval_readiness"),
        "release_state": "LOCKED",
        "qualified_for_human_review": qualified,
        "human_approval_required": True,
        "automatic_approval": False,
        "broker_execution_enabled": False,
        "real_money_enabled": False,
        "fail_closed": True,
    }

    (OUT / "production_paper_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.3",
        "",
        "## Production Paper Evidence + 5-Day Qualification",
        "",
        f"- Status: **{evidence['status']}**",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- PASS-day Source: `{source}`",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Remaining PASS days: **{evidence['remaining_pass_days']}**",
        f"- Latest market date: `{latest_market_date}`",
        f"- Market stale days: `{stale_days}`",
        f"- Qualification State: **{evidence['qualification_state']}**",
        f"- Approval Readiness: **{evidence['approval_readiness']}**",
        f"- Release State: **LOCKED**",
        "",
        "### Safety Locks",
        "",
        "- Human approval required: **YES**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Missing/inconsistent qualification data => **BLOCKED / FAIL-CLOSED**",
    ]
    (OUT / "production_paper_evidence.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8"
    )

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")

    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())