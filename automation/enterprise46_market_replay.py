from __future__ import annotations
import math,os
from datetime import date
from typing import Any
from enterprise2.client import SupabaseRestClient
RUN_DATE=os.environ.get("QUANT_RUN_DATE",date.today().isoformat())
def n(v:Any,d:float=0.0)->float:
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d
def latest(c,t,f,where=""):
    q=f"{where}&order={f}.desc&limit=1" if where else f"order={f}.desc&limit=1"
    r=c.get(t,q); return r[0] if r else {}
def clamp(x,a=0.0,b=100.0): return max(a,min(b,x))

def main():
 c=SupabaseRestClient(); ps=c.get("enterprise_portfolios_v40","lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100"); reg=latest(c,"market_regime_v46","regime_date"); count=0
 for p in ps:
  pid=str(p["id"]); risk=latest(c,"portfolio_risk_v41","risk_date",f"portfolio_id=eq.{pid}"); committee=latest(c,"explainable_decisions_v43","decision_date",f"portfolio_id=eq.{pid}"); brain=latest(c,"portfolio_brain_snapshots_v44","snapshot_date",f"portfolio_id=eq.{pid}"); memory=latest(c,"decision_memory_v45","decision_date",f"portfolio_id=eq.{pid}"); perf=latest(c,"performance_daily_v46","performance_date",f"portfolio_id=eq.{pid}")
  c.upsert("market_replay_v46",{"replay_date":RUN_DATE,"portfolio_id":pid,"market_regime":reg.get("market_regime") or "UNKNOWN","risk_status":risk.get("risk_status") or "UNKNOWN","committee_status":committee.get("final_action") or "UNKNOWN","brain_status":brain.get("brain_status") or "UNKNOWN","recommendation":memory.get("recommendation") or "HOLD","confidence":memory.get("confidence") or 0,"expected_return_pct":memory.get("expected_return_pct"),"realized_return_pct":perf.get("daily_return_pct"),"snapshot":{"risk":risk,"committee":committee,"brain":brain,"memory":memory,"performance":perf}},"replay_date,portfolio_id"); count+=1
 print(f"Enterprise 4.6 created {count} market replay record(s).")
if __name__=="__main__": main()
