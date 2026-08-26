from __future__ import annotations
import math, os
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Any
import requests

URL=os.environ.get("SUPABASE_URL","").rstrip("/")
KEY=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
ACCOUNT=os.environ.get("AUTOTRADER_ACCOUNT","paper-main")
if not URL or not KEY: raise SystemExit("Missing Supabase secrets")
H={"apikey":KEY,"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}
HR={**H,"Prefer":"return=representation"}
HU={**H,"Prefer":"resolution=merge-duplicates,return=representation"}
def u(t,q=""): return f"{URL}/rest/v1/{t}"+(f"?{q}" if q else "")
def get(t,q=""):
 r=requests.get(u(t,q),headers=H,timeout=45); r.raise_for_status(); return r.json()
def post(t,p):
 r=requests.post(u(t),headers=HR,json=p,timeout=45); r.raise_for_status(); return r.json()
def upsert(t,p,conflict):
 r=requests.post(u(t,f"on_conflict={quote(conflict)}"),headers=HU,json=p,timeout=45); r.raise_for_status(); return r.json()
def num(v,d=0.0):
 try:
  x=float(v); return x if math.isfinite(x) else d
 except: return d
def integer(v,d=0):
 try:return int(v)
 except:return d
def evalrow(day,stock,signal,price,decision,code,msg,qty=0,notional=0,order_id=None):
 payload={"account_name":ACCOUNT,"evaluation_date":day,"stock_id":stock.get("id"),"symbol":stock.get("symbol"),"name":stock.get("name"),"score":num(signal.get("total_score")),"risk_score":num(signal.get("risk_score")),"confidence":num(signal.get("confidence")),"reference_price":price,"decision":decision,"reason_code":code,"reason_message":msg,"proposed_quantity":qty,"proposed_notional":round(notional,2),"order_id":order_id}
 upsert("order_evaluations_v16",payload,"account_name,evaluation_date,symbol,reason_code")

cfgs=get("autotrader_configs_v13",f"account_name=eq.{quote(ACCOUNT)}&limit=1")
if not cfgs: raise SystemExit("No config")
cfg=cfgs[0]
if not cfg.get("enabled") or cfg.get("kill_switch") or cfg.get("mode")!="PAPER": raise SystemExit("Trader not enabled for PAPER")
acct=get("paper_accounts_v13",f"account_name=eq.{quote(ACCOUNT)}&limit=1")[0]
sigs=get("signals","select=stock_id,trade_date,strategy_version,total_score,trend_score,momentum_score,volume_score,risk_score,confidence&order=trade_date.desc,total_score.desc&limit=500")
if not sigs: raise SystemExit("No signals")
day=str(sigs[0]["trade_date"]); sigs=[s for s in sigs if str(s["trade_date"])==day]
stocks=get("stocks","select=id,symbol,name&limit=10000"); sm={str(s["id"]):s for s in stocks}
ids=sorted({str(s["stock_id"]) for s in sigs if s.get("stock_id") is not None})
prices=get("daily_prices",f"select=stock_id,trade_date,close&stock_id=in.({','.join(ids)})&order=trade_date.desc&limit=5000")
pm={}
for p in prices: pm.setdefault(str(p["stock_id"]),p)
positions=get("paper_positions_v13",f"account_name=eq.{quote(ACCOUNT)}&select=symbol&limit=1000")
held={str(x["symbol"]) for x in positions}
opens=get("trade_orders_v13",f"account_name=eq.{quote(ACCOUNT)}&status=in.(PROPOSED,APPROVED)&select=symbol,side&limit=1000")
blocked={str(x["symbol"]) for x in opens if x.get("side")=="BUY"}
# best signal per symbol
best={}
for s in sigs:
 st=sm.get(str(s.get("stock_id"))); pr=pm.get(str(s.get("stock_id")))
 if not st or not pr or not st.get("symbol"): continue
 sym=str(st["symbol"]); cur=best.get(sym)
 if cur is None or num(s.get("total_score"))>num(cur["signal"].get("total_score")): best[sym]={"stock":st,"price":pr,"signal":s}
min_score=num(cfg.get("min_score"),40); max_risk=num(cfg.get("max_risk_score"),60)
mode=str(cfg.get("selection_mode") or "STRICT").upper(); fallback_n=max(0,integer(cfg.get("fallback_top_n"),1)); fallback_risk=num(cfg.get("fallback_max_risk_score"),70)
accepted=[]; rejected=[]
for sym,item in best.items():
 st,pr,s=item["stock"],item["price"],item["signal"]; price=num(pr.get("close")); score=num(s.get("total_score")); risk=num(s.get("risk_score"),50)
 if sym in held: evalrow(day,st,s,price,"SKIPPED","ALREADY_HELD","Existing paper position"); continue
 if sym in blocked: evalrow(day,st,s,price,"SKIPPED","OPEN_BUY_EXISTS","Existing proposed/approved buy order"); continue
 if price<=0: evalrow(day,st,s,price,"REJECTED","NO_VALID_PRICE","No positive latest close"); continue
 reasons=[]
 if score<min_score: reasons.append(f"score {score:.2f} < {min_score:.2f}")
 if risk>max_risk: reasons.append(f"risk {risk:.2f} > {max_risk:.2f}")
 composite=score+0.15*num(s.get("confidence"),50)-0.20*risk
 if reasons: rejected.append((composite,sym,item,reasons)); evalrow(day,st,s,price,"REJECTED","STRICT_RISK_GATE","; ".join(reasons))
 else: accepted.append((composite,sym,item,"STRICT"))
# Explainable fallback: only when strict produced none and explicitly enabled
if not accepted and mode=="FALLBACK_TOP_N" and fallback_n>0:
 for comp,sym,item,reasons in sorted(rejected,key=lambda x:x[0],reverse=True):
  if len(accepted)>=fallback_n: break
  risk=num(item["signal"].get("risk_score"),50)
  if risk<=fallback_risk:
   accepted.append((comp,sym,item,"FALLBACK")); evalrow(day,item["stock"],item["signal"],num(item["price"].get("close")),"ACCEPTED","FALLBACK_TOP_N",f"Fallback accepted; strict reasons: {'; '.join(reasons)}")
slots=max(0,integer(cfg.get("max_positions"),5)-len(held)-len(blocked)); limit=min(slots,integer(cfg.get("max_daily_orders"),5))
cash=num(acct.get("cash")); equity=num(acct.get("equity"),cash); invest=max(0,cash-equity*num(cfg.get("reserve_cash_pct"),30)/100); cap=equity*num(cfg.get("max_position_pct"),15)/100; lot=max(1,integer(cfg.get("lot_size"),1)); rate=num(cfg.get("commission_rate"),0.001425)
created=[]
for idx,(_,sym,item,source) in enumerate(sorted(accepted,key=lambda x:x[0],reverse=True)[:limit]):
 remaining=max(1,limit-idx); budget=min(cap,invest/remaining); price=num(item["price"].get("close")); qty=(math.floor(budget/price)//lot)*lot
 if qty<=0: evalrow(day,item["stock"],item["signal"],price,"REJECTED","INSUFFICIENT_BUDGET",f"budget={budget:.2f}"); continue
 gross=qty*price; fee=max(1,gross*rate)
 if gross+fee>invest: evalrow(day,item["stock"],item["signal"],price,"REJECTED","INSUFFICIENT_CASH",f"required={gross+fee:.2f}, investable={invest:.2f}"); continue
 key=f"{ACCOUNT}:{day}:{sym}:BUY:ENTRY_SIGNAL_V16"
 if get("trade_orders_v13",f"idempotency_key=eq.{quote(key)}&select=id&limit=1"): continue
 payload={"account_name":ACCOUNT,"symbol":sym,"side":"BUY","quantity":qty,"reference_price":round(price,2),"notional":round(gross,2),"score":num(item["signal"].get("total_score")),"risk_score":num(item["signal"].get("risk_score"),50),"confidence":num(item["signal"].get("confidence"),50),"reason":f"ENTRY_SIGNAL_V16_{source}","mode":"PAPER","status":"PROPOSED","signal_date":day,"execution_date":day,"idempotency_key":key}
 row=post("trade_orders_v13",payload)[0]; created.append(row); evalrow(day,item["stock"],item["signal"],price,"ACCEPTED","ORDER_CREATED",f"source={source}",qty,gross,row["id"]); invest=max(0,invest-gross-fee)
print(f"V16 complete date={day} strict_accepted={sum(1 for x in accepted if x[3]=='STRICT')} fallback_accepted={sum(1 for x in accepted if x[3]=='FALLBACK')} created={len(created)}")
# Phase 3.7.18.3 compatibility entrypoint.
#
# This module is a legacy top-level executable: its V16 order-generation work
# runs when the module is executed/imported. Enterprise 3.0 Stable dynamically
# loads the module and then requires a callable main(). The missing callable
# caused the orchestrator to mark V16_ORDERS failed after the legacy body had
# already completed. This no-op entrypoint intentionally does not re-run the
# order-generation body; it only satisfies the orchestrator contract.
def main() -> None:
    return None
