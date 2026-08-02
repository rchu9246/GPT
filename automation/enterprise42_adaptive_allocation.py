
from __future__ import annotations
import math, os, random
from datetime import date
from enterprise2.client import SupabaseRestClient
RUN_DATE=os.environ.get("QUANT_RUN_DATE",date.today().isoformat()); PATHS=int(os.environ.get("ENTERPRISE42_MC_PATHS","500")); DAYS=int(os.environ.get("ENTERPRISE42_MC_DAYS","20"))
def n(v,d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d
def latest(c,t,f,w=""):
    q=f"{w}&order={f}.desc&limit=1" if w else f"order={f}.desc&limit=1"; r=c.get(t,q); return r[0] if r else {}


def safe_get(c,table,query):
    try:
        return c.get(table,query)
    except Exception:
        return []

def main():
    random.seed(42); c=SupabaseRestClient(); portfolios=c.get("enterprise_portfolios_v40","lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100"); strategies=c.get("enterprise_strategies_v40","enabled=eq.true&paper_approved=eq.true&limit=100"); regime=str(latest(c,"market_regimes_v40","regime_date").get("regime") or "UNKNOWN"); rm={"BULL":1.0,"SIDEWAYS":.8,"BEAR":.45,"HIGH_VOLATILITY":.35,"RISK_OFF":.1,"UNKNOWN":.5}.get(regime,.5); scenarios=c.get("scenario_definitions_v42","enabled=eq.true&limit=100"); srun=props=0; blockers=[]
    for i,a in enumerate(strategies):
      for b in strategies[i:]:
        corr=1.0 if a['id']==b['id'] else .75 if a.get('strategy_family')==b.get('strategy_family') else .35; status='CRITICAL' if corr>.8 and a['id']!=b['id'] else 'WARNING' if corr>.65 and a['id']!=b['id'] else 'PASS'; c.upsert('strategy_correlation_v42',{'correlation_date':RUN_DATE,'strategy_id_a':a['id'],'strategy_id_b':b['id'],'correlation':corr,'diversification_score':(1-abs(corr))*100,'risk_status':status,'diagnostics':{'method':'family_proxy'}},'correlation_date,strategy_id_a,strategy_id_b')
    for i,a in enumerate(portfolios):
      for b in portfolios[i:]:
        corr=1.0 if a['id']==b['id'] else .65 if a.get('account_name')==b.get('account_name') else .35; c.upsert('portfolio_risk_matrix_v42',{'matrix_date':RUN_DATE,'portfolio_id_a':a['id'],'portfolio_id_b':b['id'],'correlation':corr,'overlap_score':100 if a['id']==b['id'] else 60 if corr>.6 else 25,'joint_stress_loss_pct':20 if a['id']==b['id'] else 14 if corr>.6 else 9,'risk_status':'WARNING' if corr>.6 and a['id']!=b['id'] else 'PASS','diagnostics':{}},'matrix_date,portfolio_id_a,portfolio_id_b')
    for p in portfolios:
      pid=str(p['id']); account=str(p.get('account_name') or 'paper-main'); compat=latest(c,'compat_portfolios_v40','latest_snapshot_date',f'portfolio_id=eq.{pid}'); risk=latest(c,'portfolio_risk_v41','risk_date',f'portfolio_id=eq.{pid}'); equity=n(compat.get('latest_equity'),n(p.get('starting_cash'),1000000)); vol=max(.01,n(risk.get('var_95_pct'),2)/100/1.65); worst=0
      for s in scenarios:
        loss=min(50,abs(n(s.get('equity_shock_pct')))*rm+vol*100*n(s.get('volatility_multiplier'),1)*2+n(s.get('correlation_shift'))*10); worst=max(worst,loss); c.upsert('scenario_results_v42',{'scenario_date':RUN_DATE,'scenario_id':s['id'],'portfolio_id':pid,'estimated_loss_pct':loss,'post_scenario_equity':equity*(1-loss/100),'risk_status':'CRITICAL' if loss>10 else 'WARNING' if loss>6 else 'PASS','diagnostics':{'regime':regime}},'scenario_date,scenario_id,portfolio_id'); srun+=1
      terminal=[]; breaches=0; ddlim=n(p.get('max_drawdown_pct'),12)
      for _ in range(PATHS):
        value=peak=equity; hit=False
        for __ in range(DAYS):
          value*=max(.01,1+random.gauss(.0003*rm,vol)); peak=max(peak,value); hit=hit or ((peak-value)/peak*100>ddlim if peak else False)
        terminal.append(value); breaches+=1 if hit else 0
      terminal.sort(); p5=terminal[max(0,int(len(terminal)*.05)-1)]; med=terminal[int(len(terminal)*.5)]; p95=terminal[min(len(terminal)-1,int(len(terminal)*.95))]; pb=breaches/len(terminal); status='CRITICAL' if pb>.25 else 'WARNING' if pb>.10 else 'PASS'; c.upsert('monte_carlo_runs_v42',{'run_date':RUN_DATE,'portfolio_id':pid,'paths':PATHS,'horizon_days':DAYS,'initial_equity':equity,'percentile_5_equity':p5,'median_equity':med,'percentile_95_equity':p95,'probability_of_loss':sum(1 for x in terminal if x<equity)/len(terminal),'probability_of_breach':pb,'expected_shortfall_pct':max(0,(equity-p5)/equity*100) if equity else 0,'status':status,'diagnostics':{'regime':regime}},'run_date,portfolio_id')
      weights=safe_get(c,'portfolio_target_weights_v32',f'account_name=eq.{account}&order=optimization_date.desc,target_weight.desc&limit=100'); latestd=str(weights[0]['optimization_date']) if weights else RUN_DATE; weights=[x for x in weights if str(x.get('optimization_date'))==latestd]; riskm=max(.25,min(1,1-n(risk.get('risk_score'))/140)); items=[]; turn=0
      for w in weights:
        base=n(w.get('target_weight')); target=min(n(p.get('max_position_pct'),15),base*rm*riskm); turn+=abs(target); c.upsert('dynamic_position_sizing_v42',{'sizing_date':RUN_DATE,'portfolio_id':pid,'symbol':str(w.get('symbol')),'base_weight':base,'regime_multiplier':rm,'risk_budget_multiplier':riskm,'final_target_weight':target,'action':'BUY' if target>1 else 'HOLD','rationale':f'Base {base:.2f}%, regime {regime}, risk {riskm:.2f}.'},'sizing_date,portfolio_id,symbol'); items.append((w,target))
      pstatus='BLOCKED' if status=='CRITICAL' or worst>10 else 'PROPOSED'; prop=c.upsert('rebalance_proposals_v42',{'proposal_date':RUN_DATE,'portfolio_id':pid,'proposal_status':pstatus,'gross_turnover_pct':turn,'estimated_cost':equity*turn/100*.001425,'target_cash_pct':max(0,100-sum(t for _,t in items)),'risk_before':n(risk.get('risk_score')),'risk_after':n(risk.get('risk_score'))*riskm,'requires_approval':True,'paper_only':True,'summary':f'{len(items)} item(s), regime {regime}, MC {status}, worst stress {worst:.2f}%.','blockers':(['MONTE_CARLO_CRITICAL'] if status=='CRITICAL' else [])+(['STRESS_LOSS_LIMIT'] if worst>10 else [])},'proposal_date,portfolio_id'); prid=prop[0]['id'] if prop else None
      for w,t in items: c.upsert('rebalance_items_v42',{'proposal_id':prid,'symbol':str(w.get('symbol')),'current_weight':0,'target_weight':t,'delta_weight':t,'action':'BUY' if t>1 else 'HOLD','estimated_trade_value':equity*t/100,'rationale':f'Adaptive target under {regime}.'},'proposal_id,symbol')
      props+=1; blockers += [f"portfolio:{p.get('portfolio_key')}:rebalance_blocked"] if pstatus=='BLOCKED' else []
    overall='CRITICAL' if blockers else 'PASS'; summary=f'Processed {len(portfolios)} portfolio(s), {len(strategies)} strategy(s), {srun} scenario(s), {props} proposal(s).'; c.upsert('adaptive_allocation_status_v42',{'status_date':RUN_DATE,'overall_status':overall,'portfolios_processed':len(portfolios),'strategies_processed':len(strategies),'scenarios_run':srun,'monte_carlo_runs':len(portfolios),'proposals_generated':props,'live_trading_enabled':False,'blockers':blockers,'summary':summary},'status_date'); c.insert('audit_logs_v40',{'actor_type':'SYSTEM','actor_key':'enterprise42-adaptive-allocation','action':'ADAPTIVE_ALLOCATION_COMPLETED','entity_type':'PORTFOLIO_ENGINE','entity_key':RUN_DATE,'severity':'CRITICAL' if blockers else 'INFO','metadata':{'overall_status':overall,'regime':regime,'summary':summary}}); print(summary)
if __name__=='__main__': main()
