from __future__ import annotations
import math, os
from datetime import date
from enterprise2.client import SupabaseRestClient
ACCOUNT=os.environ.get("AUTOTRADER_ACCOUNT","paper-main")
def n(v,d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d
def latest(c,t,f):
    r=c.get(t,f"account_name=eq.{ACCOUNT}&order={f}.desc&limit=1"); return r[0] if r else {}
def main():
    c=SupabaseRestClient(); p=latest(c,"quant_portfolio_snapshots","snapshot_date")
    w=c.get("portfolio_target_weights_v32",f"account_name=eq.{ACCOUNT}&order=optimization_date.desc,target_weight.desc&limit=100")
    d=str(w[0]["optimization_date"]) if w else date.today().isoformat(); w=[x for x in w if str(x.get("optimization_date"))==d]
    gross=sum(abs(n(x.get("target_weight"))) for x in w); concentration=max([n(x.get("target_weight")) for x in w],default=0)
    weighted=sum(n(x.get("risk_contribution")) for x in w); var95=min(10,gross*.025+weighted*.01); es=min(15,var95*1.35)
    mdd=abs(n(p.get("max_drawdown"))); stress=min(25,var95*2.5+concentration*.15); liquidity=max(0,100-concentration*2)
    score=min(100,var95*12+es*5+mdd*2+concentration); breaches=[]
    if var95>3:breaches.append("VAR_95_LIMIT")
    if es>4:breaches.append("EXPECTED_SHORTFALL_LIMIT")
    if concentration>15:breaches.append("CONCENTRATION_LIMIT")
    if mdd>12:breaches.append("MAX_DRAWDOWN_LIMIT")
    status="CRITICAL" if len(breaches)>=2 else "WARNING" if breaches else "PASS"
    c.upsert("risk_snapshots_v32",{"account_name":ACCOUNT,"snapshot_date":d,"equity":n(p.get("equity")),"gross_exposure_pct":gross,"net_exposure_pct":gross,"var_95_pct":var95,"expected_shortfall_pct":es,"max_drawdown_pct":mdd,"stress_loss_pct":stress,"concentration_pct":concentration,"liquidity_score":liquidity,"risk_score":score,"risk_status":status,"breaches":breaches,"diagnostics":{"target_count":len(w)}},"account_name,snapshot_date")
    print(f"Risk Engine 2.0: {status}, score {score:.1f}.")
if __name__=="__main__":main()
