import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import type { Signal } from "../types/quant";

export default function Screener() {
  const [min,setMin]=useState(80);
  const [rows,setRows]=useState<Signal[]>([]);
  useEffect(()=>{
    if (!supabase) return;
    supabase.from("signals").select("*, stocks(symbol,name,industry)")
      .gte("total_score",min).order("total_score",{ascending:false}).limit(100)
      .then(({data})=>setRows((data||[]) as unknown as Signal[]));
  },[min]);
  return <section>
    <PageTitle title="選股器" desc="以 0～100 Score 排序，先看訊號品質，再看原因。"/>
    <div className="toolbar"><label>最低 Score <input type="number" min="0" max="100" value={min} onChange={e=>setMin(+e.target.value)}/></label><span>目前 {rows.length} 檔</span></div>
    <div className="panel"><div className="table-wrap"><table><thead><tr><th>股票</th><th>Score</th><th>Trend</th><th>Momentum</th><th>法人</th><th>突破</th><th>Risk</th></tr></thead>
    <tbody>{rows.map(r=><tr key={r.id}><td><b>{r.stocks?.symbol}</b> {r.stocks?.name}</td><td><strong>{r.total_score}</strong></td><td>{r.trend_score}</td><td>{r.momentum_score}</td><td>{r.institutional_score}</td><td>{r.breakout_score}</td><td>{r.risk_score}</td></tr>)}</tbody></table></div></div>
  </section>
}
function PageTitle({title,desc}:{title:string,desc:string}) { return <div className="page-title"><h1>{title}</h1><p>{desc}</p></div> }
