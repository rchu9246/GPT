#!/usr/bin/env python3
"""
GPT Quant V9.2
Phase 3.7.2.6.1 V5
PostgREST Canonical Audit Table Resolution Verification

Safety:
- read-only verification
- no historical rewrite
- no broker API
- no order submission
- no real-money trading
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CONTRACT = "PHASE37261_V5_POSTGREST_CANONICAL_AUDIT_TABLE_RESOLUTION_FIX"
CANONICAL_AUDIT_TABLE = (
    "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
)
LEGACY_AUDIT_TABLE = (
    "paper_post_recovery_activation_master_cycle_reconstruction_audit"
)

BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
HISTORICAL_REWRITE_ALLOWED = False


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    supabase_url = required_env("SUPABASE_URL").rstrip("/")
    service_key = required_env("SUPABASE_SERVICE_ROLE_KEY")

    # IMPORTANT:
    # The URL is built ONLY from CANONICAL_AUDIT_TABLE.
    # No legacy alias, fallback, inference, or alternate resolver is permitted.
    query = urllib.parse.urlencode({
        "select": "*",
        "limit": "1",
    })
    request_url = (
        f"{supabase_url}/rest/v1/{CANONICAL_AUDIT_TABLE}?{query}"
    )

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1 V5")
    print("")
    print("## PostgREST Canonical Audit Table Resolution")
    print("")
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Verification Date: `{datetime.now(timezone.utc).date().isoformat()}`")
    print(f"- Resolved Audit Table: `{CANONICAL_AUDIT_TABLE}`")
    print(f"- Legacy Audit Table Allowed: **NO**")
    print(
        "- PostgREST Request Target: "
        f"`/rest/v1/{CANONICAL_AUDIT_TABLE}`"
    )
    print("- Verification Mode: **READ_ONLY**")
    print("- Historical Rewrite Allowed: **NO**")
    print("")

    if CANONICAL_AUDIT_TABLE == LEGACY_AUDIT_TABLE:
        raise RuntimeError("Canonical table unexpectedly equals legacy table.")

    req = urllib.request.Request(
        request_url,
        headers=headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.getcode()

        if status < 200 or status >= 300:
            raise RuntimeError(f"Unexpected PostgREST HTTP status: {status}")

        try:
            rows = json.loads(body or "[]")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"PostgREST returned non-JSON response: {body[:500]}"
            ) from exc

        if not isinstance(rows, list):
            raise RuntimeError(
                "PostgREST canonical audit response was not a JSON array."
            )

        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **PASS**")
        print(f"- HTTP Status: **{status}**")
        print(f"- Canonical Rows Sampled: **{len(rows)}**")
        print("- Canonical Resolver: **LOCKED_TO_V92**")
        print("- PGRST205: **NOT_PRESENT**")
        print("")
        print("## Safety Boundary")
        print("")
        print("- Broker API Used: **NO**")
        print("- Broker Credentials Used: **NO**")
        print("- Broker Order Submission: **DISABLED**")
        print("- Real-money Trading: **DISABLED**")
        print("- Live-money Release Authorized: **NO**")
        return 0

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **FAIL**")
        print(f"- HTTP Status: **{exc.code}**")
        print(f"- Resolved Audit Table: `{CANONICAL_AUDIT_TABLE}`")
        print(
            "- Actual Request Target: "
            f"`/rest/v1/{CANONICAL_AUDIT_TABLE}`"
        )
        print("")
        print("```json")
        print(body[:4000])
        print("```")
        raise RuntimeError(
            "Canonical _v92 audit table is not visible through PostgREST: "
            f"HTTP {exc.code}: {body}"
        ) from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print(f"PHASE37261_V5_FATAL: {exc}", file=sys.stderr)
        raise