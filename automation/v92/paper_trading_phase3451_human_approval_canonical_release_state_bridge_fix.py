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
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase3451_output"
COMPAT_OUT = ROOT / "phase345_output"
OUT.mkdir(exist_ok=True)
COMPAT_OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE345_REQUIRED_PASS_DAYS", "5"))

RECONSTRUCT = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
)
READINESS_JSON = ROOT / "phase344_output/phase344_readiness.json"

APPROVE_PHRASE = "I APPROVE PRODUCTION PAPER ONLY"
REJECT_PHRASE = "I REJECT PRODUCTION PAPER"

SAFETY_CONTRACT = "PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY"
BRIDGE_CONTRACT = "PHASE3451_CANONICAL_READINESS_TO_HUMAN_DECISION_RELEASE_BRIDGE"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing JSON evidence: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON object: {path}")
    return data


def evidence_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def run_reconstruction() -> None:
    if not RECONSTRUCT.exists():
        raise RuntimeError(f"Missing reconstruction engine: {RECONSTRUCT}")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE344_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE3421_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    proc = subprocess.run(
        [sys.executable, str(RECONSTRUCT)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Canonical reconstruction failed with exit code {proc.returncode}"
        )


def canonical_gate(readiness: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []

    checks = [
        (
            readiness.get("status") == "PASS",
            f"status={readiness.get('status')!r}, expected 'PASS'",
        ),
        (
            readiness.get("canonical_source_valid") is True,
            "canonical_source_valid is not true",
        ),
        (
            readiness.get("qualification_state") == "QUALIFIED",
            (
                "qualification_state="
                f"{readiness.get('qualification_state')!r}, expected 'QUALIFIED'"
            ),
        ),
        (
            readiness.get("approval_readiness") == "READY_FOR_HUMAN_APPROVAL",
            (
                "approval_readiness="
                f"{readiness.get('approval_readiness')!r}, "
                "expected 'READY_FOR_HUMAN_APPROVAL'"
            ),
        ),
        (
            readiness.get("human_approval_gate_state") == "OPEN_FOR_HUMAN_REVIEW",
            (
                "human_approval_gate_state="
                f"{readiness.get('human_approval_gate_state')!r}, "
                "expected 'OPEN_FOR_HUMAN_REVIEW'"
            ),
        ),
    ]

    for ok, message in checks:
        if not ok:
            failures.append(message)

    try:
        pass_days = int(readiness.get("consecutive_pass_days") or 0)
    except (TypeError, ValueError):
        pass_days = 0
        failures.append("consecutive_pass_days is not a valid integer")

    if pass_days < REQUIRED_PASS_DAYS:
        failures.append(
            f"consecutive_pass_days={pass_days}, required={REQUIRED_PASS_DAYS}"
        )

    if not readiness.get("latest_market_date"):
        failures.append("latest_market_date is missing")

    # IMPORTANT:
    # release_state=LOCKED and release_authorized=false are EXPECTED here.
    # This is the pre-human-approval canonical state and must NOT be treated
    # as a reason to reject an otherwise valid human APPROVE decision.
    return (len(failures) == 0, failures)


def persist(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = evidence_hash(result)

    json_text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (OUT / "phase3451_decision.json").write_text(json_text, encoding="utf-8")

    # Compatibility mirror so existing Phase 3.4.5 consumers can read the
    # post-bridge decision schema without any cross-workflow artifact.
    (COMPAT_OUT / "phase345_decision.json").write_text(json_text, encoding="utf-8")

    summary = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.5.1",
        "",
        "## Human Approval Canonical Release State Bridge Fix",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Bridge Contract: **{result['bridge_contract']}**",
        f"- Canonical Source Valid: **{'YES' if result['canonical_source_valid'] else 'NO'}**",
        f"- Qualification State: **{result['qualification_state']}**",
        f"- Approval Readiness: **{result['approval_readiness']}**",
        f"- Human Approval Gate: **{result['human_approval_gate_state']}**",
        (
            "- Consecutive PASS days: "
            f"**{result['consecutive_pass_days']} / {result['required_pass_days']}**"
        ),
        f"- Latest Market Date: `{result['latest_market_date']}`",
        "",
        "### Canonical State Bridge",
        "",
        f"- Canonical Gate Eligible: **{'YES' if result['canonical_gate_eligible'] else 'NO'}**",
        f"- Pre-Human Release State: **{result['canonical_release_state_before']}**",
        (
            "- Pre-Human Release Authorized: "
            f"**{'YES' if result['canonical_release_authorized_before'] else 'NO'}**"
        ),
        f"- Human Decision: **{result['human_decision']}**",
        f"- Approver: `{result['human_approver']}`",
        (
            "- Human Approval Recorded: "
            f"**{'YES' if result['human_approval_recorded'] else 'NO'}**"
        ),
        (
            "- Human Rejection Recorded: "
            f"**{'YES' if result['human_rejection_recorded'] else 'NO'}**"
        ),
        (
            "- Production Paper Activation Authorized: "
            f"**{'YES' if result['production_paper_activation_authorized'] else 'NO'}**"
        ),
        (
            "- Production Paper Release: "
            f"**{result['production_paper_release_state']}**"
        ),
        f"- Transition: `{result['release_transition']}`",
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
        "- Fail-closed policy: **ENABLED**",
        (
            "- Fail-closed triggered: "
            f"**{'YES' if result['fail_closed_triggered'] else 'NO'}**"
        ),
    ]

    if result.get("errors"):
        summary.extend(["", "### Errors", ""])
        summary.extend(f"- {item}" for item in result["errors"])

    md_text = "\n".join(summary) + "\n"
    (OUT / "phase3451_decision.md").write_text(md_text, encoding="utf-8")
    (COMPAT_OUT / "phase345_decision.md").write_text(md_text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(md_text)


def build_fail_closed_result(
    *,
    decision: str,
    approver: str,
    note: str,
    readiness: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    try:
        pass_days = int(readiness.get("consecutive_pass_days") or 0)
    except (TypeError, ValueError):
        pass_days = 0

    return {
        "version": "3.4.5.1",
        "status": "BLOCKED",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "bridge_contract": BRIDGE_CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "canonical_source_valid": readiness.get("canonical_source_valid") is True,
        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "human_approval_gate_state": readiness.get("human_approval_gate_state"),
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": readiness.get("latest_market_date"),
        "market_stale_days": readiness.get("market_stale_days"),
        "canonical_gate_eligible": False,
        "canonical_release_state_before": readiness.get("release_state", "LOCKED"),
        "canonical_release_authorized_before": bool(
            readiness.get("release_authorized", False)
        ),
        "human_decision": decision,
        "human_approver": approver,
        "human_approval_recorded": False,
        "human_rejection_recorded": decision == "REJECT",
        "approval_note": note,
        "production_paper_release_state": "LOCKED",
        "production_paper_activation_authorized": False,
        "release_transition": "BLOCKED_FAIL_CLOSED",
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": True,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    parser.add_argument("--approver", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    decision = args.decision.strip().upper()
    approver = args.approver.strip()
    confirmation = args.confirmation.strip()
    note = args.note.strip()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation: mode must remain SHADOW_ONLY_NO_BROKER")

    # Rebuild readiness in this same runner. No cross-workflow artifact dependency.
    run_reconstruction()
    readiness = load_json(READINESS_JSON)

    gate_ok, gate_failures = canonical_gate(readiness)

    expected_confirmation = (
        APPROVE_PHRASE if decision == "APPROVE" else REJECT_PHRASE
    )

    input_failures: list[str] = []
    if not approver:
        input_failures.append("Human approver must not be empty")
    if confirmation != expected_confirmation:
        input_failures.append(
            "Confirmation phrase mismatch; expected exactly: "
            f"{expected_confirmation}"
        )

    failures = gate_failures + input_failures
    if failures:
        result = build_fail_closed_result(
            decision=decision,
            approver=approver,
            note=note,
            readiness=readiness,
            errors=failures,
        )
        persist(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            "PHASE3451 BLOCKED / FAIL-CLOSED: " + "; ".join(failures),
            file=sys.stderr,
        )
        return 2

    pass_days = int(readiness.get("consecutive_pass_days") or 0)
    approved = decision == "APPROVE"

    # THE 3.4.5.1 BRIDGE:
    # The reconstructed canonical readiness intentionally arrives LOCKED before
    # human approval. A valid APPROVE is the ONLY event that transitions the
    # Production Paper release state to ACTIVE.
    release_state = "ACTIVE" if approved else "LOCKED"
    release_authorized = approved
    transition = (
        "LOCKED_TO_ACTIVE_BY_EXPLICIT_HUMAN_APPROVAL"
        if approved
        else "LOCKED_TO_LOCKED_BY_EXPLICIT_HUMAN_REJECTION"
    )

    result: dict[str, Any] = {
        "version": "3.4.5.1",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "bridge_contract": BRIDGE_CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "canonical_source_valid": True,
        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "human_approval_gate_state": readiness.get("human_approval_gate_state"),
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": readiness.get("latest_market_date"),
        "market_stale_days": readiness.get("market_stale_days"),
        "canonical_gate_eligible": True,

        # Preserve the reconstructed pre-human state as evidence.
        "canonical_release_state_before": readiness.get("release_state", "LOCKED"),
        "canonical_release_authorized_before": bool(
            readiness.get("release_authorized", False)
        ),
        "release_locked_before_human_approval": True,

        # Explicit human decision.
        "human_decision": decision,
        "human_approver": approver,
        "human_approval_recorded": approved,
        "human_rejection_recorded": not approved,
        "approval_note": note,

        # Post-human Production Paper state.
        "production_paper_release_state": release_state,
        "production_paper_activation_authorized": release_authorized,
        "release_transition": transition,

        # Hard safety locks — never changed by APPROVE.
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,

        # Policy is always enabled; it is not triggered on a valid decision.
        "fail_closed_policy": True,
        "fail_closed_triggered": False,
        "errors": [],
    }

    persist(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if approved:
        print(
            "PHASE3451 PASS: explicit human APPROVE bridged canonical "
            "readiness to Production Paper ACTIVE; broker/live-money remain disabled."
        )
    else:
        print(
            "PHASE3451 PASS: explicit human REJECT preserved Production Paper LOCKED."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
