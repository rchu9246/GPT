import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadPaperOperationsV14, moneyV14, percentV14 } from "../lib/v14Operations";
import type { PaperOperationsV14 } from "../types/v14";
const EMPTY: PaperOperationsV14 = { account:null, positions:[], orders:[], fills:[], snapshots:[], runs:[] };
export default function AutoPortfolioV15(){
 const [data,setData]=useState<PaperOperationsV14>(EMPTY); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
 useEffect(()=>{loadPaperOperationsV14().then(setData).catch((e)=>setError(e instanceof Error?e.message:"讀取失敗")).finally(()=>setLoading(false));},[]);
 const proposed=data.orders.filter(x=>x.status==="PROPOSED"); const approved=data.orders.filter(x=>x.status==="APPROVED"); const filled=data.orders.filter(x=>x.status==="FILLED");
 const allocated=data.positions.reduce((s,x)=>s+x.market_value,0); const equity=data.account?.equity??0; const rate=equity>0?allocated/equity:0;
 const funnel=[['最新委託',data.orders.length],['待核准',proposed.length],['已核准',approved.length],['已成交',filled.length],['目前持倉',data.positions.length]] as const;
 return <section>
  <div className="page-title"><div><div className="eyebrow">V15 AUTO PORTFOLIO</div><h1>自動投資組合閉環</h1><p>Signal → Proposed → Approval → Fill → Position → P/L。</p></div></div>
  {error&&<div className="alert">{error}</div>}
  <div className="cards"><MetricCard label="待核准委託" value={String(proposed.length)} note="PROPOSED"/><MetricCard label="待成交委託" value={String(approved.length)} note="APPROVED"/><MetricCard label="投資比例" value={percentV14(rate)} note={moneyV14(allocated)}/><MetricCard label="帳戶淨值" value={moneyV14(data.account?.equity)} note={loading?"讀取中":"Paper Account"}/></div>
  <div className="panel"><div className="panel-title">交易生命週期</div><div className="v15-funnel">{funnel.map(([label,value],i)=><div className="v15-funnel-step" key={label}><b>{value}</b><span>{label}</span>{i<funnel.length-1&&<i>→</i>}</div>)}</div></div>
  <div className="grid2"><div className="panel"><div className="panel-title">最新候選委託</div><div className="table-wrap"><table><thead><tr><th>股票</th><th>方向</th><th>數量</th><th>參考價</th><th>Score</th><th>狀態</th></tr></thead><tbody>{data.orders.slice(0,20).map(x=><tr key={x.id}><td><strong>{x.symbol}</strong></td><td>{x.side}</td><td>{x.quantity}</td><td>{moneyV14(x.reference_price)}</td><td>{x.score?.toFixed(1)??'—'}</td><td>{x.status}</td></tr>)}</tbody></table></div></div>
  <div className="panel"><div className="panel-title">目前投資組合</div><div className="run-list">{data.positions.map(x=><div className="run-item" key={x.symbol}><span>{x.symbol} {x.name??''}</span><b>{moneyV14(x.market_value)}</b><small>{x.quantity} 股 · 未實現 {moneyV14(x.unrealized_pnl)}</small></div>)}</div></div></div>
  <div className="panel"><div className="panel-title">操作順序</div><div className="execution-step"><b>1</b><span>Actions → V15 Generate Proposed Orders</span></div><div className="execution-step"><b>2</b><span>Actions → V14.5 Review Paper Order</span></div><div className="execution-step"><b>3</b><span>Actions → V14.5 Fill Approved Orders</span></div><div className="execution-step"><b>4</b><span>回到本頁查看持倉、現金與損益</span></div></div>
 </section>;
}
