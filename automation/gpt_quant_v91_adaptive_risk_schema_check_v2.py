#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
TABLE = "gpt_quant_v9_risk_portfolio_state"

def main():
    query = urllib.parse.urlencode({
        "select": "state_date",
        "order": "state_date.desc",
        "limit": "1",
    })
    url = f"{URL}/rest/v1/{TABLE}?{query}"
    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
    }

    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            rows = json.loads(raw) if raw else []
            print(json.dumps({
                "status": "PASS",
                "http_status": response.status,
                "table": TABLE,
                "reachable": True,
                "rows_returned": len(rows) if isinstance(rows, list) else None,
                "note": "0 rows is acceptable; schema/API reachability is the purpose of this check.",
            }, indent=2))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

if __name__ == "__main__":
    main()