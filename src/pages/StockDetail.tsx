import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import type { Signal } from "../types/quant";

export default function StockDetail({symbol,onBack}:{symbol:string,onBack:()=>void}) {
  const [signal,setSignal]=useState<Signal|null>(null);
  useEffect(()=>{
    if (!supabase) return;
    supabase.from("signals").select("*, stocks(symbol,name,industry)")
      .eq("stocks.symbol",symbol).order("trade_date",{ascending:false}).limit(1)
      .then(({data})=>setSignal((data?.[0] as unknown as Signal)||null));
  },[symbol]);
  const s=signal;
  return <section>
    <button className="back" onClick={onBack}>← 返回</button>
    <div className="hero"><div><div className="eyebrow">STOCK DETAIL</div><h1>{symbol} {s?.stocks?.name||"股票分析"}</h1><p>{s?.stocks?.industry||"等待 Supabase 訊號資料"}</p></div><div className="score-big">{s?.total_score??"—"}</div></div>
    <div className="panel"><div className="panel-title">Score Breakdown</div>
      {[
        ["Trend",s?.trend_score],["Momentum",s?.momentum_score],["Volume",s?.volume_score],
        ["Institutional",s?.institutional_score],["Breakout",s?.breakout_score],
        ["Relative Strength",s?.relative_strength_score],["Market",s?.market_score],["Risk",s?.risk_score]
      ].map(([n,v])=><div className="barrow" key={String(n)}><span>{n}</span><div className="bar"><i style={{width:`${Number(v)||0}%`}}/></div><b>{v??"—"}</b></div>)}
    </div>
    <div className="grid2">
      <div className="panel"><div className="panel-title">為什麼入選？</div><ul className="reasons"><li>趨勢、動能、法人、量價特徵整合</li><li>相對大盤強弱納入評分</li><li>市場 Regime 作為總體濾網</li><li>風險分數獨立計算，不把高波動誤判成強勢</li></ul></div>
      <div className="panel"><div className="panel-title">歷史結果</div><p className="muted">signal_outcomes 建立後，這裡會顯示 T+1 / T+3 / T+5 / T+20 勝率與平均報酬。</p></div>
    </div>
  </section>
}
