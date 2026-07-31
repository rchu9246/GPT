from __future__ import annotations
import math, os
from typing import Any
from urllib.parse import quote
import requests
URL=os.environ.get('SUPABASE_URL','').rstrip('/')
KEY=os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')
ACCOUNT=os.environ.get('AUTOTRADER_ACCOUNT','paper-main')
if not URL or not KEY: raise SystemExit('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY')
H={'apikey':KEY,'Authorization':f'Bearer {KEY}','Content-Type':'application/json'}
RH={**H,'Prefer':'return=representation'}
def u(t,q=''): return f"{URL}/rest/v1/{t}"+(f"?{q}" if q else '')
def get(t,q=''):
 r=requests.get(u(t,q),headers=H,timeout=45); r.raise_for_status(); return r.json()
def post(t,p):
 r=requests.post(u(t),headers=RH,json=p,timeout=45); r.raise_for_status(); return r.json()
def num(v,d=0.0):
 try:
  x=float(v); return x if math.isfinite(x) else d
 except: return d
def integer(v,d=0):
 try: return int(v)
 except: return d
cfgs=get('autotrader_configs_v13',f'account_name=eq.{quote(ACCOUNT)}&limit=1')
if not cfgs: raise SystemExit('No autotrader configuration found')
cfg=cfgs[0]
if not cfg.get('enabled'): raise SystemExit('Autotrader is disabled')
if cfg.get('kill_switch'): raise SystemExit('Kill switch is enabled')
if cfg.get('mode')!='PAPER': raise SystemExit('Only PAPER mode supported')
accounts=get('paper_accounts_v13',f'account_name=eq.{quote(ACCOUNT)}&limit=1')
if not accounts: raise SystemExit('No paper account found')
acct=accounts[0]
sigs=get('signals','select=stock_id,trade_date,strategy_version,total_score,trend_score,momentum_score,volume_score,risk_score,confidence&order=trade_date.desc,total_score.desc&limit=500')
if not sigs: raise SystemExit('No signals available')
latest=str(sigs[0]['trade_date']); sigs=[s for s in sigs if str(s['trade_date'])==latest]
stocks=get('stocks','select=id,symbol,name&limit=10000'); sbid={str(s['id']):s for s in stocks}
ids=sorted({str(s['stock_id']) for s in sigs if s.get('stock_id') is not None})
prices=get('daily_prices',f"select=stock_id,trade_date,close&stock_id=in.({','.join(ids)})&order=trade_date.desc&limit=5000")
latestp={}
for p in prices:
 latestp.setdefault(str(p['stock_id']),p)
positions=get('paper_positions_v13',f'account_name=eq.{quote(ACCOUNT)}&select=symbol&limit=1000')
held={str(x['symbol']) for x in positions}
openo=get('trade_orders_v13',f'account_name=eq.{quote(ACCOUNT)}&status=in.(PROPOSED,APPROVED)&select=symbol,side&limit=1000')
blocked={str(x['symbol']) for x in openo if x.get('side')=='BUY'}
by={}
for s in sigs:
 st=sbid.get(str(s.get('stock_id'))); pr=latestp.get(str(s.get('stock_id')))
 if not st or not pr or not st.get('symbol'): continue
 sym=str(st['symbol'])
 if sym not in by or num(s.get('total_score'))>num(by[sym]['signal'].get('total_score')): by[sym]={'stock':st,'price':pr,'signal':s}
min_score=num(cfg.get('min_score'),40); max_risk=num(cfg.get('max_risk_score'),60)
max_positions=integer(cfg.get('max_positions'),5); max_daily=integer(cfg.get('max_daily_orders'),5)
max_pct=num(cfg.get('max_position_pct'),15)/100; reserve_pct=num(cfg.get('reserve_cash_pct'),30)/100
lot=max(1,integer(cfg.get('lot_size'),1)); comm=num(cfg.get('commission_rate'),0.001425)
slots=max(0,max_positions-len(held)-len(blocked)); max_new=min(slots,max_daily)
cash=num(acct.get('cash')); equity=num(acct.get('equity'),cash); invest=max(0,cash-equity*reserve_pct); max_notional=equity*max_pct
cands=[]
for sym,item in by.items():
 if sym in held or sym in blocked: continue
 s=item['signal']; score=num(s.get('total_score')); risk=num(s.get('risk_score'),50); conf=num(s.get('confidence'),50); close=num(item['price'].get('close'))
 if score<min_score or risk>max_risk or close<=0: continue
 cands.append((score+0.15*conf-0.20*risk,sym,item))
cands.sort(reverse=True,key=lambda x:x[0]); created=[]
for i,(_,sym,item) in enumerate(cands[:max_new]):
 remain=max(1,max_new-i); budget=min(max_notional,invest/remain); price=num(item['price']['close']); raw=math.floor(budget/price); qty=(raw//lot)*lot
 if qty<=0: continue
 gross=qty*price; fee=max(1.0,gross*comm)
 if gross+fee>invest: continue
 s=item['signal']; key=f'{ACCOUNT}:{latest}:{sym}:BUY:ENTRY_SIGNAL_V15'
 if get('trade_orders_v13',f'idempotency_key=eq.{quote(key)}&select=id&limit=1'): continue
 payload={'account_name':ACCOUNT,'symbol':sym,'side':'BUY','quantity':qty,'reference_price':round(price,2),'notional':round(gross,2),'score':num(s.get('total_score')),'risk_score':num(s.get('risk_score'),50),'confidence':num(s.get('confidence'),50),'reason':'ENTRY_SIGNAL_V15','mode':'PAPER','status':'PROPOSED','signal_date':latest,'execution_date':latest,'idempotency_key':key}
 created.append(post('trade_orders_v13',payload)[0]); invest=max(0,invest-gross-fee)
print(f'V15 order generation complete: date={latest}, candidates={len(cands)}, created={len(created)}')
for r in created: print(f"PROPOSED {r['symbol']} x {r['quantity']} @ {r['reference_price']}")
