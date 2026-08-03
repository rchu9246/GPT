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

from statistics import mean,pstdev
def main():
 c=SupabaseRestClient(); perf=c.get("performance_daily_v46","order=performance_date.asc&limit=500"); ret=[n(x.get("daily_return_pct")) for x in perf][-20:]
 bench=sum(ret); vol=pstdev(ret)*math.sqrt(252) if len(ret)>=2 else 0; rr=c.get("risk_governor_status_v41","order=status_date.desc&limit=20"); risk=mean([n(x.get("overall_risk_score")) for x in rr]) if rr else 0
 trend="BULL" if bench>2 else "BEAR" if bench<-2 else "SIDEWAYS"; vr="HIGH_VOLATILITY" if vol>=25 else "LOW_VOLATILITY"; riskreg="RISK_OFF" if risk>=60 or trend=="BEAR" else "RISK_ON"
 mr="CHOPPY" if trend=="SIDEWAYS" and vr=="HIGH_VOLATILITY" else ("BULL_RISK_ON" if trend=="BULL" and riskreg=="RISK_ON" else ("BEAR_RISK_OFF" if trend=="BEAR" else trend)); conf=clamp(55+min(abs(bench)*5,25)+min(vol/5,20),0,95)
 c.upsert("market_regime_v46",{"regime_date":RUN_DATE,"trend_regime":trend,"volatility_regime":vr,"risk_regime":riskreg,"market_regime":mr,"regime_confidence":conf,"benchmark_return_pct":bench,"realized_volatility_pct":vol,"drawdown_pct":max([n(x.get("max_drawdown_pct")) for x in perf],default=0),"breadth_score":clamp(50+bench*5),"liquidity_score":clamp(100-risk),"evidence":{"performance_samples":len(ret),"average_risk_score":risk}},"regime_date")
 print(f"Enterprise 4.6 market regime: {mr} ({conf:.1f}% confidence).")
if __name__=="__main__": main()
