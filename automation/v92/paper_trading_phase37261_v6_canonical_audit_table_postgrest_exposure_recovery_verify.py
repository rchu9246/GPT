#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CONTRACT = "PHASE37261_V6_CANONICAL_AUDIT_TABLE_POSTGREST_EXPOSURE_RECOVERY"
CANONICAL_AUDIT_TABLE = "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"

BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
HISTORICAL_REWRITE_ALLOWED = False


def require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    supabase_url = require("SUPABASE_URL").rstrip("/")
    service_key = require("SUPABASE_SERVICE_ROLE_KEY")

    query = urllib.parse.urlencode({
        "select": "id,reconstruction_date,portfolio_id,activation_state,master_cycle_state,runtime_supervision_state",
        "limit": "1",
    })

    target = f"/rest/v1/{CANONICAL_AUDIT_TABLE}"
    url = f"{supabase_url}{target}?{query}"

    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
        },
    )

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1 V6")
    print("")
    print("## Canonical Audit Table PostgREST Exposure Recovery")
    print("")
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Verification Date: `{datetime.now(timezone.utc).date().isoformat()}`")
    print(f"- Resolved Audit Table: `{CANONICAL_AUDIT_TABLE}`")
    print(f"- PostgREST Request Target: `{target}`")
    print("- Verification Mode: **READ_ONLY**")
    print("- Historical Rewrite Allowed: **NO**")
    print("")

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="replace")

        if not (200 <= status < 300):
            raise RuntimeError(f"Unexpected HTTP status: {status}")

        rows = json.loads(body or "[]")
        if not isinstance(rows, list):
            raise RuntimeError("Canonical audit endpoint did not return a JSON array")

        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **PASS**")
        print(f"- HTTP Status: **{status}**")
        print("- Canonical Resolver: **LOCKED_TO_V92**")
        print("- PGRST205: **NOT_PRESENT**")
        print(f"- Rows Sampled: **{len(rows)}**")
        print("")
        print("## Safety Boundary")
        print("")
        print("- Paper only: **ENABLED**")
        print("- Broker API used: **NO**")
        print("- Broker credentials used: **NO**")
        print("- Broker order submission: **DISABLED**")
        print("- Real-money trading: **DISABLED**")
        print("- Live-money release authorized: **NO**")
        print("- Historical evidence rewrite: **DISABLED**")
        return 0

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **FAIL**")
        print(f"- HTTP Status: **{exc.code}**")
        print(f"- Resolved Audit Table: `{CANONICAL_AUDIT_TABLE}`")
        print(f"- Actual Request Target: `{target}`")
        print("")
        print("```json")
        print(body[:4000])
        print("```")
        raise RuntimeError(
            f"Canonical audit table exposure verification failed: HTTP {exc.code}: {body}"
        ) from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE37261_V6_FATAL: {exc}", file=sys.stderr)
        raise