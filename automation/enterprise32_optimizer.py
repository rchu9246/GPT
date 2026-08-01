from __future__ import annotations
import math, os
from enterprise2.client import SupabaseRestClient
ACCOUNT=os.environ.get("AUTOTRADER_ACCOUNT","paper-main")
def n(v,d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d
def main():
    c=SupabaseRestClient()
    recs=c.get("quant_portfolio_recommendations",f"account_name=eq.{ACCOUNT}&order=recommendation_date.desc,expected_return_score.desc&limit=200")
    if not recs:
        print("No recommendations."); return
    latest=str(recs[0]["recommendation_date"]); recs=[r for r in recs if str(r.get("recommendation_date"))==latest and r.get("action")=="BUY"][:5]
    cfgs=c.get("autotrader_configs_v13",f"account_name=eq.{ACCOUNT}&limit=1"); cfg=cfgs[0] if cfgs else {}
    reserve=n(cfg.get("reserve_cash_pct"),30); max_pos=n(cfg.get("max_position_pct"),15)
    scores=[max(1,n(r.get("expected_return_score")))*max(.25,n(r.get("conviction"),50)/100)/(max(1,n(r.get("risk_score"),50))+25) for r in recs]
    total=sum(scores) or 1; investable=max(0,100-reserve)
    run=c.upsert("portfolio_optimization_runs_v32",{"account_name":ACCOUNT,"optimization_date":latest,"method":"RISK_ADJUSTED_CONVICTION","status":"SUCCESS","target_volatility":12,"estimated_volatility":None,"expected_return_score":sum(n(r.get("expected_return_score")) for r in recs)/len(recs) if recs else 0,"estimated_var_95":None,"estimated_expected_shortfall":None,"turnover_pct":None,"cash_weight":reserve,"constraints":{"max_positions":5,"max_position_pct":max_pos},"diagnostics":{"selected":len(recs)}},"account_name,optimization_date,method")
    run_id=run[0]["id"] if run else None
    for r,s in zip(recs,scores):
        target=min(max_pos,investable*s/total)
        c.upsert("portfolio_target_weights_v32",{"run_id":run_id,"account_name":ACCOUNT,"optimization_date":latest,"symbol":str(r.get("symbol")),"stock_id":r.get("stock_id"),"current_weight":0,"target_weight":target,"delta_weight":target,"risk_contribution":target*n(r.get("risk_score"),50)/100,"expected_return_score":n(r.get("expected_return_score")),"action":"BUY","rationale":f"Risk-adjusted conviction allocation {target:.2f}%."},"account_name,optimization_date,symbol")
    print(f"Optimizer completed: {len(recs)} targets.")
if __name__=="__main__":main()
