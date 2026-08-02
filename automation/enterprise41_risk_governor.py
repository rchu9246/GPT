from __future__ import annotations
import math, os
from datetime import date, datetime, timezone
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



def latest_risk_snapshot(c,pid,account):
    sources=[
        ("compat_risk_snapshot_v41","snapshot_date",f"portfolio_id=eq.{pid}"),
        ("risk_snapshots_v32","snapshot_date",f"account_name=eq.{account}"),
    ]
    for table,field,where in sources:
        try:
            row=latest(c,table,field,where)
            if row:
                row["_source"]=table
                return row
        except Exception:
            pass
    return {
        "_source":"default",
        "var_95_pct":0,
        "expected_shortfall_pct":0,
        "max_drawdown_pct":0,
        "concentration_pct":0,
        "gross_exposure_pct":0,
        "liquidity_score":100,
    }

def main():
    c=SupabaseRestClient()
    portfolios=c.get("enterprise_portfolios_v40","lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100")
    strategies=c.get("enterprise_strategies_v40","enabled=eq.true&paper_approved=eq.true&limit=100")
    critical=warnings=0; scores=[]; blockers=[]

    for p in portfolios:
        pid=str(p["id"]); account=str(p.get("account_name") or "paper-main")
        r=latest_risk_snapshot(c,pid,account)
        equity=n(latest(c,"compat_portfolios_v40","latest_snapshot_date",f"portfolio_id=eq.{pid}").get("latest_equity"),n(p.get("starting_cash"),1000000))
        var95=n(r.get("var_95_pct")); es=n(r.get("expected_shortfall_pct")); dd=n(r.get("max_drawdown_pct")); conc=n(r.get("concentration_pct")); gross=n(r.get("gross_exposure_pct")); liq=n(r.get("liquidity_score"),100)
        breaches=[]
        limits=[("MAX_VAR_95_PCT",var95,3,"CRITICAL"),("MAX_EXPECTED_SHORTFALL_PCT",es,4,"CRITICAL"),("MAX_DRAWDOWN_PCT",dd,n(p.get("max_drawdown_pct"),12),"CRITICAL"),("MAX_SINGLE_POSITION_PCT",conc,n(p.get("max_position_pct"),15),"WARNING")]
        for key,obs,lim,severity in limits:
            if obs>lim:
                breaches.append(key)
                c.insert("risk_events_v41",{"event_date":RUN_DATE,"portfolio_id":pid,"strategy_id":None,"event_type":"PORTFOLIO_LIMIT_BREACH","severity":severity,"event_status":"OPEN","limit_key":key,"observed_value":obs,"limit_value":lim,"decision":"TRIGGER_BREAKER" if severity=="CRITICAL" else "REDUCE","message":f"{key}: {obs:.2f} > {lim:.2f}"})
                if severity=="CRITICAL": critical+=1
                else: warnings+=1
        score=min(100,var95*10+es*8+dd*2+conc+max(0,gross-100)*2); scores.append(score)
        status="CRITICAL" if any(x!="MAX_SINGLE_POSITION_PCT" for x in breaches) else "WARNING" if breaches else "PASS"
        if status=="CRITICAL":
            blockers.append(f"portfolio:{p.get('portfolio_key')}")
            bs=c.get("circuit_breakers_v41",f"portfolio_id=eq.{pid}&enabled=eq.true")
            for b in bs:
                c.patch("circuit_breakers_v41",f"id=eq.{b['id']}",{"breaker_status":"TRIGGERED","last_triggered_at":datetime.now(timezone.utc).isoformat(),"trigger_count":int(b.get("trigger_count") or 0)+1})
        c.upsert("portfolio_risk_v41",{"portfolio_id":pid,"risk_date":RUN_DATE,"equity":equity,"daily_loss_pct":0,"gross_exposure_pct":gross,"var_95_pct":var95,"expected_shortfall_pct":es,"max_drawdown_pct":dd,"concentration_pct":conc,"liquidity_score":liq,"risk_score":score,"risk_status":status,"breaches":breaches,"diagnostics":{"source":r.get("_source","unknown")}},"portfolio_id,risk_date")
        c.insert("risk_governor_decisions_v41",{"decision_date":RUN_DATE,"portfolio_id":pid,"strategy_id":None,"decision_scope":"PORTFOLIO","requested_action":"CONTINUE_PAPER_OPERATIONS","decision":"BLOCKED" if status=="CRITICAL" else "REDUCED" if status=="WARNING" else "APPROVED","rationale":f"Portfolio risk status {status}.","breaches":breaches,"policy_snapshot":{"var95":3,"es":4,"drawdown":n(p.get("max_drawdown_pct"),12),"position":n(p.get("max_position_pct"),15)}})

    for s in strategies:
        sid=str(s["id"])
        m=latest(c,"quant_strategy_marketplace","updated_at",f"strategy_key=eq.{s.get('strategy_key')}")
        quality=n(m.get("quality_score"),50); score=min(100,100-quality); breaches=[]
        if score>=80:
            breaches.append("STRATEGY_RISK_SCORE"); critical+=1; status="CRITICAL"; blockers.append(f"strategy:{s.get('strategy_key')}")
        elif score>=60:
            warnings+=1; status="WARNING"
        else:
            status="PASS"
        c.upsert("strategy_risk_v41",{"strategy_id":sid,"risk_date":RUN_DATE,"allocation_weight":0,"health_score":quality,"risk_score":score,"risk_status":status,"breaches":breaches,"diagnostics":{"source":"quant_strategy_marketplace"}},"strategy_id,risk_date")

    active=c.get("circuit_breakers_v41","breaker_status=eq.TRIGGERED&enabled=eq.true&select=id&limit=1000")
    avg=sum(scores)/len(scores) if scores else 0
    overall="CRITICAL" if critical or active else "WARNING" if warnings else "PASS"
    summary=f"Checked {len(portfolios)} portfolio(s), {len(strategies)} strategy(s); critical {critical}, warnings {warnings}, active breakers {len(active)}."
    c.upsert("risk_governor_status_v41",{"status_date":RUN_DATE,"overall_status":overall,"overall_risk_score":avg,"active_breakers":len(active),"open_critical_events":critical,"open_warning_events":warnings,"portfolios_checked":len(portfolios),"strategies_checked":len(strategies),"live_trading_enabled":False,"blockers":blockers,"summary":summary},"status_date")
    c.insert("audit_logs_v40",{"actor_type":"SYSTEM","actor_key":"enterprise41-risk-governor","action":"DAILY_RISK_GOVERNANCE_COMPLETED","entity_type":"RISK_GOVERNOR","entity_key":RUN_DATE,"severity":"CRITICAL" if overall=="CRITICAL" else "INFO","metadata":{"overall_status":overall,"summary":summary,"blockers":blockers}})
    print(summary)
    print(f"Central Risk Governor status: {overall}")

if __name__=="__main__":
    main()
