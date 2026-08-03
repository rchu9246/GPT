import { supabase } from "./supabase";
import type {CircuitBreaker41,PortfolioRisk41,RiskEvent41,RiskGovernorStatus41} from "../types/enterprise41";
export async function loadEnterprise41(){
 if(!supabase)return{status:null as RiskGovernorStatus41|null,portfolioRisks:[] as PortfolioRisk41[],breakers:[] as CircuitBreaker41[],events:[] as RiskEvent41[]};
 const[s,p,b,e]=await Promise.all([
  supabase.from("risk_governor_status_v41").select("*").order("status_date",{ascending:false}).limit(1).maybeSingle(),
  supabase.from("portfolio_risk_v41").select("*").order("risk_date",{ascending:false}).order("risk_score",{ascending:false}).limit(50),
  supabase.from("circuit_breakers_v41").select("*").order("breaker_status",{ascending:true}).limit(100),
  supabase.from("risk_events_v41").select("*").order("event_date",{ascending:false}).limit(100)
 ]);
 const err=s.error??p.error??b.error??e.error;if(err)throw err;
 const status=s.data?{...s.data,overall_risk_score:Number(s.data.overall_risk_score??0),active_breakers:Number(s.data.active_breakers??0),open_critical_events:Number(s.data.open_critical_events??0),open_warning_events:Number(s.data.open_warning_events??0),portfolios_checked:Number(s.data.portfolios_checked??0),strategies_checked:Number(s.data.strategies_checked??0),blockers:Array.isArray(s.data.blockers)?s.data.blockers:[]} as RiskGovernorStatus41:null;
 const portfolioRisks=(p.data??[]).map(x=>({...x,equity:Number(x.equity??0),gross_exposure_pct:Number(x.gross_exposure_pct??0),var_95_pct:Number(x.var_95_pct??0),expected_shortfall_pct:Number(x.expected_shortfall_pct??0),max_drawdown_pct:Number(x.max_drawdown_pct??0),concentration_pct:Number(x.concentration_pct??0),risk_score:Number(x.risk_score??0),breaches:Array.isArray(x.breaches)?x.breaches:[]})) as PortfolioRisk41[];
 const breakers=(b.data??[]).map(x=>({...x,trigger_count:Number(x.trigger_count??0)})) as CircuitBreaker41[];
 const events=(e.data??[]) as RiskEvent41[];
 return{status,portfolioRisks,breakers,events};
}
