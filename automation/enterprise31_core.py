
from __future__ import annotations
import os, math
from datetime import date
from typing import Any
from enterprise2.client import SupabaseRestClient
ACCOUNT=os.environ.get("AUTOTRADER_ACCOUNT","paper-main"); RUN_DATE=os.environ.get("QUANT_RUN_DATE",date.today().isoformat())
def n(v:Any,d:float=0.0)->float:
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d
def latest(c,t,f):
    r=c.get(t,f"account_name=eq.{ACCOUNT}&order={f}.desc&limit=1"); return r[0] if r else {}
def main():
    c=SupabaseRestClient(); blockers=[]
    prices=c.get("daily_prices","select=trade_date&order=trade_date.desc&limit=1"); signals=c.get("signals","select=trade_date&order=trade_date.desc&limit=1")
    market_date=str(prices[0]["trade_date"]) if prices else None; signal_date=str(signals[0]["trade_date"]) if signals else None
    run=latest(c,"quant_release_runs","run_date"); portfolio=latest(c,"quant_portfolio_snapshots","snapshot_date"); directive=latest(c,"trading_directives_v22","directive_date")
    orders=c.get("trade_orders_v13",f"account_name=eq.{ACCOUNT}&select=status&limit=5000"); positions=c.get("paper_positions_v13",f"account_name=eq.{ACCOUNT}&select=symbol&limit=5000")
    risks=c.get("quant_risk_events",f"account_name=eq.{ACCOUNT}&status=eq.OPEN&limit=500"); strategies=c.get("quant_strategy_marketplace","select=quality_score&limit=500")
    data_score=100 if market_date and signal_date else 40; pipeline_score=100 if run.get("run_status")=="SUCCESS" else 50
    strategy_score=sum(n(x.get("quality_score")) for x in strategies)/len(strategies) if strategies else 50; portfolio_score=100 if portfolio or positions else 60; risk_score=max(0,100-len(risks)*15)
    overall=sum([100,data_score,pipeline_score,strategy_score,portfolio_score,risk_score,100])/7
    if not market_date:blockers.append("market_data_missing")
    if not signal_date:blockers.append("signals_missing")
    if run.get("run_status")!="SUCCESS":blockers.append("stable_pipeline_not_success")
    if risks:blockers.append(f"open_risk_events:{len(risks)}")
    status="HEALTHY" if overall>=85 and not blockers else "DEGRADED" if overall>=60 else "CRITICAL"
    c.upsert("enterprise_health_v31",{"account_name":ACCOUNT,"health_date":RUN_DATE,"overall_score":overall,"database_score":100,"data_score":data_score,"pipeline_score":pipeline_score,"strategy_score":strategy_score,"portfolio_score":portfolio_score,"risk_score":risk_score,"frontend_score":100,"overall_status":status,"blockers":blockers,"details":{"market_date":market_date,"signal_date":signal_date}},"account_name,health_date")
    proposed=sum(1 for x in orders if x.get("status")=="PROPOSED"); approved=sum(1 for x in orders if x.get("status")=="APPROVED"); filled=sum(1 for x in orders if x.get("status")=="FILLED")
    headline="Enterprise 3.1 operating normally" if status=="HEALTHY" else "Enterprise 3.1 requires review"; market=f"Latest market {market_date or 'missing'}, signals {signal_date or 'missing'}."; port=f"Equity {n(portfolio.get('equity')):,.0f}, cash {n(portfolio.get('cash')):,.0f}, {len(positions)} positions."; risk="No open risk events." if not risks else f"{len(risks)} open risk event(s)."; strategy=f"{len(strategies)} strategies, average quality {strategy_score:.1f}."; ops=f"Stable run {run.get('run_status','NO_DATA')}, health {overall:.1f}/100 ({status})."; actions=blockers or ["Continue PAPER validation and monitoring."]
    c.upsert("daily_executive_reports_v31",{"account_name":ACCOUNT,"report_date":RUN_DATE,"report_version":"3.1.0","headline":headline,"market_summary":market,"portfolio_summary":port,"risk_summary":risk,"strategy_summary":strategy,"operations_summary":ops,"action_items":actions,"payload":{"overall_score":overall,"blockers":blockers}},"account_name,report_date,report_version")
    c.upsert("operations_center_v31",{"account_name":ACCOUNT,"snapshot_date":RUN_DATE,"market_date":market_date,"signal_date":signal_date,"pipeline_status":run.get("run_status") or "NO_DATA","data_status":"PASS" if market_date and signal_date else "FAIL","strategy_status":"PASS" if strategies else "WARN","portfolio_status":"PASS" if portfolio or positions else "WARN","risk_status":"PASS" if not risks else "WARN","frontend_status":"PASS","health_score":overall,"equity":n(portfolio.get("equity")),"cash":n(portfolio.get("cash")),"proposed_orders":proposed,"approved_orders":approved,"filled_orders":filled,"open_positions":len(positions),"latest_action":directive.get("directive") or "NO_DATA","latest_report":headline,"blockers":blockers},"account_name,snapshot_date")
    print(f"Enterprise 3.1 health: {overall:.1f} ({status})")
if __name__=="__main__": main()
