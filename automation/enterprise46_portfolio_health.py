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
 c=SupabaseRestClient(); ps=c.get("enterprise_portfolios_v40","lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100"); count=0
 for p in ps:
  pid=str(p["id"]); perf=latest(c,"performance_daily_v46","performance_date",f"portfolio_id=eq.{pid}"); risk=latest(c,"portfolio_risk_v41","risk_date",f"portfolio_id=eq.{pid}"); ds=c.get("decision_memory_v45",f"portfolio_id=eq.{pid}&order=decision_date.desc&limit=100")
  rs=clamp(100-n(risk.get("risk_score"))); gs=clamp(50+n(perf.get("cumulative_return_pct"))*5); ls=clamp(n(risk.get("liquidity_score"),100)); div=clamp(100-n(risk.get("concentration_pct"))); es=clamp(100-abs(n(risk.get("gross_exposure_pct"))-75)); dds=clamp(100-n(perf.get("max_drawdown_pct"))*5); lv=[n(x.get("learning_score")) for x in ds if n(x.get("learning_score"))>0]; learn=sum(lv)/len(lv) if lv else 50
  hs=clamp(rs*.25+gs*.2+ls*.15+div*.15+es*.1+dds*.1+learn*.05); blockers=[]; rec=[]
  if rs<40: blockers.append("HIGH_RISK"); rec.append("Reduce portfolio risk.")
  if div<50: rec.append("Improve diversification.")
  status="CRITICAL" if blockers or hs<40 else ("WARNING" if hs<65 else "PASS")
  c.upsert("portfolio_health_v46",{"health_date":RUN_DATE,"portfolio_id":pid,"health_score":hs,"risk_score":rs,"growth_score":gs,"liquidity_score":ls,"diversification_score":div,"exposure_score":es,"drawdown_score":dds,"learning_score":learn,"health_status":status,"blockers":blockers,"recommendations":rec,"diagnostics":{"decision_samples":len(ds)}},"health_date,portfolio_id"); count+=1
 print(f"Enterprise 4.6 generated {count} portfolio health record(s).")
if __name__=="__main__": main()
