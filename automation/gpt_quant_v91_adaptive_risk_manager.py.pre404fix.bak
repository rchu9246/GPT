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
    ap=argparse.ArgumentParser(); ap.add_argument("--base-risk-budget",type=float,default=.60); a=ap.parse_args()
    c=SupabaseRestClient()
    s=c.get("gpt_quant_v9_risk_summaries","order=risk_date.desc&limit=1")
    p=c.get("gpt_quant_v9_risk_portfolio_state","order=state_date.desc&limit=1")
    sm=s[0] if s else {}; st=p[0] if p else {}
    pnl=n(st.get("daily_pnl")); dd=n(st.get("portfolio_drawdown")); var=n(sm.get("estimated_total_var"))
    kill=bool(sm.get("kill_switch_active"))
    pm=.60 if pnl<-.01 else .85 if pnl<0 else 1.05 if pnl>.01 else 1.0
    dm=0.0 if dd>=.10 else .35 if dd>=.07 else .65 if dd>=.04 else .85 if dd>=.02 else 1.0
    vm=.40 if var>=.08 else .65 if var>=.05 else .80 if var>=.03 else 1.0
    budget=0.0 if kill else max(.15,min(.80,a.base_risk_budget*pm*dm*vm))
    regime="HALT" if budget==0 else "DEFENSIVE" if budget<.30 else "CAUTIOUS" if budget<.55 else "NORMAL"
    c.upsert("gpt_quant_v91_adaptive_risk_state",{
        "state_date":datetime.now(timezone.utc).date().isoformat(),
        "base_risk_budget":a.base_risk_budget,"adaptive_risk_budget":budget,
        "pnl_multiplier":pm,"drawdown_multiplier":dm,"var_multiplier":vm,
        "daily_pnl":pnl,"portfolio_drawdown":dd,"estimated_total_var":var,
        "risk_regime":regime,"kill_switch_active":kill,"paper_only":True,
        "live_trading_enabled":False,"broker_submission_enabled":False,
        "engine_version":VERSION,"calculated_at":now()
    },"state_date")
    print(f"Adaptive risk budget={budget:.2%}; regime={regime}")

if __name__=="__main__":main()
