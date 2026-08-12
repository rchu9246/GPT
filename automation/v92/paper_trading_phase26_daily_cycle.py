#!/usr/bin/env python3
import json,os,subprocess,sys,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; URL=os.environ["SUPABASE_URL"].rstrip("/"); KEY=os.environ["SUPABASE_SERVICE_ROLE_KEY"]
VER=os.getenv("PAPER_STRATEGY_VERSION","V9.1"); MODE="SHADOW_ONLY_NO_BROKER"; DATE=datetime.now(timezone.utc).astimezone().date().isoformat(); RUN_KEY=f"{DATE}-{VER}"
def rest(method,table,query="",payload=None,prefer=None):
 u=f"{URL}/rest/v1/{table}"+(("?"+query) if query else ""); h={"apikey":KEY,"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}
 if prefer:h["Prefer"]=prefer
 req=urllib.request.Request(u,data=None if payload is None else json.dumps(payload).encode(),headers=h,method=method)
 try:
  with urllib.request.urlopen(req,timeout=30) as r:
   s=r.read().decode(); return json.loads(s) if s else None
 except urllib.error.HTTPError as e: raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')}")
def last_json(path):
 s=path.read_text(encoding="utf-8",errors="replace") if path.exists() else ""; d=json.JSONDecoder(); out=[]
 for i,c in enumerate(s):
  if c in "[{":
   try:
    x,_=d.raw_decode(s[i:])
    if isinstance(x,(dict,list)):out.append(x)
   except:pass
 return out[-1] if out else {}
def main():
 p=subprocess.run([sys.executable,str(ROOT/"automation/v92/paper_trading_phase25_orchestrator.py")],cwd=ROOT,env=os.environ.copy())
 if p.returncode: return p.returncode
 p25=json.loads((ROOT/"phase25_result.json").read_text(encoding="utf-8")); p21=last_json(ROOT/"phase25_logs/phase2_1.log"); p23=last_json(ROOT/"phase25_logs/phase2_3.log"); p24=last_json(ROOT/"phase25_logs/phase2_4.log")
 st={x.get("phase"):x.get("status") for x in p25.get("phases",[])}
 x={"run_key":RUN_KEY,"run_date":DATE,"strategy_version":VER,"mode":MODE,"status":p25.get("status"),"pipeline_status":p25.get("pipeline"),
 "phase22_status":st.get("2.2"),"phase21_status":st.get("2.1"),"phase23_status":st.get("2.3"),"phase24_status":st.get("2.4"),
 "latest_market_date":(p21.get("market_data") or {}).get("latest_market_date"),"signals_eligible":(p21.get("signal_engine") or {}).get("signals_eligible",0),
 "top_symbol":(p21.get("signal_engine") or {}).get("top_symbol"),"top_score":(p21.get("signal_engine") or {}).get("top_score"),
 "orders_created":p23.get("orders_created",0),"positions_open":p24.get("positions_open",0),"cash":p24.get("ending_cash",0),
 "market_value":p24.get("ending_market_value",0),"equity":p24.get("ending_equity",0),"realized_pnl":p24.get("realized_pnl_today",0),
 "unrealized_pnl":p24.get("unrealized_pnl",0),"positions":p24.get("decisions",[]),"top_candidates":p21.get("top_candidates",[]),
 "raw_summary":{"phase25":p25,"phase21":p21,"phase23":p23,"phase24":p24},"completed_at":datetime.now(timezone.utc).isoformat()}
 q=urllib.parse.urlencode({"on_conflict":"run_key"}); rest("POST","gptq_paper_daily_snapshots",q,x,"resolution=merge-duplicates,return=representation")
 (ROOT/"phase26_result.json").write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
 md=f"""# GPT Quant V9.2 Phase 2.6
- status: **{x['status']}**
- pipeline: **{x['pipeline_status']}**
- equity: **{x['equity']}**
- cash: **{x['cash']}**
- market value: **{x['market_value']}**
- positions: **{x['positions_open']}**

| Stage | Status |
|---|---|
| 2.2 Market Data | {x['phase22_status']} |
| 2.1 Signal Generation | {x['phase21_status']} |
| 2.3 Signal Execution | {x['phase23_status']} |
| 2.4 Position Management | {x['phase24_status']} |
"""
 (ROOT/"phase26_summary.md").write_text(md,encoding="utf-8"); print(json.dumps(x,ensure_ascii=False,indent=2))
 return 0 if x["status"]=="COMPLETED" and x["pipeline_status"]=="COMPLETED" else 1
if __name__=="__main__":raise SystemExit(main())
