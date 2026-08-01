import { useEffect,useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise41 } from "../lib/enterprise41";
import type {CircuitBreaker41,PortfolioRisk41,RiskEvent41,RiskGovernorStatus41} from "../types/enterprise41";
export default function Enterprise41RiskCenter(){
 const[status,setStatus]=useState<RiskGovernorStatus41|null>(null);
 const[portfolioRisks,setPortfolioRisks]=useState<PortfolioRisk41[]>([]);
 const[breakers,setBreakers]=useState<CircuitBreaker41[]>([]);
 const[events,setEvents]=useState<RiskEvent41[]>([]);
 const[error,setError]=useState("");
 useEffect(()=>{loadEnterprise41().then(d=>{setStatus(d.status);setPortfolioRisks(d.portfolioRisks);setBreakers(d.breakers);setEvents(d.events)}).catch(e=>setError(e instanceof Error?e.message:"讀取失敗"))},[]);
 return <section>
  <div className="page-title"><div><div className="eyebrow">GPT QUANT ENTERPRISE 4.1 STABLE</div><h1>Central Risk Governor</h1><p>Portfolio、Strategy、Circuit Breaker、VaR、ES、集中度與回撤治理。</p></div></div>
  {error&&<div className="alert">{error}</div>}
  <div className="panel"><div className="panel-title">Risk Governor Status</div><h1>{status?.overall_status??"NO DATA"}</h1><p>{status?.summary??"尚未執行 Enterprise 4.1 Daily Risk Monitor"}</p></div>
  <div className="cards">
   <MetricCard label="Risk Score" value={status?.overall_risk_score?.toFixed(1)??"0"} note="0–100"/>
   <MetricCard label="Active Breakers" value={String(status?.active_breakers??0)} note={`${breakers.length} configured`}/>
   <MetricCard label="Critical Events" value={String(status?.open_critical_events??0)} note={`${status?.open_warning_events??0} warnings`}/>
   <MetricCard label="Coverage" value={`${status?.portfolios_checked??0} / ${status?.strategies_checked??0}`} note="Portfolios / Strategies"/>
  </div>
  <div className="grid2">
   <div className="panel"><div className="panel-title">Circuit Breakers</div>{breakers.map(x=><div className="run-item" key={x.id}><span>{x.breaker_key}</span><b>{x.breaker_status}</b><small>{x.scope_type} · {x.trigger_action}</small></div>)}</div>
   <div className="panel"><div className="panel-title">Open Risk Events</div>{events.filter(x=>x.event_status==="OPEN").map(x=><div className="run-item" key={x.id}><span>{x.limit_key??x.event_type}</span><b>{x.severity}</b><small>{x.message}</small></div>)}</div>
  </div>
  <div className="panel"><div className="panel-title">Portfolio Risk</div><div className="table-wrap"><table><thead><tr><th>日期</th><th>狀態</th><th>Risk Score</th><th>Equity</th><th>Exposure</th><th>VaR</th><th>ES</th><th>Drawdown</th><th>Concentration</th></tr></thead><tbody>{portfolioRisks.map(x=><tr key={x.id}><td>{x.risk_date}</td><td>{x.risk_status}</td><td>{x.risk_score.toFixed(1)}</td><td>{x.equity.toFixed(0)}</td><td>{x.gross_exposure_pct.toFixed(2)}%</td><td>{x.var_95_pct.toFixed(2)}%</td><td>{x.expected_shortfall_pct.toFixed(2)}%</td><td>{x.max_drawdown_pct.toFixed(2)}%</td><td>{x.concentration_pct.toFixed(2)}%</td></tr>)}</tbody></table></div></div>
 </section>
}
