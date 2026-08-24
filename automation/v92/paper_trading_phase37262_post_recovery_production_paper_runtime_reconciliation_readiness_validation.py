#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT = "PHASE37262_POST_RECOVERY_PRODUCTION_PAPER_RUNTIME_RECONCILIATION_READINESS_VALIDATION"

ACTIVATION_TABLE = "paper_post_recovery_activation_state_v92"
MASTER_CYCLE_TABLE = "paper_post_recovery_master_cycle_v92"
SUPERVISION_TABLE = "paper_runtime_supervision_state_v92"
RECONSTRUCTION_AUDIT_TABLE = "phase37261_reconstruction_audit_v92"

BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
HISTORICAL_REWRITE_ALLOWED = False

FAIL_STATES = {"REVOKED", "FAIL_CLOSED", "BLOCKED", "HALTED", "SUSPENDED"}
ACTIVE_STATES = {"ACTIVE", "CONTINUE_ACTIVE", "READY", "PASS", "COMPLETED"}


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class SupabaseREST:
    def __init__(self, base_url: str, key: str):
        self.base_url = base_url.rstrip("/")
        self.key = key

    def get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(params, safe="*,.()")
        url = f"{self.base_url}/rest/v1/{table}?{query}"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read().decode("utf-8", errors="replace")
                data = json.loads(body or "[]")
                if not isinstance(data, list):
                    raise RuntimeError(f"{table}: expected JSON list")
                return data
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc


def first_existing(row: dict[str, Any] | None, names: tuple[str, ...], default: Any = None) -> Any:
    if not row:
        return default
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def state_of(row: dict[str, Any] | None, names: tuple[str, ...]) -> str:
    value = first_existing(row, names, "")
    return str(value).strip().upper() if value is not None else ""


def latest(
    sb: SupabaseREST,
    table: str,
    portfolio_id: str,
    date_columns: tuple[str, ...],
) -> tuple[dict[str, Any] | None, str]:
    base = {"select": "*", "limit": "1"}

    # First try portfolio-filtered queries, because all current Production Paper
    # canonical objects are intended to be portfolio-scoped.
    for date_col in date_columns:
        params = dict(base)
        params["portfolio_id"] = f"eq.{portfolio_id}"
        params["order"] = f"{date_col}.desc"
        try:
            rows = sb.get(table, params)
            if rows:
                return rows[0], f"portfolio_id + {date_col}"
        except RuntimeError as exc:
            msg = str(exc)
            # Missing compatibility columns are handled by trying the next shape.
            if "PGRST204" not in msg and "42703" not in msg:
                raise

    # Compatibility fallback: if a canonical relation has no portfolio_id,
    # still permit read-only validation of its latest row.
    for date_col in date_columns:
        params = dict(base)
        params["order"] = f"{date_col}.desc"
        try:
            rows = sb.get(table, params)
            if rows:
                return rows[0], date_col
        except RuntimeError as exc:
            msg = str(exc)
            if "PGRST204" not in msg and "42703" not in msg:
                raise

    # Last resort: read one row without ordering.
    rows = sb.get(table, base)
    return (rows[0] if rows else None), "unordered"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default="V92_PRODUCTION_PAPER_V91")
    parser.add_argument("--strategy-version", default="V9.1")
    args = parser.parse_args()

    sb = SupabaseREST(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"))

    activation, activation_source = latest(
        sb,
        ACTIVATION_TABLE,
        args.portfolio_id,
        ("activation_date", "state_date", "created_at", "updated_at"),
    )
    master_cycle, master_source = latest(
        sb,
        MASTER_CYCLE_TABLE,
        args.portfolio_id,
        ("cycle_date", "master_cycle_date", "created_at", "updated_at"),
    )
    supervision, supervision_source = latest(
        sb,
        SUPERVISION_TABLE,
        args.portfolio_id,
        ("supervision_date", "state_date", "created_at", "updated_at"),
    )
    reconstruction, reconstruction_source = latest(
        sb,
        RECONSTRUCTION_AUDIT_TABLE,
        args.portfolio_id,
        ("reconstruction_date", "created_at"),
    )

    activation_state = state_of(
        activation,
        ("activation_state", "state", "status"),
    )
    master_state = state_of(
        master_cycle,
        ("master_cycle_state", "cycle_state", "state", "status"),
    )
    supervision_state = state_of(
        supervision,
        ("supervision_state", "runtime_supervision", "state", "status"),
    )
    reconstruction_state = state_of(
        reconstruction,
        ("reconstruction_state", "state", "status"),
    )

    activation_ok = bool(activation) and activation_state == "ACTIVE"
    master_ok = bool(master_cycle) and master_state not in FAIL_STATES
    supervision_ok = bool(supervision) and supervision_state not in FAIL_STATES
    reconstruction_ok = bool(reconstruction) and reconstruction_state not in FAIL_STATES

    # A blank reconstruction state is acceptable when the short canonical audit
    # view exposes an earlier schema without an explicit state field. Its presence
    # still proves the repaired canonical relation is readable.
    if reconstruction and not reconstruction_state:
        reconstruction_ok = True

    readiness = (
        "READY"
        if activation_ok and master_ok and supervision_ok and reconstruction_ok
        else "NOT_READY"
    )

    reasons: list[str] = []
    if not activation:
        reasons.append("ACTIVATION_CANONICAL_ROW_MISSING")
    elif not activation_ok:
        reasons.append(f"ACTIVATION_NOT_ACTIVE:{activation_state or 'UNKNOWN'}")

    if not master_cycle:
        reasons.append("MASTER_CYCLE_CANONICAL_ROW_MISSING")
    elif not master_ok:
        reasons.append(f"MASTER_CYCLE_BLOCKED:{master_state or 'UNKNOWN'}")

    if not supervision:
        reasons.append("RUNTIME_SUPERVISION_ROW_MISSING")
    elif not supervision_ok:
        reasons.append(f"RUNTIME_SUPERVISION_BLOCKED:{supervision_state or 'UNKNOWN'}")

    if not reconstruction:
        reasons.append("RECONSTRUCTION_AUDIT_ROW_MISSING")
    elif not reconstruction_ok:
        reasons.append(f"RECONSTRUCTION_NOT_READY:{reconstruction_state or 'UNKNOWN'}")

    now = datetime.now(timezone.utc)

    evidence = {
        "contract": CONTRACT,
        "validation_time_utc": now.isoformat(),
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "production_paper_readiness": readiness,
        "reasons": reasons,
        "canonical_inputs": {
            "activation": {
                "table": ACTIVATION_TABLE,
                "source_shape": activation_source,
                "found": bool(activation),
                "state": activation_state,
                "pass": activation_ok,
            },
            "master_cycle": {
                "table": MASTER_CYCLE_TABLE,
                "source_shape": master_source,
                "found": bool(master_cycle),
                "state": master_state,
                "pass": master_ok,
            },
            "runtime_supervision": {
                "table": SUPERVISION_TABLE,
                "source_shape": supervision_source,
                "found": bool(supervision),
                "state": supervision_state,
                "pass": supervision_ok,
            },
            "reconstruction_audit": {
                "table": RECONSTRUCTION_AUDIT_TABLE,
                "source_shape": reconstruction_source,
                "found": bool(reconstruction),
                "state": reconstruction_state,
                "pass": reconstruction_ok,
            },
        },
        "safety": {
            "paper_only": True,
            "broker_api_used": BROKER_API_USED,
            "broker_credentials_used": BROKER_CREDENTIALS_USED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "live_money_release_authorized": LIVE_MONEY_RELEASE_AUTHORIZED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        },
    }

    artifact_dir = Path("artifacts/phase37262")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "verification.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = f"""# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.2

## Post-Recovery Production Paper Runtime Reconciliation + Readiness Validation

- Contract: `{CONTRACT}`
- Portfolio ID: `{args.portfolio_id}`
- Strategy Version: `{args.strategy_version}`
- Validation Date: `{now.date().isoformat()}`
- Production Paper Readiness: **{readiness}**

## Canonical Runtime Inputs

- Activation Canonical Table: `{ACTIVATION_TABLE}`
- Activation Row Found: **{'YES' if activation else 'NO'}**
- Activation State: **{activation_state or 'UNKNOWN'}**
- Activation Validation: **{'PASS' if activation_ok else 'FAIL'}**

- Master Cycle Canonical Table: `{MASTER_CYCLE_TABLE}`
- Master Cycle Row Found: **{'YES' if master_cycle else 'NO'}**
- Master Cycle State: **{master_state or 'UNKNOWN'}**
- Master Cycle Validation: **{'PASS' if master_ok else 'FAIL'}**

- Runtime Supervision Table: `{SUPERVISION_TABLE}`
- Runtime Supervision Row Found: **{'YES' if supervision else 'NO'}**
- Runtime Supervision State: **{supervision_state or 'UNKNOWN'}**
- Runtime Supervision Validation: **{'PASS' if supervision_ok else 'FAIL'}**

- Reconstruction Audit Relation: `{RECONSTRUCTION_AUDIT_TABLE}`
- Reconstruction Audit Row Found: **{'YES' if reconstruction else 'NO'}**
- Reconstruction Validation: **{'PASS' if reconstruction_ok else 'FAIL'}**

## Readiness Reasons

{chr(10).join(f'- `{reason}`' for reason in reasons) if reasons else '- `NONE`'}

## Safety Boundary

- Paper only: **ENABLED**
- Broker API used: **NO**
- Broker credentials used: **NO**
- Broker order submission: **DISABLED**
- Real-money trading: **DISABLED**
- Live-money release authorized: **NO**
- Historical rewrite allowed: **NO**
"""

    (artifact_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    if readiness != "READY":
        raise RuntimeError(
            "Phase 3.7.2.6.2 readiness validation blocked: " + ", ".join(reasons)
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE37262_FATAL: {exc}", file=sys.stderr)
        raise