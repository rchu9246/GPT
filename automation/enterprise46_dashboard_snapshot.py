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

from statistics import mean
def main():
 c=SupabaseRestClient(); health=c.get("portfolio_health_v46",f"health_date=eq.{RUN_DATE}&limit=100"); ss=c.get("strategy_analytics_v46",f"analytics_date=eq.{RUN_DATE}&limit=100"); regs=c.get("market_regime_v46",f"regime_date=eq.{RUN_DATE}&limit=1"); learn=c.get("learning_cycle_status_v45",f"status_date=eq.{RUN_DATE}&limit=1")
 regime=regs[0]["market_regime"] if regs else "UNKNOWN"; ah=mean([n(x.get("health_score")) for x in health]) if health else 0; ae=mean([n(x.get("edge_score")) for x in ss]) if ss else 0; od=int(n(learn[0].get("open_decisions"))) if learn else 0; fr=int(n(learn[0].get("feedback_records"))) if learn else 0
 blockers=[]; 
 if any(x.get("health_status")=="CRITICAL" for x in health): blockers.append("CRITICAL_PORTFOLIO_HEALTH")
 if regime=="BEAR_RISK_OFF": blockers.append("MARKET_RISK_OFF")
 overall="CRITICAL" if blockers else ("WARNING" if ah<65 else "PASS"); summary=f"Processed {len(health)} portfolio(s) and {len(ss)} strategy analytics; market regime {regime}; open decisions {od}."
 c.upsert("enterprise_dashboard_v46",{"dashboard_date":RUN_DATE,"overall_status":overall,"market_regime":regime,"portfolios_processed":len(health),"strategies_processed":len(ss),"average_health_score":ah,"average_strategy_edge":ae,"open_decisions":od,"learning_feedback_records":fr,"scheduler_status":"PASS","live_trading_enabled":False,"live_learning_enabled":False,"blockers":blockers,"highlights":[f"Market regime: {regime}",f"Average portfolio health: {ah:.1f}",f"Average strategy edge: {ae:.1f}"],"summary":summary},"dashboard_date")
 print(summary)
if __name__=="__main__": main()
