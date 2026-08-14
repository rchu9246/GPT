#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.4
Human Approval Gate + Release Authorization

Safety contract:
- Approval is MANUAL ONLY.
- Approval is impossible unless Phase 3.4.3 says READY_FOR_HUMAN_APPROVAL.
- Exact approval phrase + non-empty approver are required.
- Production PAPER release only.
- Broker execution remains disabled.
- Real-money trading remains disabled.
- Revocation is explicit and manual.
- Missing/inconsistent data fails closed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PHASE34 = ROOT / "automation" / "v92" / "paper_trading_phase34_human_approval_release.py"
PHASE343 = ROOT / "automation" / "v92" / "paper_trading_phase343_approval_readiness.py"

PHASE34_RESULT = ROOT / "phase34_result.json"
PHASE34_RELEASE = ROOT / "phase34_production_paper_release.json"
PHASE34_REVOCATION = ROOT / "phase34_release_revocation.json"
PHASE343_SUMMARY = ROOT / "phase343_output" / "phase343_summary.json"

OUTDIR = ROOT / "phase344_output"
OUTDIR.mkdir(exist_ok=True)

VERSION = "3.4.4"
MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")

ACTION = os.getenv("PHASE344_ACTION", "evaluate").strip().lower()
APPROVER = os.getenv("PHASE344_APPROVER", "").strip()
CONFIRMATION_TEXT = os.getenv("PHASE344_CONFIRMATION_TEXT", "").strip()

APPROVE_PHRASE = "APPROVE PRODUCTION PAPER"
REVOKE_PHRASE = "REVOKE PRODUCTION PAPER"
ALLOWED_ACTIONS = {"evaluate", "approve_production_paper", "revoke_production_paper"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing required file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return data


def run_command(script: Path, env: dict, label: str):
    if not script.exists():
        raise RuntimeError(f"Missing {label}: {script}")

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    safe = label.lower().replace(" ", "_").replace(".", "")
    (OUTDIR / f"{safe}_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (OUTDIR / f"{safe}_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError(
            f"{label} returned non-zero exit code.\n"
            f"exit_code={proc.returncode}\n"
            f"stdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )

    return proc


def run_phase343_readiness():
    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY_VERSION
    env["PAPER_TRADING_MODE"] = MODE
    env["PHASE343_REQUIRED_PASS_DAYS"] = os.getenv("PHASE343_REQUIRED_PASS_DAYS", "5")
    run_command(PHASE343, env, "phase343_readiness")
    return load_json(PHASE343_SUMMARY)


def validate_readiness(data):
    errors = []

    if data.get("canonical_source_valid") is not True:
        errors.append("canonical_source_invalid")

    if str(data.get("strategy_version")) != STRATEGY_VERSION:
        errors.append("strategy_version_mismatch")

    if str(data.get("trading_mode")) != MODE:
        errors.append("safety_mode_mismatch")

    if str(data.get("release_state")).upper() != "LOCKED":
        errors.append("preapproval_release_must_be_locked")

    try:
        pass_days = int(data.get("consecutive_pass_days"))
        required = int(data.get("required_pass_days"))
    except (TypeError, ValueError):
        errors.append("pass_day_fields_invalid")
        pass_days = -1
        required = 5

    ready = (
        not errors
        and str(data.get("status")).upper() == "PASS"
        and str(data.get("qualification_state")).upper() == "QUALIFIED"
        and str(data.get("approval_readiness")).upper() == "READY_FOR_HUMAN_APPROVAL"
        and pass_days >= required
    )

    return ready, errors, pass_days, required


def run_phase34_action(action: str):
    env = os.environ.copy()
    env["PAPER_STRATEGY_VERSION"] = STRATEGY_VERSION
    env["PAPER_TRADING_MODE"] = MODE
    env["PHASE34_ACTION"] = action
    env["PHASE34_APPROVER"] = APPROVER

    if action == "approve_production_paper":
        env["PHASE34_APPROVAL_TEXT"] = APPROVE_PHRASE
    else:
        env["PHASE34_APPROVAL_TEXT"] = ""

    run_command(PHASE34, env, f"phase34_{action}")
    return load_json(PHASE34_RESULT)


def validate_release_result(result):
    errors = []

    if str(result.get("mode")) != MODE:
        errors.append("release_mode_mismatch")

    state = str(result.get("release_state") or "").upper()
    if state != "PRODUCTION_PAPER_APPROVED":
        errors.append(f"unexpected_release_state:{state or 'EMPTY'}")

    if not PHASE34_RELEASE.exists():
        errors.append("release_manifest_missing")
        manifest = {}
    else:
        manifest = load_json(PHASE34_RELEASE)

    if manifest:
        if manifest.get("broker_execution_enabled") is not False:
            errors.append("broker_execution_not_disabled")
        if manifest.get("real_money_enabled") is not False:
            errors.append("real_money_not_disabled")
        if manifest.get("automatic_live_switch_enabled") is not False:
            errors.append("automatic_live_switch_not_disabled")
        if str(manifest.get("strategy_version")) != STRATEGY_VERSION:
            errors.append("manifest_strategy_mismatch")

    return len(errors) == 0, errors, manifest


def validate_revocation_result(result):
    errors = []
    state = str(result.get("release_state") or "").upper()

    if state != "PRODUCTION_PAPER_REVOKED":
        errors.append(f"unexpected_revocation_state:{state or 'EMPTY'}")

    if not PHASE34_REVOCATION.exists():
        errors.append("revocation_manifest_missing")
        revocation = {}
    else:
        revocation = load_json(PHASE34_REVOCATION)

    if revocation:
        if revocation.get("broker_execution_enabled") is not False:
            errors.append("revocation_broker_lock_invalid")
        if revocation.get("real_money_enabled") is not False:
            errors.append("revocation_real_money_lock_invalid")

    return len(errors) == 0, errors, revocation


def build_evaluation(readiness, ready, errors, pass_days, required):
    return {
        "version": VERSION,
        "checked_at": now_iso(),
        "action": "evaluate",
        "status": "PASS" if not errors else "BLOCKED",
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "qualification_state": readiness.get("qualification_state"),
        "approval_readiness": readiness.get("approval_readiness"),
        "release_state": "LOCKED",
        "consecutive_pass_days": pass_days if pass_days >= 0 else None,
        "required_pass_days": required,
        "human_approval_allowed": bool(ready),
        "human_approval_required": True,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "errors": errors,
    }


def execute():
    if ACTION not in ALLOWED_ACTIONS:
        raise RuntimeError(f"Unsupported PHASE344_ACTION: {ACTION}")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock violation: invalid trading mode")

    # Every Phase 3.4.4 operation starts with a fresh readiness evaluation.
    readiness = run_phase343_readiness()
    ready, readiness_errors, pass_days, required = validate_readiness(readiness)

    if ACTION == "evaluate":
        return build_evaluation(
            readiness, ready, readiness_errors, pass_days, required
        )

    if not APPROVER:
        return {
            **build_evaluation(readiness, ready, readiness_errors, pass_days, required),
            "action": ACTION,
            "status": "BLOCKED",
            "authorization_state": "DENIED",
            "errors": readiness_errors + ["approver_required"],
        }

    if ACTION == "approve_production_paper":
        approval_errors = list(readiness_errors)

        if not ready:
            approval_errors.append("not_ready_for_human_approval")

        if CONFIRMATION_TEXT != APPROVE_PHRASE:
            approval_errors.append("approval_phrase_mismatch")

        if approval_errors:
            return {
                **build_evaluation(readiness, ready, approval_errors, pass_days, required),
                "action": ACTION,
                "status": "BLOCKED",
                "authorization_state": "DENIED",
                "approver": APPROVER,
                "release_state": "LOCKED",
            }

        result = run_phase34_action("approve_production_paper")
        valid, release_errors, manifest = validate_release_result(result)

        return {
            "version": VERSION,
            "checked_at": now_iso(),
            "action": ACTION,
            "status": "PASS" if valid else "BLOCKED",
            "authorization_state": "AUTHORIZED" if valid else "DENIED",
            "strategy_version": STRATEGY_VERSION,
            "trading_mode": MODE,
            "qualification_state": "QUALIFIED",
            "approval_readiness": "READY_FOR_HUMAN_APPROVAL",
            "approver": APPROVER,
            "consecutive_pass_days": pass_days,
            "required_pass_days": required,
            "release_state": (
                "PRODUCTION_PAPER_APPROVED" if valid else "LOCKED"
            ),
            "production_paper_release": bool(valid),
            "human_approval_required": True,
            "automatic_approval": False,
            "broker_trading_enabled": False,
            "real_money_trading_enabled": False,
            "manifest_valid": bool(valid),
            "release_manifest": manifest if valid else None,
            "errors": release_errors,
        }

    # Explicit revocation. This is allowed only by a named human and exact phrase.
    revoke_errors = list(readiness_errors)

    if CONFIRMATION_TEXT != REVOKE_PHRASE:
        revoke_errors.append("revocation_phrase_mismatch")

    # Revocation should remain possible even if qualification is no longer READY,
    # therefore readiness is used for audit, not as a revocation blocker.
    blocking_revoke_errors = [
        e for e in revoke_errors
        if e in {"canonical_source_invalid", "strategy_version_mismatch", "safety_mode_mismatch"}
    ]
    if blocking_revoke_errors or CONFIRMATION_TEXT != REVOKE_PHRASE:
        return {
            **build_evaluation(readiness, ready, revoke_errors, pass_days, required),
            "action": ACTION,
            "status": "BLOCKED",
            "authorization_state": "DENIED",
            "approver": APPROVER,
            "release_state": "LOCKED",
        }

    result = run_phase34_action("revoke_production_paper")
    valid, revoke_result_errors, revocation = validate_revocation_result(result)

    return {
        "version": VERSION,
        "checked_at": now_iso(),
        "action": ACTION,
        "status": "PASS" if valid else "BLOCKED",
        "authorization_state": "REVOKED" if valid else "DENIED",
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "approver": APPROVER,
        "release_state": "PRODUCTION_PAPER_REVOKED" if valid else "LOCKED",
        "production_paper_release": False,
        "human_approval_required": True,
        "automatic_approval": False,
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "revocation_manifest": revocation if valid else None,
        "errors": revoke_result_errors,
    }


def write_summary(result):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return

    def v(x):
        return "N/A" if x is None else str(x)

    with open(path, "a", encoding="utf-8") as f:
        f.write("# GPT Quant V9.2 Paper Trading - Phase 3.4.4\n\n")
        f.write("## Human Approval Gate + Release Authorization\n\n")
        f.write(f"- Action: **{v(result.get('action'))}**\n")
        f.write(f"- Status: **{v(result.get('status'))}**\n")
        f.write(
            f"- Authorization State: **"
            f"{v(result.get('authorization_state', 'NOT_REQUESTED'))}**\n"
        )
        f.write(f"- Qualification State: **{v(result.get('qualification_state'))}**\n")
        f.write(f"- Approval Readiness: **{v(result.get('approval_readiness'))}**\n")
        f.write(f"- Release State: **{v(result.get('release_state'))}**\n")
        f.write(f"- Strategy: `{STRATEGY_VERSION}`\n")
        f.write(f"- Trading Mode: `{MODE}`\n")
        f.write(
            f"- Consecutive PASS days: **"
            f"{v(result.get('consecutive_pass_days'))} / "
            f"{v(result.get('required_pass_days'))}**\n"
        )
        f.write(
            f"- Human approval allowed: **"
            f"{'YES' if result.get('human_approval_allowed') else 'NO'}**\n"
        )

        if result.get("approver"):
            f.write(f"- Approver: `{result.get('approver')}`\n")

        errors = result.get("errors") or []
        if errors:
            f.write(f"- Gate errors: `{', '.join(map(str, errors))}`\n")

        f.write("\n### Release Safety\n\n")
        f.write("- Automatic approval: **DISABLED**\n")
        f.write("- Production PAPER only: **YES**\n")
        f.write("- Broker trading: **DISABLED**\n")
        f.write("- Real-money trading: **DISABLED**\n")
        f.write("- Missing/inconsistent authorization data => **BLOCKED / FAIL-CLOSED**\n")


def main():
    print("=== GPT Quant V9.2 Phase 3.4.4 Human Approval Gate + Release Authorization ===")

    try:
        result = execute()
    except Exception as exc:
        result = {
            "version": VERSION,
            "checked_at": now_iso(),
            "action": ACTION,
            "status": "BLOCKED",
            "authorization_state": "DENIED",
            "strategy_version": STRATEGY_VERSION,
            "trading_mode": MODE,
            "release_state": "LOCKED",
            "human_approval_required": True,
            "automatic_approval": False,
            "broker_trading_enabled": False,
            "real_money_trading_enabled": False,
            "errors": [str(exc)],
        }

    (OUTDIR / "phase344_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    write_summary(result)

    # Evaluation below 5/5 is a valid state and should remain green.
    if ACTION == "evaluate" and result.get("status") == "PASS":
        return 0

    # Requested approve/revoke must actually succeed; denied requests fail the job.
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())