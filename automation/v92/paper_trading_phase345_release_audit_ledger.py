#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.5
Release Audit Ledger + Approval Evidence

Creates an append-only-style audit evidence package from the canonical
Phase 3.4.4 gate result. It does NOT approve, release, revoke, trade,
or connect to a broker.

Security properties:
- evaluation/evidence only
- SHA-256 evidence fingerprint
- previous-entry hash chain when a prior ledger is supplied
- no secrets written to evidence
- fail closed on missing/inconsistent gate data
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ROOT / "phase345_output"
OUTDIR.mkdir(exist_ok=True)

VERSION = "3.4.5"
MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")

PHASE344_SUMMARY = ROOT / "phase344_output" / "phase344_summary.json"
PHASE343_SUMMARY = ROOT / "phase343_output" / "phase343_summary.json"
PHASE34_RESULT = ROOT / "phase34_result.json"
PHASE34_RELEASE = ROOT / "phase34_production_paper_release.json"
PHASE34_REVOCATION = ROOT / "phase34_release_revocation.json"

PREVIOUS_LEDGER = os.getenv("PHASE345_PREVIOUS_LEDGER", "").strip()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, required=False):
    if not path.exists():
        if required:
            raise RuntimeError(f"Missing required evidence source: {path}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return data


def canonical_bytes(obj):
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_obj(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_gate(gate):
    errors = []

    if str(gate.get("strategy_version")) != STRATEGY_VERSION:
        errors.append("strategy_version_mismatch")

    if str(gate.get("trading_mode")) != MODE:
        errors.append("trading_mode_mismatch")

    if gate.get("automatic_approval") is not False:
        errors.append("automatic_approval_lock_invalid")

    if gate.get("broker_trading_enabled") is not False:
        errors.append("broker_lock_invalid")

    if gate.get("real_money_trading_enabled") is not False:
        errors.append("real_money_lock_invalid")

    action = str(gate.get("action") or "")
    if action not in {"evaluate", "approve_production_paper", "revoke_production_paper"}:
        errors.append("unknown_gate_action")

    status = str(gate.get("status") or "").upper()
    if status not in {"PASS", "BLOCKED"}:
        errors.append("unknown_gate_status")

    return errors


def evidence_kind(gate):
    action = str(gate.get("action") or "")
    state = str(gate.get("authorization_state") or "NOT_REQUESTED").upper()

    if action == "approve_production_paper" and state == "AUTHORIZED":
        return "APPROVAL"
    if action == "revoke_production_paper" and state == "REVOKED":
        return "REVOCATION"
    if state == "DENIED":
        return "DENIAL"
    return "EVALUATION"


def source_record(name, path: Path, data):
    if data is None or not path.exists():
        return {
            "name": name,
            "present": False,
            "sha256": None,
        }
    return {
        "name": name,
        "present": True,
        "sha256": sha256_file(path),
    }


def previous_chain_hash():
    if not PREVIOUS_LEDGER:
        return None

    path = Path(PREVIOUS_LEDGER)
    if not path.is_absolute():
        path = ROOT / path

    if not path.exists():
        raise RuntimeError(f"Previous ledger file not found: {path}")

    return sha256_file(path)


def build_entry():
    gate = load_json(PHASE344_SUMMARY, required=True)
    gate_errors = validate_gate(gate)

    phase343 = load_json(PHASE343_SUMMARY)
    phase34 = load_json(PHASE34_RESULT)
    release = load_json(PHASE34_RELEASE)
    revocation = load_json(PHASE34_REVOCATION)

    kind = evidence_kind(gate)
    prev_hash = previous_chain_hash()

    # Only an actually authorized approval may claim a release manifest.
    if kind == "APPROVAL" and release is None:
        gate_errors.append("authorized_approval_missing_release_manifest")

    if kind == "REVOCATION" and revocation is None:
        gate_errors.append("revocation_missing_manifest")

    evidence = {
        "schema": "gpt_quant_v92_release_audit_ledger",
        "version": VERSION,
        "recorded_at": now_iso(),
        "evidence_kind": kind,
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "gate": {
            "action": gate.get("action"),
            "status": gate.get("status"),
            "authorization_state": gate.get("authorization_state", "NOT_REQUESTED"),
            "qualification_state": gate.get("qualification_state"),
            "approval_readiness": gate.get("approval_readiness"),
            "release_state": gate.get("release_state"),
            "consecutive_pass_days": gate.get("consecutive_pass_days"),
            "required_pass_days": gate.get("required_pass_days"),
            "human_approval_allowed": gate.get("human_approval_allowed"),
            "approver": gate.get("approver"),
        },
        "safety": {
            "automatic_approval": False,
            "broker_trading_enabled": False,
            "real_money_trading_enabled": False,
            "production_paper_only": True,
        },
        "sources": [
            source_record("phase344_summary", PHASE344_SUMMARY, gate),
            source_record("phase343_summary", PHASE343_SUMMARY, phase343),
            source_record("phase34_result", PHASE34_RESULT, phase34),
            source_record("phase34_release_manifest", PHASE34_RELEASE, release),
            source_record("phase34_revocation_manifest", PHASE34_REVOCATION, revocation),
        ],
        "chain": {
            "previous_ledger_sha256": prev_hash,
        },
        "validation": {
            "valid": len(gate_errors) == 0,
            "errors": gate_errors,
        },
    }

    fingerprint_payload = dict(evidence)
    evidence["evidence_fingerprint_sha256"] = sha256_obj(fingerprint_payload)
    return evidence


def write_markdown(entry):
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.5",
        "",
        "## Release Audit Ledger + Approval Evidence",
        "",
        f"- Status: **{'PASS' if entry['validation']['valid'] else 'BLOCKED'}**",
        f"- Evidence Kind: **{entry['evidence_kind']}**",
        f"- Strategy: `{entry['strategy_version']}`",
        f"- Trading Mode: `{entry['trading_mode']}`",
        f"- Gate Action: **{entry['gate']['action']}**",
        f"- Authorization State: **{entry['gate']['authorization_state']}**",
        f"- Qualification State: **{entry['gate']['qualification_state']}**",
        f"- Approval Readiness: **{entry['gate']['approval_readiness']}**",
        f"- Release State: **{entry['gate']['release_state']}**",
        f"- PASS days: **{entry['gate']['consecutive_pass_days']} / {entry['gate']['required_pass_days']}**",
        f"- Evidence Fingerprint: `{entry['evidence_fingerprint_sha256']}`",
        "",
        "### Audit Chain",
        "",
        f"- Previous ledger SHA-256: `{entry['chain']['previous_ledger_sha256'] or 'GENESIS'}`",
        "",
        "### Safety Locks",
        "",
        "- Automatic approval: **DISABLED**",
        "- Production PAPER only: **YES**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Phase 3.4.5 can authorize trades/releases: **NO**",
        "",
        "### Validation",
        "",
        f"- Evidence valid: **{'YES' if entry['validation']['valid'] else 'NO'}**",
    ]

    if entry["gate"].get("approver"):
        lines.append(f"- Approver: `{entry['gate']['approver']}`")

    if entry["validation"]["errors"]:
        lines.append(f"- Errors: `{', '.join(entry['validation']['errors'])}`")

    return "\n".join(lines) + "\n"


def main():
    try:
        entry = build_entry()
    except Exception as exc:
        entry = {
            "schema": "gpt_quant_v92_release_audit_ledger",
            "version": VERSION,
            "recorded_at": now_iso(),
            "evidence_kind": "ERROR",
            "strategy_version": STRATEGY_VERSION,
            "trading_mode": MODE,
            "gate": {
                "action": None,
                "authorization_state": "DENIED",
                "qualification_state": None,
                "approval_readiness": None,
                "release_state": "LOCKED",
                "consecutive_pass_days": None,
                "required_pass_days": None,
                "human_approval_allowed": False,
                "approver": None,
            },
            "safety": {
                "automatic_approval": False,
                "broker_trading_enabled": False,
                "real_money_trading_enabled": False,
                "production_paper_only": True,
            },
            "sources": [],
            "chain": {"previous_ledger_sha256": None},
            "validation": {"valid": False, "errors": [str(exc)]},
        }
        entry["evidence_fingerprint_sha256"] = sha256_obj(entry)

    ledger_path = OUTDIR / "phase345_audit_ledger.json"
    evidence_path = OUTDIR / "phase345_approval_evidence.json"
    summary_path = OUTDIR / "phase345_summary.md"

    ledger_path.write_text(
        json.dumps(entry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(entry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(write_markdown(entry), encoding="utf-8")

    print(json.dumps(entry, ensure_ascii=False, indent=2))

    github_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if github_summary:
        with open(github_summary, "a", encoding="utf-8") as f:
            f.write(write_markdown(entry))

    return 0 if entry["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())