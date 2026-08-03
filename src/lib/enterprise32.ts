import { supabase } from "./supabase";
import type { FactorRanking32,RiskSnapshot32,TargetWeight32 } from "../types/enterprise32";
export async function loadEnterprise32(accountName="paper-main"){
 if(!supabase)return{factors:[] as FactorRanking32[],weights:[] as TargetWeight32[],risk:null as RiskSnapshot32|null};
 const[f,w,r]=await Promise.all([
  supabase.from("factor_rankings_v32").select("*").eq("account_name",accountName).order("ranking_date",{ascending:false}).order("rank_position",{ascending:true}).limit(50),
  supabase.from("portfolio_target_weights_v32").select("*").eq("account_name",accountName).order("optimization_date",{ascending:false}).order("target_weight",{ascending:false}).limit(50),
  supabase.from("risk_snapshots_v32").select("*").eq("account_name",accountName).order("snapshot_date",{ascending:false}).limit(1).maybeSingle()
 ]);
 const e=f.error??w.error??r.error;if(e)throw e;
 const factors=(f.data??[]).map(x=>({...x,rank_position:Number(x.rank_position??0),quality_score:Number(x.quality_score??0),stability_score:x.stability_score==null?null:Number(x.stability_score)})) as FactorRanking32[];
 const weights=(w.data??[]).map(x=>({...x,target_weight:Number(x.target_weight??0),risk_contribution:Number(x.risk_contribution??0),expected_return_score:Number(x.expected_return_score??0)})) as TargetWeight32[];
 const risk=r.data?{...r.data,gross_exposure_pct:Number(r.data.gross_exposure_pct??0),var_95_pct:Number(r.data.var_95_pct??0),expected_shortfall_pct:Number(r.data.expected_shortfall_pct??0),max_drawdown_pct:Number(r.data.max_drawdown_pct??0),stress_loss_pct:Number(r.data.stress_loss_pct??0),concentration_pct:Number(r.data.concentration_pct??0),liquidity_score:Number(r.data.liquidity_score??0),risk_score:Number(r.data.risk_score??0),breaches:Array.isArray(r.data.breaches)?r.data.breaches:[]} as RiskSnapshot32:null;
 return{factors,weights,risk};
}
