from __future__ import annotations
import argparse
from datetime import datetime, timezone
from enterprise2.client import SupabaseRestClient

VERSION="9.1.0"
def n(v,d=0.0):
    try:return float(v)
    except (TypeError,ValueError):return d
def now():return datetime.now(timezone.utc).isoformat()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--max-positions",type=int,default=10)
    ap.add_argument("--max-single-weight",type=float,default=.10)
    a=ap.parse_args(); c=SupabaseRestClient()
    cal=c.get("gpt_quant_v91_confidence_calibration","order=final_confidence.desc&limit=100")
    rs=c.get("gpt_quant_v91_adaptive_risk_state","order=state_date.desc&limit=1")
    budget=n(rs[0].get("adaptive_risk_budget")) if rs else 0.0
    eligible=[r for r in cal if r.get("governed_recommendation") in {"STRONG_BUY","BUY","WATCH"}][:a.max_positions]
    scores=[max(0,n(r.get("final_confidence"))) for r in eligible]; total=sum(scores)
    today=datetime.now(timezone.utc).date().isoformat()
    for r,score in zip(eligible,scores):
        raw=0 if total<=0 else budget*score/total; opt=min(raw,a.max_single_weight)
        c.upsert("gpt_quant_v91_portfolio_allocations",{
            "allocation_date":today,"ranking_id":r["ranking_id"],"final_confidence":score,
            "governed_recommendation":r["governed_recommendation"],"raw_weight":raw,
            "optimized_weight":opt,"risk_budget":budget,"paper_only":True,
            "live_trading_enabled":False,"broker_submission_enabled":False,
            "engine_version":VERSION,"calculated_at":now()
        },"allocation_date,ranking_id")
    print(f"Optimized {len(eligible)} allocations")

if __name__=="__main__":main()
