#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.6
Persistent Audit Chain + Tamper Verification

Purpose:
- Persist Phase 3.4.5 evidence across GitHub Actions runs.
- Maintain a SHA-256 hash-linked audit chain.
- Re-verify the full chain before every append.
- Refuse to append if prior state is inconsistent/tampered.
- Run a non-destructive in-memory tamper self-test.
- Never approve, release, revoke, trade, or enable broker access.

Persistence transport is provided by GitHub Actions cache.
The cache is only storage; integrity is enforced by this program.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

VERSION = "3.4.6"
MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")

SOURCE_LEDGER = ROOT / "phase345_output" / "phase345_audit_ledger.json"

PERSIST_DIR = ROOT / "phase346_persistent"
PERSIST_DIR.mkdir(exist_ok=True)

CHAIN_FILE = PERSIST_DIR / f"audit_chain_{STRATEGY_VERSION.replace('.', '_')}.json"
HEAD_FILE = PERSIST_DIR / f"audit_chain_head_{STRATEGY_VERSION.replace('.', '_')}.json"

OUTDIR = ROOT / "phase346_output"
OUTDIR.mkdir(exist_ok=True)

MAX_ENTRIES = max(10, int(os.getenv("PHASE346_MAX_ENTRIES", "10000")))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(obj):
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_obj(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def load_json(path: Path, required=False):
    if not path.exists():
        if required:
            raise RuntimeError(f"Missing required JSON: {path}")
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON {path}: {exc}") from exc

    return data


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_phase345(source):
    errors = []

    if not isinstance(source, dict):
        return ["phase345_source_not_object"]

    if str(source.get("strategy_version")) != STRATEGY_VERSION:
        errors.append("phase345_strategy_version_mismatch")

    if str(source.get("trading_mode")) != MODE:
        errors.append("phase345_trading_mode_mismatch")

    validation = source.get("validation")
    if not isinstance(validation, dict) or validation.get("valid") is not True:
        errors.append("phase345_evidence_invalid")

    fingerprint = source.get("evidence_fingerprint_sha256")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        errors.append("phase345_fingerprint_invalid")

    safety = source.get("safety")
    if not isinstance(safety, dict):
        errors.append("phase345_safety_missing")
    else:
        if safety.get("automatic_approval") is not False:
            errors.append("automatic_approval_lock_invalid")
        if safety.get("broker_trading_enabled") is not False:
            errors.append("broker_lock_invalid")
        if safety.get("real_money_trading_enabled") is not False:
            errors.append("real_money_lock_invalid")
        if safety.get("production_paper_only") is not True:
            errors.append("production_paper_only_invalid")

    return errors


def genesis_chain():
    return {
        "schema": "gpt_quant_v92_persistent_audit_chain",
        "version": VERSION,
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "created_at": now_iso(),
        "updated_at": None,
        "entries": [],
    }


def entry_payload_without_hash(entry):
    data = dict(entry)
    data.pop("entry_hash_sha256", None)
    return data


def compute_entry_hash(entry):
    return sha256_obj(entry_payload_without_hash(entry))


def verify_chain(chain):
    errors = []

    if not isinstance(chain, dict):
        return False, ["chain_not_object"], None

    if chain.get("schema") != "gpt_quant_v92_persistent_audit_chain":
        errors.append("chain_schema_invalid")

    if str(chain.get("strategy_version")) != STRATEGY_VERSION:
        errors.append("chain_strategy_version_mismatch")

    if str(chain.get("trading_mode")) != MODE:
        errors.append("chain_trading_mode_mismatch")

    entries = chain.get("entries")
    if not isinstance(entries, list):
        errors.append("chain_entries_not_list")
        return False, errors, None

    if len(entries) > MAX_ENTRIES:
        errors.append("chain_too_large")

    expected_previous = None
    seen_hashes = set()

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry_{index}_not_object")
            continue

        sequence = entry.get("sequence")
        if sequence != index + 1:
            errors.append(f"entry_{index}_sequence_invalid")

        actual_previous = entry.get("previous_entry_hash_sha256")
        if actual_previous != expected_previous:
            errors.append(f"entry_{index}_previous_hash_mismatch")

        stored_hash = entry.get("entry_hash_sha256")
        calculated_hash = compute_entry_hash(entry)

        if stored_hash != calculated_hash:
            errors.append(f"entry_{index}_hash_mismatch")

        if stored_hash in seen_hashes:
            errors.append(f"entry_{index}_duplicate_hash")

        if stored_hash:
            seen_hashes.add(stored_hash)
            expected_previous = stored_hash

    head = expected_previous
    return len(errors) == 0, errors, head


def build_entry(source, previous_hash, sequence):
    gate = source.get("gate") if isinstance(source.get("gate"), dict) else {}

    entry = {
        "sequence": sequence,
        "recorded_at": now_iso(),
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": MODE,
        "evidence_kind": source.get("evidence_kind"),
        "phase345_evidence_fingerprint_sha256": source.get("evidence_fingerprint_sha256"),
        "gate_snapshot": {
            "action": gate.get("action"),
            "status": gate.get("status"),
            "authorization_state": gate.get("authorization_state"),
            "qualification_state": gate.get("qualification_state"),
            "approval_readiness": gate.get("approval_readiness"),
            "release_state": gate.get("release_state"),
            "consecutive_pass_days": gate.get("consecutive_pass_days"),
            "required_pass_days": gate.get("required_pass_days"),
            "approver": gate.get("approver"),
        },
        "safety": {
            "automatic_approval": False,
            "production_paper_only": True,
            "broker_trading_enabled": False,
            "real_money_trading_enabled": False,
        },
        "previous_entry_hash_sha256": previous_hash,
    }
    entry["entry_hash_sha256"] = compute_entry_hash(entry)
    return entry


def tamper_self_test(chain):
    """
    Non-destructive test:
    mutate a deep copy of a chain entry and verify that validation fails.
    The real persistent chain is never modified.
    """
    if not chain.get("entries"):
        return {
            "performed": False,
            "detected": None,
            "reason": "no_entries_available",
        }

    probe = copy.deepcopy(chain)
    probe["entries"][-1]["gate_snapshot"]["release_state"] = "TAMPERED_TEST_VALUE"

    valid, errors, _ = verify_chain(probe)

    return {
        "performed": True,
        "detected": not valid,
        "expected_detection": True,
        "verification_errors": errors,
    }


def main():
    try:
        source = load_json(SOURCE_LEDGER, required=True)
        source_errors = validate_phase345(source)
        if source_errors:
            raise RuntimeError("Phase 3.4.5 source invalid: " + ", ".join(source_errors))

        restored = CHAIN_FILE.exists()

        if restored:
            chain = load_json(CHAIN_FILE, required=True)
        else:
            chain = genesis_chain()

        pre_valid, pre_errors, previous_head = verify_chain(chain)
        if not pre_valid:
            raise RuntimeError(
                "TAMPER/INTEGRITY FAILURE before append: " + ", ".join(pre_errors)
            )

        # Append one evidence record for this workflow run.
        entry = build_entry(
            source=source,
            previous_hash=previous_head,
            sequence=len(chain["entries"]) + 1,
        )
        chain["entries"].append(entry)
        chain["updated_at"] = now_iso()

        post_valid, post_errors, new_head = verify_chain(chain)
        if not post_valid:
            raise RuntimeError(
                "Integrity failure after append: " + ", ".join(post_errors)
            )

        tamper_test = tamper_self_test(chain)
        if tamper_test.get("performed") and tamper_test.get("detected") is not True:
            raise RuntimeError("Tamper self-test failed to detect mutation")

        save_json(CHAIN_FILE, chain)

        head = {
            "schema": "gpt_quant_v92_persistent_audit_chain_head",
            "version": VERSION,
            "strategy_version": STRATEGY_VERSION,
            "trading_mode": MODE,
            "updated_at": now_iso(),
            "entry_count": len(chain["entries"]),
            "head_hash_sha256": new_head,
            "last_phase345_evidence_fingerprint_sha256": source.get(
                "evidence_fingerprint_sha256"
            ),
        }
        save_json(HEAD_FILE, head)

        result = {
            "version": VERSION,
            "checked_at": now_iso(),
            "status": "PASS",
            "strategy_version": STRATEGY_VERSION,
            "trading_mode": MODE,
            "persistent_state_restored": restored,
            "pre_append_chain_valid": True,
            "post_append_chain_valid": True,
            "tamper_detected_in_self_test": tamper_test.get("detected"),
            "tamper_self_test_performed": tamper_test.get("performed"),
            "entry_count": len(chain["entries"]),
            "previous_head_hash_sha256": previous_head,
            "new_head_hash_sha256": new_head,
            "phase345_evidence_fingerprint_sha256": source.get(
                "evidence_fingerprint_sha256"
            ),
            "chain_file": str(CHAIN_FILE.relative_to(ROOT)),
            "safety": {
                "automatic_approval": False,
                "production_paper_only": True,
                "broker_trading_enabled": False,
                "real_money_trading_enabled": False,
                "phase346_can_authorize_release": False,
            },
            "errors": [],
        }

    except Exception as exc:
        result = {
            "version": VERSION,
            "checked_at": now_iso(),
            "status": "BLOCKED",
            "strategy_version": STRATEGY_VERSION,
            "trading_mode": MODE,
            "persistent_state_restored": CHAIN_FILE.exists(),
            "pre_append_chain_valid": False,
            "post_append_chain_valid": False,
            "tamper_detected_in_self_test": None,
            "tamper_self_test_performed": False,
            "entry_count": None,
            "previous_head_hash_sha256": None,
            "new_head_hash_sha256": None,
            "phase345_evidence_fingerprint_sha256": None,
            "chain_file": str(CHAIN_FILE.relative_to(ROOT)),
            "safety": {
                "automatic_approval": False,
                "production_paper_only": True,
                "broker_trading_enabled": False,
                "real_money_trading_enabled": False,
                "phase346_can_authorize_release": False,
            },
            "errors": [str(exc)],
        }

    save_json(OUTDIR / "phase346_summary.json", result)

    md = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.6",
        "",
        "## Persistent Audit Chain + Tamper Verification",
        "",
        f"- Status: **{result['status']}**",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Persistent state restored: **{'YES' if result['persistent_state_restored'] else 'NO / GENESIS'}**",
        f"- Pre-append chain valid: **{'YES' if result['pre_append_chain_valid'] else 'NO'}**",
        f"- Post-append chain valid: **{'YES' if result['post_append_chain_valid'] else 'NO'}**",
        f"- Entry count: **{result['entry_count'] if result['entry_count'] is not None else 'N/A'}**",
        f"- Previous head SHA-256: `{result['previous_head_hash_sha256'] or 'GENESIS'}`",
        f"- New head SHA-256: `{result['new_head_hash_sha256'] or 'N/A'}`",
        f"- Phase 3.4.5 Evidence Fingerprint: `{result['phase345_evidence_fingerprint_sha256'] or 'N/A'}`",
        "",
        "### Tamper Verification",
        "",
        f"- Self-test performed: **{'YES' if result['tamper_self_test_performed'] else 'NO'}**",
        f"- Tamper detected: **{'YES' if result['tamper_detected_in_self_test'] else 'NO' if result['tamper_detected_in_self_test'] is False else 'N/A'}**",
        "",
        "### Safety Locks",
        "",
        "- Automatic approval: **DISABLED**",
        "- Production PAPER only: **YES**",
        "- Broker trading: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Phase 3.4.6 can authorize releases: **NO**",
        "- Invalid/tampered previous chain => **BLOCKED / FAIL-CLOSED**",
    ]

    if result["errors"]:
        md.extend(["", "### Errors", "", f"- `{'; '.join(result['errors'])}`"])

    markdown = "\n".join(md) + "\n"
    (OUTDIR / "phase346_summary.md").write_text(markdown, encoding="utf-8")

    github_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if github_summary:
        with open(github_summary, "a", encoding="utf-8") as f:
            f.write(markdown)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())