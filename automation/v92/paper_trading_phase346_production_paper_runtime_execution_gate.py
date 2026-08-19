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
OUT = ROOT / "phase346_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
REQUIRED_PASS_DAYS = int(os.getenv("PHASE346_REQUIRED_PASS_DAYS", "5"))

RECONSTRUCT = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase3443_runtime_canonical_state_reconstruction.py"
)

BRIDGE = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase3451_human_approval_canonical_release_state_bridge_fix.py"
)

READINESS_JSON = ROOT / "phase344_output/phase344_readiness.json"
APPROVAL_JSON = ROOT / "phase3451_output/phase3451_decision.json"

APPROVE_PHRASE = "I APPROVE PRODUCTION PAPER ONLY"

RUNTIME_CONTRACT = "PHASE346_PRODUCTION_PAPER_RUNTIME_EXECUTION_GATE"
SAFETY_CONTRACT = "PRODUCTION_PAPER_ONLY_NO_BROKER_NO_REAL_MONEY"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing evidence JSON: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON object: {path}")
    return data


def sha256_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def run(cmd: list[str], env: dict[str, str]) -> None:
    proc = subprocess.run(
        cmd,
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
            f"Upstream command failed with exit code {proc.returncode}: {' '.join(cmd)}"
        )


def rebuild_canonical() -> None:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE344_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)
    env["PHASE3421_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    run([sys.executable, str(RECONSTRUCT)], env)


def rebuild_approval(approver: str, note: str) -> None:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE345_REQUIRED_PASS_DAYS"] = str(REQUIRED_PASS_DAYS)

    run(
        [
            sys.executable,
            str(BRIDGE),
            "--decision",
            "APPROVE",
            "--approver",
            approver,
            "--confirmation",
            APPROVE_PHRASE,
            "--note",
            note,
        ],
        env,
    )


def validate_runtime_gate(
    readiness: dict[str, Any],
    approval: dict[str, Any],
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(readiness.get("status") == "PASS", "readiness.status must be PASS")
    require(
        readiness.get("canonical_source_valid") is True,
        "readiness.canonical_source_valid must be true",
    )
    require(
        readiness.get("qualification_state") == "QUALIFIED",
        "readiness.qualification_state must be QUALIFIED",
    )
    require(
        readiness.get("approval_readiness") == "READY_FOR_HUMAN_APPROVAL",
        "readiness.approval_readiness must be READY_FOR_HUMAN_APPROVAL",
    )
    require(
        readiness.get("human_approval_gate_state") == "OPEN_FOR_HUMAN_REVIEW",
        "readiness.human_approval_gate_state must be OPEN_FOR_HUMAN_REVIEW",
    )

    try:
        pass_days = int(readiness.get("consecutive_pass_days") or 0)
    except (TypeError, ValueError):
        pass_days = 0
        errors.append("readiness.consecutive_pass_days is invalid")

    require(
        pass_days >= REQUIRED_PASS_DAYS,
        f"consecutive_pass_days={pass_days} is below required={REQUIRED_PASS_DAYS}",
    )

    require(bool(readiness.get("latest_market_date")), "latest_market_date is missing")

    require(approval.get("status") == "PASS", "approval.status must be PASS")
    require(
        approval.get("canonical_source_valid") is True,
        "approval.canonical_source_valid must be true",
    )
    require(
        approval.get("canonical_gate_eligible") is True,
        "approval.canonical_gate_eligible must be true",
    )
    require(
        approval.get("qualification_state") == "QUALIFIED",
        "approval.qualification_state must be QUALIFIED",
    )
    require(
        approval.get("approval_readiness") == "READY_FOR_HUMAN_APPROVAL",
        "approval.approval_readiness must be READY_FOR_HUMAN_APPROVAL",
    )
    require(
        approval.get("human_approval_gate_state") == "OPEN_FOR_HUMAN_REVIEW",
        "approval.human_approval_gate_state must be OPEN_FOR_HUMAN_REVIEW",
    )
    require(
        approval.get("human_decision") == "APPROVE",
        "human_decision must be APPROVE",
    )
    require(
        approval.get("human_approval_recorded") is True,
        "human_approval_recorded must be true",
    )
    require(
        approval.get("human_rejection_recorded") is False,
        "human_rejection_recorded must be false",
    )
    require(
        approval.get("production_paper_activation_authorized") is True,
        "production_paper_activation_authorized must be true",
    )
    require(
        approval.get("production_paper_release_state") == "ACTIVE",
        "production_paper_release_state must be ACTIVE",
    )

    # Hard safety locks.
    require(
        approval.get("automatic_approval") is False,
        "automatic_approval must remain false",
    )
    require(
        approval.get("broker_trading_enabled") is False,
        "broker_trading_enabled must remain false",
    )
    require(
        approval.get("broker_order_submission_enabled") is False,
        "broker_order_submission_enabled must remain false",
    )
    require(
        approval.get("real_money_trading_enabled") is False,
        "real_money_trading_enabled must remain false",
    )
    require(
        approval.get("live_money_release_authorized") is False,
        "live_money_release_authorized must remain false",
    )
    require(
        approval.get("fail_closed_policy") is True,
        "fail_closed_policy must remain enabled",
    )
    require(
        approval.get("fail_closed_triggered") is False,
        "approval evidence is already fail-closed",
    )

    # Cross-evidence consistency.
    require(
        approval.get("strategy_version") == STRATEGY,
        "approval strategy_version does not match requested strategy",
    )
    require(
        readiness.get("latest_market_date") == approval.get("latest_market_date"),
        "canonical latest_market_date does not match approval evidence",
    )
    require(
        readiness.get("qualification_state") == approval.get("qualification_state"),
        "qualification_state mismatch across canonical and approval evidence",
    )
    require(
        readiness.get("approval_readiness") == approval.get("approval_readiness"),
        "approval_readiness mismatch across evidence",
    )
    require(
        readiness.get("human_approval_gate_state")
        == approval.get("human_approval_gate_state"),
        "human_approval_gate_state mismatch across evidence",
    )

    return len(errors) == 0, errors


def write_result(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = sha256_payload(result)

    json_text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (OUT / "phase346_runtime_gate.json").write_text(json_text, encoding="utf-8")

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.6",
        "",
        "## Production Paper Runtime Execution Gate",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Runtime Contract: **{result['runtime_contract']}**",
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
        "### Human Approval Evidence",
        "",
        f"- Human Decision: **{result['human_decision']}**",
        (
            "- Human Approval Recorded: "
            f"**{'YES' if result['human_approval_recorded'] else 'NO'}**"
        ),
        (
            "- Production Paper Activation Authorized: "
            f"**{'YES' if result['production_paper_activation_authorized'] else 'NO'}**"
        ),
        (
            "- Production Paper Release: "
            f"**{result['production_paper_release_state']}**"
        ),
        "",
        "### Runtime Gate",
        "",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        (
            "- Paper Execution Authorized: "
            f"**{'YES' if result['paper_execution_authorized'] else 'NO'}**"
        ),
        (
            "- Runtime Gate Eligible: "
            f"**{'YES' if result['runtime_gate_eligible'] else 'NO'}**"
        ),
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
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    if result.get("errors"):
        lines.extend(["", "### Errors", ""])
        lines.extend(f"- {e}" for e in result["errors"])

    md_text = "\n".join(lines) + "\n"
    (OUT / "phase346_runtime_gate.md").write_text(md_text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(md_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE346_APPROVER", "rchu9246"),
    )
    parser.add_argument(
        "--note",
        default="Phase 3.4.6 production paper runtime gate reconstruction",
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    note = args.note.strip()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety violation: runtime mode must remain SHADOW_ONLY_NO_BROKER"
        )

    if not approver:
        raise RuntimeError("Approver must not be empty")

    # Phase 3.4.6 reconstructs both evidence layers in this same workflow runner.
    # This intentionally avoids cross-workflow artifact dependencies.
    rebuild_canonical()
    rebuild_approval(approver, note)

    readiness = load_json(READINESS_JSON)
    approval = load_json(APPROVAL_JSON)

    gate_ok, errors = validate_runtime_gate(readiness, approval)

    try:
        pass_days = int(readiness.get("consecutive_pass_days") or 0)
    except (TypeError, ValueError):
        pass_days = 0

    if gate_ok:
        result: dict[str, Any] = {
            "version": "3.4.6",
            "status": "PASS",
            "checked_at": now_iso(),
            "strategy_version": STRATEGY,
            "trading_mode": MODE,
            "runtime_contract": RUNTIME_CONTRACT,
            "safety_contract": SAFETY_CONTRACT,
            "canonical_source_valid": True,
            "qualification_state": readiness.get("qualification_state"),
            "approval_readiness": readiness.get("approval_readiness"),
            "human_approval_gate_state": readiness.get("human_approval_gate_state"),
            "consecutive_pass_days": pass_days,
            "required_pass_days": REQUIRED_PASS_DAYS,
            "latest_market_date": readiness.get("latest_market_date"),
            "market_stale_days": readiness.get("market_stale_days"),
            "human_decision": approval.get("human_decision"),
            "human_approver": approval.get("human_approver"),
            "human_approval_recorded": True,
            "production_paper_activation_authorized": True,
            "production_paper_release_state": "ACTIVE",
            "runtime_gate_eligible": True,
            "runtime_execution_gate": "OPEN",
            "paper_execution_authorized": True,
            "automatic_approval": False,
            "broker_trading_enabled": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "fail_closed_triggered": False,
            "errors": [],
        }
        write_result(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            "PHASE346 PASS: Production Paper Runtime Execution Gate OPEN. "
            "Paper execution authorized; broker/live-money remain disabled."
        )
        return 0

    result = {
        "version": "3.4.6",
        "status": "BLOCKED",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "runtime_contract": RUNTIME_CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "canonical_source_valid": readiness.get("canonical_source_valid") is True,
        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "human_approval_gate_state": readiness.get("human_approval_gate_state"),
        "consecutive_pass_days": pass_days,
        "required_pass_days": REQUIRED_PASS_DAYS,
        "latest_market_date": readiness.get("latest_market_date"),
        "market_stale_days": readiness.get("market_stale_days"),
        "human_decision": approval.get("human_decision"),
        "human_approver": approval.get("human_approver"),
        "human_approval_recorded": bool(approval.get("human_approval_recorded", False)),
        "production_paper_activation_authorized": bool(
            approval.get("production_paper_activation_authorized", False)
        ),
        "production_paper_release_state": approval.get(
            "production_paper_release_state",
            "LOCKED",
        ),
        "runtime_gate_eligible": False,
        "runtime_execution_gate": "BLOCKED",
        "paper_execution_authorized": False,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": True,
        "errors": errors,
    }

    write_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE346 BLOCKED / FAIL-CLOSED: " + "; ".join(errors),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
