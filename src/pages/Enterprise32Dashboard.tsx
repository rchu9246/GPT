import { useEffect,useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise32 } from "../lib/enterprise32";
import type { FactorRanking32,RiskSnapshot32,TargetWeight32 } from "../types/enterprise32";
export default function Enterprise32Dashboard(){
 const[factors,setFactors]=useState<FactorRanking32[]>([]);
 const[weights,setWeights]=useState<TargetWeight32[]>([]);
 const[risk,setRisk]=useState<RiskSnapshot32|null>(null);
 const[error,setError]=useState("");
 useEffect(()=>{loadEnterprise32().then(d=>{setFactors(d.factors);setWeights(d.weights);setRisk(d.risk)}).catch(e=>setError(e instanceof Error?e.message:"讀取失敗"))},[]);
 return <section>
  <div className="page-title"><div><div className="eyebrow">GPT QUANT ENTERPRISE 3.2 STABLE</div><h1>Factor, Portfolio & Risk Intelligence</h1><p>因子排名、風險調整權重、VaR、Expected Shortfall 與壓力測試。</p></div></div>
  {error&&<div className="alert">{error}</div>}
  <div className="cards">
   <MetricCard label="Risk Status" value={risk?.risk_status??"NO DATA"} note={`Score ${risk?.risk_score?.toFixed(1)??"0"}`}/>
   <MetricCard label="VaR 95%" value={`${risk?.var_95_pct?.toFixed(2)??"0"}%`} note={`ES ${risk?.expected_shortfall_pct?.toFixed(2)??"0"}%`}/>
   <MetricCard label="Stress Loss" value={`${risk?.stress_loss_pct?.toFixed(2)??"0"}%`} note={`MDD ${risk?.max_drawdown_pct?.toFixed(2)??"0"}%`}/>
   <MetricCard label="Exposure" value={`${risk?.gross_exposure_pct?.toFixed(1)??"0"}%`} note={`Concentration ${risk?.concentration_pct?.toFixed(1)??"0"}%`}/>
  </div>
  <div className="grid2">
   <div className="panel"><div className="panel-title">Factor Rankings</div>{factors.map(x=><div className="run-item" key={x.factor_key}><span>#{x.rank_position} {x.factor_key}</span><b>{x.quality_score.toFixed(1)}</b><small>{x.recommendation}</small></div>)}</div>
   <div className="panel"><div className="panel-title">Risk Breaches</div>{(risk?.breaches??[]).map(x=><div className="run-item" key={x}><span>{x}</span><b>REVIEW</b></div>)}{(risk?.breaches??[]).length===0&&<div className="run-item"><span>No active breach</span><b>PASS</b></div>}</div>
  </div>
  <div className="panel"><div className="panel-title">Optimized Target Weights</div><div className="table-wrap"><table><thead><tr><th>股票</th><th>動作</th><th>目標權重</th><th>風險貢獻</th><th>預期分數</th><th>理由</th></tr></thead><tbody>{weights.map(x=><tr key={x.symbol}><td><strong>{x.symbol}</strong></td><td>{x.action}</td><td>{x.target_weight.toFixed(2)}%</td><td>{x.risk_contribution.toFixed(2)}</td><td>{x.expected_return_score.toFixed(1)}</td><td>{x.rationale}</td></tr>)}</tbody></table></div></div>
 </section>
}
