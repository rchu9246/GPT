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

CONTRACT = "PHASE3727_PRODUCTION_PAPER_GO_LIVE"

ACTIVATION_TABLE = "paper_post_recovery_activation_state_v92"
MASTER_CYCLE_TABLE = "paper_post_recovery_master_cycle_v92"
SUPERVISION_TABLE = "paper_runtime_supervision_state_v92"
RECONSTRUCTION_AUDIT_TABLE = "phase37261_reconstruction_audit_v92"

AUTHORIZED_GATE_STATE = "AUTHORIZED_PAPER_CONTINUATION"

BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
HISTORICAL_REWRITE_ALLOWED = False
PAPER_TRADING_ENABLED = True
DATA_COLLECTION_ENABLED = True
RUNTIME_SUPERVISION_ENABLED = True

BLOCK_STATES = {"REVOKED", "FAIL_CLOSED", "BLOCKED", "HALTED", "SUSPENDED"}


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


def first(row: dict[str, Any] | None, names: tuple[str, ...], default: Any = None) -> Any:
    if not row:
        return default
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def state(row: dict[str, Any] | None, names: tuple[str, ...]) -> str:
    value = first(row, names, "")
    return str(value).strip().upper() if value is not None else ""


def latest(
    sb: SupabaseREST,
    table: str,
    portfolio_id: str,
    order_columns: tuple[str, ...],
) -> dict[str, Any] | None:
    for col in order_columns:
        params = {
            "select": "*",
            "portfolio_id": f"eq.{portfolio_id}",
            "order": f"{col}.desc",
            "limit": "1",
        }
        try:
            rows = sb.get(table, params)
            if rows:
                return rows[0]
        except RuntimeError as exc:
            msg = str(exc)
            if "PGRST204" not in msg and "42703" not in msg:
                raise

    for col in order_columns:
        params = {"select": "*", "order": f"{col}.desc", "limit": "1"}
        try:
            rows = sb.get(table, params)
            if rows:
                return rows[0]
        except RuntimeError as exc:
            msg = str(exc)
            if "PGRST204" not in msg and "42703" not in msg:
                raise

    rows = sb.get(table, {"select": "*", "limit": "1"})
    return rows[0] if rows else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default="V92_PRODUCTION_PAPER_V91")
    parser.add_argument("--strategy-version", default="V9.1")
    args = parser.parse_args()

    sb = SupabaseREST(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"))

    activation = latest(
        sb, ACTIVATION_TABLE, args.portfolio_id,
        ("activation_date", "state_date", "created_at", "updated_at"),
    )
    master = latest(
        sb, MASTER_CYCLE_TABLE, args.portfolio_id,
        ("cycle_date", "master_cycle_date", "created_at", "updated_at"),
    )
    supervision = latest(
        sb, SUPERVISION_TABLE, args.portfolio_id,
        ("supervision_date", "state_date", "created_at", "updated_at"),
    )
    reconstruction = latest(
        sb, RECONSTRUCTION_AUDIT_TABLE, args.portfolio_id,
        ("reconstruction_date", "created_at"),
    )

    activation_state = state(activation, ("activation_state", "state", "status"))
    master_state = state(master, ("master_cycle_state", "cycle_state", "state", "status"))
    supervision_state = state(supervision, ("supervision_state", "runtime_supervision", "state", "status"))
    reconstruction_state = state(reconstruction, ("reconstruction_state", "state", "status"))

    activation_ok = bool(activation) and activation_state == "ACTIVE"
    master_ok = bool(master) and master_state not in BLOCK_STATES
    supervision_ok = bool(supervision) and supervision_state not in BLOCK_STATES
    reconstruction_ok = bool(reconstruction) and reconstruction_state not in BLOCK_STATES
    if reconstruction and not reconstruction_state:
        reconstruction_ok = True

    reasons: list[str] = []
    if not activation_ok:
        reasons.append(f"ACTIVATION_NOT_READY:{activation_state or 'MISSING'}")
    if not master_ok:
        reasons.append(f"MASTER_CYCLE_NOT_READY:{master_state or 'MISSING'}")
    if not supervision_ok:
        reasons.append(f"SUPERVISION_NOT_READY:{supervision_state or 'MISSING'}")
    if not reconstruction_ok:
        reasons.append(f"RECONSTRUCTION_NOT_READY:{reconstruction_state or 'MISSING'}")

    go_live_state = "GO_LIVE_PAPER_ACTIVE" if not reasons else "BLOCKED_FAIL_CLOSED"

    now = datetime.now(timezone.utc)
    artifact_dir = Path("artifacts/phase3727")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    evidence = {
        "contract": CONTRACT,
        "go_live_state": go_live_state,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "run_time_utc": now.isoformat(),
        "runtime": {
            "paper_trading_enabled": PAPER_TRADING_ENABLED,
            "data_collection_enabled": DATA_COLLECTION_ENABLED,
            "runtime_supervision_enabled": RUNTIME_SUPERVISION_ENABLED,
        },
        "canonical": {
            "activation_state": activation_state,
            "master_cycle_state": master_state,
            "runtime_supervision_state": supervision_state,
            "reconstruction_state": reconstruction_state,
        },
        "reasons": reasons,
        "safety": {
            "broker_api_used": BROKER_API_USED,
            "broker_credentials_used": BROKER_CREDENTIALS_USED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
            "live_money_release_authorized": LIVE_MONEY_RELEASE_AUTHORIZED,
            "historical_rewrite_allowed": HISTORICAL_REWRITE_ALLOWED,
        },
    }

    (artifact_dir / "verification.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = f"""# GPT Quant V9.2 Paper Trading - Phase 3.7.2.7

## Production Paper Go-Live

- Contract: `{CONTRACT}`
- Portfolio ID: `{args.portfolio_id}`
- Strategy Version: `{args.strategy_version}`
- Run Date: `{now.date().isoformat()}`
- Go-Live State: **{go_live_state}**

## Runtime Mode

- Paper Trading: **{'ENABLED' if PAPER_TRADING_ENABLED else 'DISABLED'}**
- Data Collection: **{'ENABLED' if DATA_COLLECTION_ENABLED else 'DISABLED'}**
- Runtime Supervision: **{'ENABLED' if RUNTIME_SUPERVISION_ENABLED else 'DISABLED'}**

## Canonical Runtime Inputs

- Activation State: **{activation_state or 'UNKNOWN'}**
- Activation Validation: **{'PASS' if activation_ok else 'FAIL'}**

- Master Cycle State: **{master_state or 'UNKNOWN'}**
- Master Cycle Validation: **{'PASS' if master_ok else 'FAIL'}**

- Runtime Supervision State: **{supervision_state or 'UNKNOWN'}**
- Runtime Supervision Validation: **{'PASS' if supervision_ok else 'FAIL'}**

- Reconstruction State: **{reconstruction_state or 'UNKNOWN'}**
- Reconstruction Validation: **{'PASS' if reconstruction_ok else 'FAIL'}**

## Go-Live Reasons

{chr(10).join(f'- `{reason}`' for reason in reasons) if reasons else '- `NONE`'}

## Safety Boundary

- Broker API used: **NO**
- Broker credentials used: **NO**
- Broker order submission: **DISABLED**
- Real-money trading: **DISABLED**
- Live-money release authorized: **NO**
- Historical rewrite allowed: **NO**

> Production Paper is live only in simulated/paper mode.
> Real-money promotion authority is **NOT PRESENT IN THIS PHASE**.
"""

    (artifact_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    if go_live_state != "GO_LIVE_PAPER_ACTIVE":
        raise RuntimeError("Phase 3.7.2.7 Go-Live blocked: " + ", ".join(reasons))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3727_FATAL: {exc}", file=sys.stderr)
        raise