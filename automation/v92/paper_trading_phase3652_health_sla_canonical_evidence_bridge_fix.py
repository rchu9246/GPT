from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE3652_HEALTH_SLA_CANONICAL_EVIDENCE_BRIDGE_FIX"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"

def env_first(*names: str) -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return ""

class SB:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def get(self, table: str, query: str) -> List[Dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/{table}?{query}"
        req = urllib.request.Request(
            endpoint,
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8")
                data = json.loads(body) if body.strip() else []
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc

def latest(sb: SB, table: str, portfolio_id: str, order_col: str) -> Optional[Dict[str, Any]]:
    q = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_col}.desc&limit=1"
    )
    rows = sb.get(table, q)
    return rows[0] if rows else None

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    args = ap.parse_args()

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = SB(url, key)

    health = latest(sb, "paper_system_health_v92", args.portfolio_id, "health_date")
    sla = latest(sb, "paper_observability_daily_v92", args.portfolio_id, "observation_date")

    health_alias = latest(sb, "paper_health_monitoring_v92", args.portfolio_id, "health_date")
    sla_alias = latest(sb, "paper_observability_sla_v92", args.portfolio_id, "sla_date")

    result = {
        "contract": CONTRACT,
        "portfolio_id": args.portfolio_id,
        "canonical_health_found": health is not None,
        "canonical_health_state": (health or {}).get("health_status"),
        "canonical_health_score": (health or {}).get("health_score"),
        "compat_health_found": health_alias is not None,
        "canonical_sla_found": sla is not None,
        "canonical_sla_state": (sla or {}).get("sla_status"),
        "canonical_sla_score": (sla or {}).get("sla_score"),
        "compat_sla_found": sla_alias is not None,
        "bridge_status": "PASS",
        "paper_only": True,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
    }

    if health is None or sla is None:
        result["bridge_status"] = "FAIL_CLOSED"

    if health_alias is None or sla_alias is None:
        result["bridge_status"] = "FAIL_CLOSED"

    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.5.2")
    print()
    print("## Health + SLA Canonical Evidence Bridge Fix")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Canonical Health Found: **{'YES' if result['canonical_health_found'] else 'NO'}**")
    print(f"- Canonical Health: `{result['canonical_health_state']}` / `{result['canonical_health_score']}`")
    print(f"- Compatibility Health Bridge: **{'PASS' if result['compat_health_found'] else 'MISSING'}**")
    print(f"- Canonical SLA Found: **{'YES' if result['canonical_sla_found'] else 'NO'}**")
    print(f"- Canonical SLA: `{result['canonical_sla_state']}` / `{result['canonical_sla_score']}`")
    print(f"- Compatibility SLA Bridge: **{'PASS' if result['compat_sla_found'] else 'MISSING'}**")
    print(f"- Bridge Status: **{result['bridge_status']}**")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase3652")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "bridge_evidence.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return 0 if result["bridge_status"] == "PASS" else 1

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3652_FATAL: {exc}", file=sys.stderr)
        raise