from __future__ import annotations
import argparse, math
from datetime import datetime, timezone
from statistics import mean, pstdev
from enterprise2.client import SupabaseRestClient

VERSION = "9.1.0"

def n(v, d=0.0):
    try:
        x=float(v)
        return d if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return d

def pct(values, value):
    if not values: return 50.0
    return 100.0*(sum(x < value for x in values)+0.5*sum(x == value for x in values))/len(values)

def clamp(x): return max(0.0, min(100.0, x))
def now(): return datetime.now(timezone.utc).isoformat()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=100); a=ap.parse_args()
    c=SupabaseRestClient()
    rows=c.get("portfolio_rankings_v56", f"order=ranking_date.desc,rank_no.asc&limit={a.limit}")
    if not rows: raise RuntimeError("No portfolio rankings")
    raw=[n(r.get("confidence_score")) for r in rows]
    mu=mean(raw); sd=pstdev(raw) if len(raw)>1 else 0.0
    for r in rows:
        rc=n(r.get("confidence_score")); evo=n(r.get("evolution_score"))
        pr=pct(raw, rc); z=0.0 if sd<=1e-9 else (rc-mu)/sd
        calibrated=clamp(0.65*pr+0.35*clamp(50+15*z))
        penalty=max(0.0, abs(evo-calibrated)-25)*0.25
        final=clamp(calibrated-penalty)
        rec="STRONG_BUY" if final>=80 else "BUY" if final>=65 else "WATCH" if final>=50 else "REJECT"
        c.upsert("gpt_quant_v91_confidence_calibration", {
            "ranking_id":r["id"], "raw_confidence":rc, "historical_percentile":pr,
            "z_score":z, "calibrated_confidence":calibrated,
            "consistency_penalty":penalty, "final_confidence":final,
            "governed_recommendation":rec, "engine_version":VERSION,
            "calculated_at":now()
        }, "ranking_id")
    print(f"Calibrated {len(rows)} rankings; paper only")

if __name__=="__main__": main()
