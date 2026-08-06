from __future__ import annotations
import argparse, uuid
from datetime import datetime, timezone
from enterprise2.client import SupabaseRestClient

VERSION="9.1.0"
def now():return datetime.now(timezone.utc).isoformat()
def uid(*p):return str(uuid.uuid5(uuid.NAMESPACE_URL,"|".join(map(str,p))))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--starting-equity",type=float,default=1000000); a=ap.parse_args()
    c=SupabaseRestClient(); today=datetime.now(timezone.utc).date().isoformat()
    alloc=c.get("gpt_quant_v91_portfolio_allocations",f"allocation_date=eq.{today}&order=optimized_weight.desc&limit=100")
    sid=uid("v91-paper",today)
    c.upsert("gpt_quant_v91_paper_sessions",{
        "id":sid,"session_date":today,"starting_equity":a.starting_equity,
        "ending_equity":a.starting_equity,"realized_pnl":0,"unrealized_pnl":0,
        "gross_exposure":sum(float(r.get("optimized_weight") or 0) for r in alloc),
        "open_positions":len(alloc),"session_status":"READY","paper_only":True,
        "live_trading_enabled":False,"broker_submission_enabled":False,
        "engine_version":VERSION,"created_at":now(),"updated_at":now()
    },"session_date")
    for r in alloc:
        c.upsert("gpt_quant_v91_paper_positions",{
            "id":uid("v91-position",today,r["ranking_id"]),"session_id":sid,
            "position_date":today,"ranking_id":r["ranking_id"],
            "target_weight":r["optimized_weight"],"filled_weight":r["optimized_weight"],
            "unrealized_pnl":0,"position_status":"PLANNED","paper_only":True,
            "live_trading_enabled":False,"broker_submission_enabled":False,
            "engine_version":VERSION,"created_at":now(),"updated_at":now()
        },"position_date,ranking_id")
    print(f"Paper session ready; positions={len(alloc)}; no broker orders")

if __name__=="__main__":main()
