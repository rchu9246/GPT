"""GPT Quant V13 server-side PAPER trader.

Security properties:
- Uses SUPABASE_SERVICE_ROLE_KEY only on GitHub Actions/local server.
- Never performs live broker orders.
- Exits unless config.enabled=true, mode=PAPER and kill_switch=false.
"""
from __future__ import annotations
import os, sys, math, requests
from datetime import datetime, timezone

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")

if not URL or not KEY:
    raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

def get(table: str, query: str = ""):
    r = requests.get(f"{URL}/rest/v1/{table}?{query}", headers=HEADERS, timeout=30)
    r.raise_for_status(); return r.json()

def post(table: str, payload):
    r = requests.post(f"{URL}/rest/v1/{table}", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status(); return r.json()

def patch(table: str, query: str, payload):
    r = requests.patch(f"{URL}/rest/v1/{table}?{query}", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status(); return r.json()

def main():
    configs = get("autotrader_configs_v13", f"account_name=eq.{ACCOUNT}&limit=1")
    if not configs:
        print("No config; run migration and create config first."); return
    c = configs[0]
    if not c.get("enabled") or c.get("kill_switch") or c.get("mode") != "PAPER":
        print("Trader disabled/locked by config."); return

    signals = get("signals", "select=stock_id,trade_date,total_score,risk_score,confidence&order=trade_date.desc,total_score.desc&limit=100")
    stocks = get("stocks", "select=id,symbol,name&limit=5000")
    stock_map = {str(s["id"]): s for s in stocks}
    if not signals: return
    latest = signals[0]["trade_date"]
    positions = get("paper_positions_v13", f"account_name=eq.{ACCOUNT}&select=symbol,quantity,average_price")
    owned = {p["symbol"] for p in positions}
    slots = max(0, int(c["max_positions"]) - len(owned))
    candidates = []
    for row in signals:
        if row["trade_date"] != latest: continue
        stock = stock_map.get(str(row.get("stock_id")))
        if not stock or stock["symbol"] in owned: continue
        score = float(row.get("total_score") or 0); risk = float(row.get("risk_score") or 50)
        if score < float(c["min_score"]) or risk > float(c["max_risk_score"]): continue
        candidates.append((row, stock, score, risk))
    candidates = candidates[:slots]
    max_notional = float(c["starting_cash"]) * float(c["max_position_pct"]) / 100
    orders = []
    for row, stock, score, risk in candidates:
        price = round(max(10, score * 2.2 + float(row.get("confidence") or 50) * 0.8), 2)
        quantity = max(1, math.floor(max_notional / price))
        status = "PROPOSED" if c.get("require_approval") else "APPROVED"
        orders.append({"account_name": ACCOUNT, "symbol": stock["symbol"], "side": "BUY", "quantity": quantity, "reference_price": price, "notional": round(quantity*price,2), "score": score, "risk_score": risk, "confidence": float(row.get("confidence") or 50), "reason": f"V13 paper signal {latest}", "mode": "PAPER", "status": status})
    if orders:
        post("trade_orders_v13", orders)
        print(f"Created {len(orders)} paper orders.")
    else:
        print("No eligible orders.")

if __name__ == "__main__": main()
