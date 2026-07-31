from __future__ import annotations
import os
from datetime import datetime, timezone
from urllib.parse import quote
import requests

url = os.environ.get("SUPABASE_URL", "").rstrip("/")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
order_id = os.environ.get("ORDER_ID", "").strip()
action = os.environ.get("ORDER_ACTION", "").strip().upper()

if not url or not key:
    raise SystemExit("Missing Supabase secrets")
if not order_id:
    raise SystemExit("Missing ORDER_ID")
if action not in {"APPROVE", "REJECT"}:
    raise SystemExit("ORDER_ACTION must be APPROVE or REJECT")

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}
payload = {"status": "APPROVED" if action == "APPROVE" else "REJECTED"}
if action == "APPROVE":
    payload["approved_at"] = datetime.now(timezone.utc).isoformat()

response = requests.patch(
    f"{url}/rest/v1/trade_orders_v13?id=eq.{quote(order_id)}"
    "&mode=eq.PAPER&status=eq.PROPOSED",
    headers=headers,
    json=payload,
    timeout=45,
)
response.raise_for_status()
rows = response.json()
if not rows:
    raise SystemExit("No matching PROPOSED PAPER order")
print(f"{action}: {rows[0]['id']} {rows[0]['symbol']}")
