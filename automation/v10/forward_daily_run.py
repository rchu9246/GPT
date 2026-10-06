from __future__ import annotations
import argparse, json
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from .forward_validation import ForwardStore, latest_complete_session, load_cached_market, run_forward_day
from .phase2_research import TwseDailyTableProvider

def main() -> int:
    parser=argparse.ArgumentParser(description="V10 all-market forward shadow paper run")
    parser.add_argument("--cache",type=Path,required=True)
    parser.add_argument("--store",type=Path,required=True)
    parser.add_argument("--as-of",type=date.fromisoformat,default=datetime.now(ZoneInfo("Asia/Taipei")).date())
    args=parser.parse_args()
    provider=TwseDailyTableProvider(args.cache)
    session=latest_complete_session(provider,args.as_of)
    store=ForwardStore(args.store)
    data=load_cached_market(provider,session)
    completed=store.completed_dates()
    for existing in completed:
        if existing in data.days:
            run_forward_day(data,existing,store)
    last=completed[-1] if completed else store.boundary()
    for trading_day in sorted(d for d in data.days if (last < d or (not completed and last==d)) and d<=session and len(data.bars_by_date[d])>=500):
        run_forward_day(data,trading_day,store)
    result=run_forward_day(data,session,store)
    print(json.dumps({"run_id":result["run_id"],"business_date":result["business_date"],
        "total_symbols":result["total_symbols"],"eligible_symbols":result["eligible_symbols"],
        "strategies":len(result["strategies"]),"execution_status":result["execution_status"]},sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())

