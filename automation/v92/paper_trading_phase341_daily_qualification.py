import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "3.4.1"
STRATEGY_VERSION = os.getenv("STRATEGY_VERSION", "V9.1")
MODE = "SHADOW_ONLY_NO_BROKER"
REQUIRED_PASS_DAYS = 5

ROOT = Path(__file__).resolve().parents[2]
PHASE34 = ROOT / "automation" / "v92" / "paper_trading_phase34_human_approval_release.py"
OUTDIR = ROOT / "phase341_output"
OUTDIR.mkdir(exist_ok=True)

def run_phase34():
    if not PHASE34.exists():
        raise RuntimeError(f"Missing Phase 3.4 engine: {PHASE34}")

    env = os.environ.copy()
    env["STRATEGY_VERSION"] = STRATEGY_VERSION

    # Phase 3.4.1 is evaluation-only. It never sends approval/release actions.
    commands = [
        [sys.executable, str(PHASE34), "--action", "evaluate", "--strategy-version", STRATEGY_VERSION],
        [sys.executable, str(PHASE34), "evaluate"],
        [sys.executable, str(PHASE34)],
    ]

    last = None
    for cmd in commands:
        p = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True, capture_output=True)
        last = p
        if p.returncode == 0:
            return p
        combined = (p.stdout or "") + "\n" + (p.stderr or "")
        # Retry only when CLI shape differs. Do not mask real runtime failures.
        if not any(x in combined.lower() for x in ("unrecognized arguments", "usage:", "invalid choice")):
            break

    raise RuntimeError(
        "Phase 3.4 evaluate failed.\nSTDOUT:\n"
        + (last.stdout or "")
        + "\nSTDERR:\n"
        + (last.stderr or "")
    )

def extract_json(text):
    decoder = json.JSONDecoder()
    candidates = []
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, end = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                candidates.append(obj)
        except Exception:
            pass
    return candidates[-1] if candidates else {}

def pick(d, *names, default=None):
    for name in names:
        if name in d and d[name] is not None:
            return d[name]
    return default

def main():
    p = run_phase34()
    raw = (p.stdout or "").strip()
    data = extract_json(raw)

    pass_days = pick(data, "consecutive_pass_days", "pass_days", default=None)
    qualification = pick(data, "qualification_state", "promotion_state", default="OBSERVATION")
    release = pick(data, "release_state", default="LOCKED")
    status = pick(data, "status", default="PASS")
    source = pick(data, "pass_day_source", "pass_days_source", default="distinct_run_date_snapshot_status")
    latest_market_date = pick(data, "latest_market_date", default=None)
    stale_days = pick(data, "market_stale_days", "stale_days", default=None)

    # Safety invariant: this automation must never approve or release.
    if str(release).upper() in {"RELEASED", "PRODUCTION_PAPER"}:
        raise RuntimeError(
            "Safety invariant violated: daily qualification automation observed an automatic release state."
        )

    summary = {
        "version": VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "automation_mode": "DAILY_EVALUATION_ONLY",
        "requested_action": "evaluate",
        "pass_day_source": source,
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "qualification_state": qualification,
        "release_state": release,
        "latest_market_date": latest_market_date,
        "market_stale_days": stale_days,
        "human_approval_required": True,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
    }

    (OUTDIR / "phase341_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUTDIR / "phase34_raw_output.txt").write_text(raw + "\n", encoding="utf-8")

    print("=== GPT Quant V9.2 Paper Trading - Phase 3.4.1 ===")
    print("Daily Qualification Automation")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # GitHub Step Summary
    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        def val(v):
            return "N/A" if v is None else str(v)
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write("# GPT Quant V9.2 Paper Trading - Phase 3.4.1\n\n")
            f.write("## Daily Qualification Automation\n\n")
            f.write(f"- Status: **{val(status)}**\n")
            f.write(f"- Qualification State: **{val(qualification)}**\n")
            f.write(f"- Release State: **{val(release)}**\n")
            f.write(f"- Strategy: `{STRATEGY_VERSION}`\n")
            f.write(f"- Trading Mode: `{MODE}`\n")
            f.write(f"- PASS-day Source: `{val(source)}`\n")
            f.write(f"- Consecutive PASS days: **{val(pass_days)} / {REQUIRED_PASS_DAYS}**\n")
            f.write(f"- Latest market date: `{val(latest_market_date)}`\n")
            f.write(f"- Market stale days: `{val(stale_days)}`\n\n")
            f.write("### Safety Locks\n\n")
            f.write("- Human approval required: **YES**\n")
            f.write("- Automatic approval: **DISABLED**\n")
            f.write("- Broker trading: **DISABLED**\n")
            f.write("- Real-money trading: **DISABLED**\n")
            f.write("- This workflow only runs Phase 3.4 `evaluate`.\n")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
