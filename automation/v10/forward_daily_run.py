from __future__ import annotations
import argparse, json
from datetime import date
from pathlib import Path
from .forward_validation import ForwardStore, latest_complete_session, load_cached_market, run_forward_day
from .phase2_research import TwseDailyTableProvider

def main() -> int:
    parser=argparse.ArgumentParser(description="V10 all-market forward shadow paper run")
    parser.add_argument("--cache",type=Path,required=True)
    parser.add_argument("--store",type=Path,required=True)
    parser.add_argument("--as-of",type=date.fromisoformat,default=date.today())
    args=parser.parse_args()
    provider=TwseDailyTableProvider(args.cache)
    session=latest_complete_session(provider,args.as_of)
    result=run_forward_day(load_cached_market(provider,session),session,ForwardStore(args.store))
    print(json.dumps({"run_id":result["run_id"],"business_date":result["business_date"],
        "total_symbols":result["total_symbols"],"eligible_symbols":result["eligible_symbols"],
        "strategies":len(result["strategies"]),"execution_status":result["execution_status"]},sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())

