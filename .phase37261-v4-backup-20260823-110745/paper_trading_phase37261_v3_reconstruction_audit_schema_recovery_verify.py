from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TABLE = "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
CONTRACT = "PHASE37261_V3_RECONSTRUCTION_AUDIT_SCHEMA_RECOVERY"

def env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""

def main() -> int:
    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL").rstrip("/")
    key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )

    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    endpoint = (
        f"{url}/rest/v1/{TABLE}"
        "?select=id,reconstruction_date,portfolio_id,activation_state,"
        "master_cycle_state,runtime_supervision_state"
        "&limit=1"
    )

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    req = urllib.request.Request(endpoint, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8")
            rows = json.loads(body) if body.strip() else []
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Canonical audit table is not visible through PostgREST: "
            f"HTTP {exc.code}: {body}"
        ) from exc

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1 V3")
    print()
    print("## Reconstruction Audit Schema Recovery Verification")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Canonical Audit Table: `{TABLE}`")
    print("- PostgREST Schema Visibility: **PASS**")
    print(f"- Existing Rows Sampled: **{len(rows)}**")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Historical evidence rewrite: **DISABLED**")
    print("- Fail-closed policy: **ENABLED**")
    print()
    print("## Next")
    print()
    print("- Re-run **Phase 3.7.2.6.1**.")
    print("- If reconstruction = PASS, then re-run **Phase 3.7.2.6**.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE37261_V3_FATAL: {exc}", file=sys.stderr)
        raise