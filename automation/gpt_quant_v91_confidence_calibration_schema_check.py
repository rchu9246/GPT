#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
TABLE = "gpt_quant_v91_confidence_calibration"

def request(method, query="", payload=None, prefer=None):
    url = f"{URL}/rest/v1/{TABLE}"
    if query:
        url += "?" + query
    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

def main():
    status, rows = request(
        "GET",
        urllib.parse.urlencode({
            "select": "ranking_id",
            "limit": "1",
        })
    )
    print(json.dumps({
        "status": "PASS",
        "http_status": status,
        "table": TABLE,
        "reachable": True,
        "sample_rows": len(rows) if isinstance(rows, list) else None,
    }, indent=2))

if __name__ == "__main__":
    main()