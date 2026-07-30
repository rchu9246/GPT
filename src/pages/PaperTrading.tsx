import { useState } from "react";
export default function PaperTrading(){
  const [enabled,setEnabled]=useState(false);
  return <section>
    <div className="page-title"><h1>紙上交易</h1><p>只模擬，不送出真實券商委託。</p></div>
    <div className="panel">
      <div className="switchrow"><span>模擬交易引擎</span><button className={enabled?"toggle on":"toggle"} onClick={()=>setEnabled(!enabled)}>{enabled?"ON":"OFF"}</button></div>
      <div className="grid2">
        <div><h3>策略</h3><p>Score ≥ 80 · T+1 開盤進場 · TP 7% · SL 3% · 最長 5 日</p></div>
        <div><h3>狀態</h3><p>{enabled?"🟢 模擬中":"⚪ 尚未啟用"}</p></div>
      </div>
    </div>
  </section>
}
