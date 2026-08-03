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
 c=SupabaseRestClient(); ps=c.get("enterprise_portfolios_v40","lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100"); count=0
 for p in ps:
  pid=str(p["id"]); rows=c.get("portfolio_snapshots_v40",f"portfolio_id=eq.{pid}&order=snapshot_date.asc&limit=500")
  compat=latest(c,"compat_portfolios_v40","latest_snapshot_date",f"portfolio_id=eq.{pid}"); risk=latest(c,"portfolio_risk_v41","risk_date",f"portfolio_id=eq.{pid}")
  eq=[n(x.get("equity")) for x in rows if n(x.get("equity"))>0]; cur=n(compat.get("latest_equity"),eq[-1] if eq else n(p.get("starting_cash"),1000000))
  if not eq: eq=[n(p.get("starting_cash"),1000000),cur]
  elif eq[-1]!=cur: eq.append(cur)
  ret=[(eq[i]/eq[i-1]-1)*100 for i in range(1,len(eq)) if eq[i-1]>0]; avg=mean(ret) if ret else 0
  vol=pstdev(ret)*math.sqrt(252) if len(ret)>=2 else 0; dn=[x for x in ret if x<0]; ddv=pstdev(dn)*math.sqrt(252) if len(dn)>=2 else 0; annual=avg*252
  peak=eq[0]; draw=[]
  for v in eq: peak=max(peak,v); draw.append((v/peak-1)*100 if peak else 0)
  mdd=abs(min(draw)) if draw else 0; wins=[x for x in ret if x>0]; losses=[x for x in ret if x<0]; gp=sum(wins); gl=abs(sum(losses)); gross=n(risk.get("gross_exposure_pct"))
  c.upsert("performance_daily_v46",{"performance_date":RUN_DATE,"portfolio_id":pid,"equity":cur,"daily_return_pct":ret[-1] if ret else 0,"cumulative_return_pct":(eq[-1]/eq[0]-1)*100 if eq[0] else 0,"rolling_volatility_pct":vol,"sharpe_ratio":(annual-1.5)/vol if vol else 0,"sortino_ratio":(annual-1.5)/ddv if ddv else 0,"calmar_ratio":annual/mdd if mdd else 0,"max_drawdown_pct":mdd,"win_rate":len(wins)/len(ret)*100 if ret else 0,"profit_factor":gp/gl if gl else gp,"expectancy_pct":avg,"gross_exposure_pct":gross,"cash_ratio_pct":clamp(100-gross),"sample_count":len(ret),"diagnostics":{"source":"portfolio_snapshots_v40+compat_portfolios_v40"}},"performance_date,portfolio_id"); count+=1
 print(f"Enterprise 4.6 generated {count} performance record(s).")
if __name__=="__main__": main()
