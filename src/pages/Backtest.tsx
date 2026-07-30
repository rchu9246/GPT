import { useState } from "react";
import { simulatePosition, summarizeReturns } from "../engine/backtester";

export default function Backtest() {
  const [score,setScore]=useState(80);
  const [tp,setTp]=useState(7);
  const [sl,setSl]=useState(3);
  const [days,setDays]=useState(5);
  const [result,setResult]=useState<ReturnType<typeof summarizeReturns>|null>(null);

  const runDemo=()=>{
    const returns=[.021,-.011,.034,.052,-.018,.009,.041,-.007,.016,.027,-.012,.031];
    setResult(summarizeReturns(returns,1_000_000));
  };

  return <section>
    <div className="page-title"><h1>Backtest Lab</h1><p>正式接上 Edge Function 後，這些參數會驅動歷史資料回測。</p></div>
    <div className="panel form-grid">
      <label>最低 Score<input type="number" value={score} onChange={e=>setScore(+e.target.value)}/></label>
      <label>停利 %<input type="number" value={tp} onChange={e=>setTp(+e.target.value)}/></label>
      <label>停損 %<input type="number" value={sl} onChange={e=>setSl(+e.target.value)}/></label>
      <label>持有天數<input type="number" value={days} onChange={e=>setDays(+e.target.value)}/></label>
      <button className="primary" onClick={runDemo}>▶ 執行 MVP 回測</button>
    </div>
    {result && <div className="cards">
      <Metric title="總報酬" value={`${(result.totalReturn*100).toFixed(2)}%`} sub="Demo trades"/>
      <Metric title="勝率" value={`${(result.winRate*100).toFixed(1)}%`} sub="Net"/>
      <Metric title="Profit Factor" value={result.profitFactor.toFixed(2)} sub="Gross win / loss"/>
      <Metric title="最大回撤" value={`${(result.maxDrawdown*100).toFixed(2)}%`} sub="Equity peak-to-trough"/>
    </div>}
    <div className="panel"><div className="panel-title">目前設定</div><pre>{JSON.stringify({scoreThreshold:score,takeProfit:tp/100,stopLoss:sl/100,maxHoldingDays:days,entry:"T+1 Open",costs:"commission + tax + slippage"},null,2)}</pre></div>
  </section>
}
function Metric({title,value,sub}:{title:string,value:string,sub:string}) { return <div className="metric"><span>{title}</span><strong>{value}</strong><small>{sub}</small></div> }
