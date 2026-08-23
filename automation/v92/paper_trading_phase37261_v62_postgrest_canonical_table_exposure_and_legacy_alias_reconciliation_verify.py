from __future__ import annotations
import json, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

CONTRACT="PHASE37261_V62_POSTGREST_CANONICAL_TABLE_EXPOSURE_AND_LEGACY_ALIAS_RECONCILIATION"
TABLE="paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
BROKER_ORDER_SUBMISSION_ENABLED=False
REAL_MONEY_TRADING_ENABLED=False
HISTORICAL_REWRITE_ALLOWED=False

def reqenv(n):
    v=os.getenv(n,"").strip()
    if not v: raise RuntimeError(f"Missing env: {n}")
    return v

def main():
    base=reqenv("SUPABASE_URL").rstrip("/")
    key=reqenv("SUPABASE_SERVICE_ROLE_KEY")
    target=f"/rest/v1/{TABLE}"
    url=f"{base}{target}?"+urllib.parse.urlencode({"select":"*","limit":"1"})
    req=urllib.request.Request(url,headers={"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json"})
    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1 V6.2")
    print("")
    print("## PostgREST Canonical Exposure + Legacy Alias Reconciliation")
    print("")
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Verification Date: `{datetime.now(timezone.utc).date().isoformat()}`")
    print(f"- Canonical Audit Table: `{TABLE}`")
    print(f"- Request Target: `{target}`")
    print("- Historical Rewrite Allowed: **NO**")
    print("")
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            status=r.getcode()
            body=r.read().decode("utf-8",errors="replace")
        rows=json.loads(body or "[]")
        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **PASS**")
        print(f"- HTTP Status: **{status}**")
        print("- Canonical Resolver: **LOCKED_TO_V92**")
        print("- PGRST205: **NOT_PRESENT**")
        print(f"- Rows Sampled: **{len(rows) if isinstance(rows,list) else 0}**")
        print("")
        print("## Safety Boundary")
        print("")
        print("- Paper only: **ENABLED**")
        print("- Broker order submission: **DISABLED**")
        print("- Real-money trading: **DISABLED**")
        print("- Historical evidence rewrite: **DISABLED**")
        return 0
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8",errors="replace")
        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **FAIL**")
        print(f"- HTTP Status: **{e.code}**")
        print(f"- Request Target: `{target}`")
        print("```json")
        print(body[:4000])
        print("```")
        raise RuntimeError(f"V6.2 verification failed: HTTP {e.code}: {body}") from e

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE37261_V62_FATAL: {exc}",file=sys.stderr)
        raise