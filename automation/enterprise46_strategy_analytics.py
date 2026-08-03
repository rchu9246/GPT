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
 c=SupabaseRestClient(); ss=c.get("enterprise_strategies_v40","enabled=eq.true&paper_approved=eq.true&limit=100"); ratings=c.get("strategy_rating_v45","order=rating_date.desc&limit=1000"); regs=c.get("market_regime_v46","order=regime_date.desc&limit=1"); regime=regs[0]["market_regime"] if regs else "UNKNOWN"; by={}; count=0
 for r in ratings:
  k=str(r.get("strategy_key"))
  if k not in by: by[k]=r
 for s in ss:
  key=str(s.get("strategy_key") or s["id"]); r=by.get(key,{}); samples=int(n(r.get("sample_count"))); overall=n(r.get("overall_score"),50); acc=n(r.get("prediction_accuracy"),50); cal=n(r.get("calibration_score"),50); avg=n(r.get("average_return_pct")); conf=n(r.get("average_confidence"),50)
  consistency=clamp((acc+cal)/2); stability=clamp(overall*.6+cal*.4); fit=65 if regime in ("SIDEWAYS","CHOPPY") else 55; edge=clamp(overall*.35+acc*.2+cal*.15+consistency*.15+fit*.15)
  status,action=("INSUFFICIENT_DATA","COLLECT_MORE_DATA") if samples<5 else (("PROMISING","PROMOTE_FOR_PAPER_REVIEW") if edge>=75 else (("WEAK","REVIEW_OR_RETIRE") if edge<=30 else ("STABLE","KEEP_PAPER")))
  c.upsert("strategy_analytics_v46",{"analytics_date":RUN_DATE,"strategy_id":s["id"],"strategy_key":key,"sample_count":samples,"alpha_pct":avg,"beta":clamp(1+(50-cal)/100,.2,2),"volatility_pct":clamp((100-overall)*.35),"consistency_score":consistency,"stability_score":stability,"learning_speed":clamp(samples*5),"confidence_drift":conf-50,"edge_score":edge,"regime_fit_score":fit,"analytics_status":status,"recommended_action":action,"diagnostics":{"source_rating_v45":bool(r),"market_regime":regime}},"analytics_date,strategy_key"); count+=1
 print(f"Enterprise 4.6 generated {count} strategy analytics record(s).")
if __name__=="__main__": main()
