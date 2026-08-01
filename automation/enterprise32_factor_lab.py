from __future__ import annotations
import math, os
from datetime import date
from typing import Any
from enterprise2.client import SupabaseRestClient
ACCOUNT=os.environ.get("AUTOTRADER_ACCOUNT","paper-main")
def n(v:Any,d:float=0.0)->float:
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d
def clamp(v:float)->float:return max(0.0,min(100.0,v))
def main():
    c=SupabaseRestClient()
    rows=c.get("signals","select=stock_id,trade_date,total_score,trend_score,momentum_score,volume_score,risk_score,confidence,strategy_version&order=trade_date.desc,total_score.desc&limit=2000")
    if not rows:
        print("No signals for factor lab."); return
    latest=str(rows[0]["trade_date"]); rows=[r for r in rows if str(r.get("trade_date"))==latest]
    stocks=c.get("stocks","select=id,symbol,name&limit=10000"); stock_map={str(x["id"]):x for x in stocks}
    buckets={"trend":[],"momentum":[],"volume":[],"quality":[],"risk_adjusted":[]}
    for r in rows:
        s=stock_map.get(str(r.get("stock_id")))
        if not s: continue
        vals={
          "trend":clamp(n(r.get("trend_score"),50)),
          "momentum":clamp(n(r.get("momentum_score"),50)),
          "volume":clamp(n(r.get("volume_score"),50)),
          "quality":clamp((n(r.get("confidence"),50)+n(r.get("total_score"),50))/2),
          "risk_adjusted":clamp(n(r.get("total_score"),50)*0.7+(100-n(r.get("risk_score"),50))*0.3)
        }
        for k,v in vals.items():
            buckets[k].append(v)
            c.upsert("factor_observations_v32",{"account_name":ACCOUNT,"observation_date":latest,"symbol":str(s.get("symbol")),"stock_id":r.get("stock_id"),"factor_key":k,"raw_value":v,"normalized_score":v,"percentile":None,"source_table":"signals","metadata":{"strategy_version":r.get("strategy_version")}},"account_name,observation_date,symbol,factor_key")
    ranks=[]
    for k,vals in buckets.items():
        if not vals: continue
        avg=sum(vals)/len(vals); sd=(sum((x-avg)**2 for x in vals)/len(vals))**0.5
        stability=clamp(100-sd); quality=clamp(avg*0.7+stability*0.3)
        rec="KEEP" if quality>=65 else "WATCH" if quality>=45 else "REDUCE"
        c.patch("factor_library_v32",f"factor_key=eq.{k}&factor_version=eq.1.0",{"quality_score":quality,"stability_score":stability,"latest_evaluation_date":latest})
        ranks.append((k,quality,stability,rec))
    ranks.sort(key=lambda x:x[1],reverse=True)
    for i,(k,q,s,r) in enumerate(ranks,1):
        c.upsert("factor_rankings_v32",{"account_name":ACCOUNT,"ranking_date":latest,"factor_key":k,"rank_position":i,"quality_score":q,"ic":None,"rank_ic":None,"stability_score":s,"recommendation":r},"account_name,ranking_date,factor_key")
    print(f"Factor Lab completed: {len(ranks)} factors.")
if __name__=="__main__":main()
