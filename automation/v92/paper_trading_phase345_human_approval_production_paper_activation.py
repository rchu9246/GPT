#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase345_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
REQUIRED_PASS_DAYS = int(os.getenv("PHASE345_REQUIRED_PASS_DAYS", "5"))

RECONSTRUCT = ROOT / "automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
READINESS_JSON = ROOT / "phase344_output/phase344_readiness.json"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run_reconstruction():
    if not RECONSTRUCT.exists():
        raise RuntimeError(f"Missing reconstruction engine: {RECONSTRUCT}")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE344_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    p = subprocess.run(
        [sys.executable, str(RECONSTRUCT)],
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
        raise RuntimeError(f"Canonical reconstruction failed with exit code {p.returncode}")

def load_json(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing readiness evidence: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid readiness JSON: {path}")
    return data

def evidence_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    parser.add_argument("--approver", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation")

    run_reconstruction()
    readiness = load_json(READINESS_JSON)

    if readiness.get("status") != "PASS":
        raise RuntimeError("Readiness status is not PASS")
    if readiness.get("canonical_source_valid") is not True:
        raise RuntimeError("Canonical source invalid")
    if readiness.get("qualification_state") != "QUALIFIED":
        raise RuntimeError("Qualification state is not QUALIFIED")
    if readiness.get("approval_readiness") != "READY_FOR_HUMAN_APPROVAL":
        raise RuntimeError("Approval readiness is not READY_FOR_HUMAN_APPROVAL")
    if readiness.get("human_approval_gate_state") != "OPEN_FOR_HUMAN_REVIEW":
        raise RuntimeError("Human approval gate is not OPEN_FOR_HUMAN_REVIEW")

    pass_days = int(readiness.get("consecutive_pass_days") or 0)
    if pass_days < REQUIRED_PASS_DAYS:
        raise RuntimeError("Insufficient PASS-day count")

    latest_market_date = readiness.get("latest_market_date")
    if not latest_market_date:
        raise RuntimeError("Missing latest_market_date")

    expected_confirmation = (
        "I APPROVE PRODUCTION PAPER ONLY"
        if args.decision == "APPROVE"
        else "I REJECT PRODUCTION PAPER"
    )

    if args.confirmation.strip() != expected_confirmation:
        raise RuntimeError(
            "Confirmation phrase mismatch. "
            f"Expected exactly: {expected_confirmation}"
        )

    approved = args.decision == "APPROVE"

    # IMPORTANT:
    # Approval only activates PRODUCTION PAPER.
    # Broker and real-money execution remain hard-disabled.
    result = {
        "version": "3.4.5",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,

        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "human_approval_gate_state": readiness.get("human_approval_gate_state"),
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": latest_market_date,
        "market_stale_days": readiness.get("market_stale_days"),
        "canonical_source_valid": True,

        "human_decision": args.decision,
        "human_approver": args.approver,
        "human_approval_recorded": approved,
        "human_rejection_recorded": not approved,
        "approval_note": args.note,

        "production_paper_release_state": "ACTIVE" if approved else "LOCKED",
        "production_paper_activation_authorized": approved,

        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "live_money_release_authorized": False,

        "safety_contract": "PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY",
        "fail_closed": True,
    }

    result["evidence_sha256"] = evidence_hash(result)

    (OUT / "phase345_decision.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.5",
        "",
        "## Human Approval Decision + Production Paper Activation",
        "",
        f"- Strategy: `{STRATEGY}`",
        f"- Trading Mode: `{MODE}`",
        f"- Qualification State: **{result['qualification_state']}**",
        f"- Approval Readiness: **{result['approval_readiness']}**",
        f"- Human Approval Gate: **{result['human_approval_gate_state']}**",
        f"- Consecutive PASS days: **{pass_days} / {REQUIRED_PASS_DAYS}**",
        f"- Latest market date: `{latest_market_date}`",
        f"- Canonical source valid: **YES**",
        "",
        "### Human Decision",
        "",
        f"- Decision: **{args.decision}**",
        f"- Approver: `{args.approver}`",
        f"- Human approval recorded: **{'YES' if approved else 'NO'}**",
        f"- Production Paper Release: **{'ACTIVE' if approved else 'LOCKED'}**",
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
        "",
        "### Safety Boundary",
        "",
        "- Production Paper only: **YES**",
        "- Automatic approval: **DISABLED**",
        "- Broker trading: **DISABLED**",
        "- Broker order submission: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Live-money release authorized: **NO**",
        "- Missing/inconsistent evidence => **BLOCKED / FAIL-CLOSED**",
    ]

    (OUT / "phase345_decision.md").write_text(
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