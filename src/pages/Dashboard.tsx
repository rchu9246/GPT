import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import type { Signal } from "../types/quant";

const demo: Signal[] = [
  {id:1,stock_id:1,trade_date:"2026-07-30",strategy_version:"V2.0",total_score:94.2,trend_score:96,momentum_score:91,volume_score:93,institutional_score:98,breakout_score:89,relative_strength_score:94,market_score:92,risk_score:76,signal:"S級強多",confidence:87,stocks:{symbol:"2330",name:"台積電",industry:"半導體"}},
  {id:2,stock_id:2,trade_date:"2026-07-30",strategy_version:"V2.0",total_score:91.4,trend_score:94,momentum_score:88,volume_score:90,institutional_score:91,breakout_score:92,relative_strength_score:89,market_score:92,risk_score:82,signal:"S級強多",confidence:84,stocks:{symbol:"2454",name:"聯發科",industry:"半導體"}},
  {id:3,stock_id:3,trade_date:"2026-07-30",strategy_version:"V2.0",total_score:87.6,trend_score:90,momentum_score:86,volume_score:84,institutional_score:88,breakout_score:81,relative_strength_score:90,market_score:92,risk_score:78,signal:"A級多頭",confidence:81,stocks:{symbol:"2382",name:"廣達",industry:"電腦週邊"}}
];

export default function Dashboard() {
  const [signals,setSignals] = useState<Signal[]>(demo);
  const [connected,setConnected] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    supabase.from("signals").select("*, stocks(symbol,name,industry)")
      .order("total_score",{ascending:false}).limit(10)
      .then(({data,error}) => {
        if (!error && data?.length) { setSignals(data as unknown as Signal[]); setConnected(true); }
      });
  },[]);

  return <section>
    <div className="hero">
      <div><div className="eyebrow">QUANT TRADING CENTER</div><h1>今日策略總覽</h1><p>{connected ? "Supabase 已連線" : "目前使用 Demo 資料；設定 Supabase 環境變數後自動切換真實資料"}</p></div>
      <div className="health"><span>策略健康度</span><strong>84</strong><small> / 100 · 🟢 HEALTHY</small></div>
    </div>

    <div className="cards">
      <Metric title="市場狀態" value="🟢 偏多" sub="TAIEX / SOX / Nasdaq"/>
      <Metric title="今日候選" value="17" sub="Score ≥ 70"/>
      <Metric title="S級強多" value="5" sub="Score ≥ 90"/>
      <Metric title="風險警示" value="6" sub="需人工檢視"/>
    </div>

    <div className="grid2">
      <div className="panel">
        <div className="panel-title">🚀 今日 TOP 訊號</div>
        <div className="table-wrap"><table><thead><tr><th>排名</th><th>股票</th><th>Score</th><th>訊號</th><th>Confidence</th></tr></thead>
        <tbody>{signals.map((s,i)=><tr key={s.id} onClick={()=>location.hash=`#/stock/${s.stocks?.symbol}`} className="clickable">
          <td>{i+1}</td><td><b>{s.stocks?.symbol}</b> {s.stocks?.name}</td><td><strong>{s.total_score}</strong></td><td>{s.signal}</td><td>{s.confidence}%</td>
        </tr>)}</tbody></table></div>
      </div>
      <div className="panel">
        <div className="panel-title">🌎 Market Regime</div>
        <Regime name="TAIEX" state="🟢 多頭" />
        <Regime name="SOX" state="🟢 多頭" />
        <Regime name="Nasdaq" state="🟢 多頭" />
        <Regime name="USD/TWD" state="🟡 中性" />
        <Regime name="Strategy" state="🟢 Healthy" />
      </div>
    </div>
  </section>
}

function Metric({title,value,sub}:{title:string,value:string,sub:string}) {
  return <div className="metric"><span>{title}</span><strong>{value}</strong><small>{sub}</small></div>
}
function Regime({name,state}:{name:string,state:string}) {
  return <div className="regime"><span>{name}</span><b>{state}</b></div>
}
