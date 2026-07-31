import { useEffect, useMemo, useState } from "react";
import { compareScore, formatNum, loadLatestSignals, ratingLabel } from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

export default function CompareV91({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [left, setLeft] = useState(""); const [right, setRight] = useState("");
  useEffect(()=>{ loadLatestSignals().then((rows)=>{ setSignals(rows); setLeft(rows[0]?.symbol ?? ""); setRight(rows[1]?.symbol ?? rows[0]?.symbol ?? ""); }).catch(()=>setSignals([])); },[]);
  const a=signals.find((row)=>row.symbol===left); const b=signals.find((row)=>row.symbol===right);
  const winner=useMemo(()=>a&&b?(compareScore(a,b)>=0?a:b):undefined,[a,b]);
  const metrics: Array<[string, keyof SignalRow]> = [["Score","score"],["趨勢","trend_score"],["動能","momentum_score"],["量能","volume_score"],["品質","quality_score"],["信心","confidence"]];
  return <section><div className="page-title"><div><div className="eyebrow">PAIRWISE INTELLIGENCE</div><h1>個股比較</h1><p>用風險調整分數比較兩檔標的。</p></div></div>
    <div className="panel compare-selectors"><select value={left} onChange={(e)=>setLeft(e.target.value)}>{signals.map((row)=><option key={row.symbol} value={row.symbol}>{row.symbol} {row.name ?? ""}</option>)}</select><span>VS</span><select value={right} onChange={(e)=>setRight(e.target.value)}>{signals.map((row)=><option key={row.symbol} value={row.symbol}>{row.symbol} {row.name ?? ""}</option>)}</select></div>
    {a&&b&&<><div className="comparison-grid"><article className={`compare-card ${winner?.symbol===a.symbol?"winner":""}`} onClick={()=>onOpenStock(a.symbol)}><h2>{a.symbol} {a.name ?? ""}</h2><span className="rating">{ratingLabel(a.rating)}</span>{metrics.map(([label,key])=><div className="compare-metric" key={String(key)}><span>{label}</span><strong>{formatNum(Number(a[key]))}</strong></div>)}<div className="compare-metric risk"><span>風險</span><strong>{formatNum(a.risk_score)}</strong></div></article>
    <article className={`compare-card ${winner?.symbol===b.symbol?"winner":""}`} onClick={()=>onOpenStock(b.symbol)}><h2>{b.symbol} {b.name ?? ""}</h2><span className="rating">{ratingLabel(b.rating)}</span>{metrics.map(([label,key])=><div className="compare-metric" key={String(key)}><span>{label}</span><strong>{formatNum(Number(b[key]))}</strong></div>)}<div className="compare-metric risk"><span>風險</span><strong>{formatNum(b.risk_score)}</strong></div></article></div>
    <div className="panel decision-winner"><div className="eyebrow">風險調整結果</div><h2>{winner?.symbol} 較具優勢</h2><p>比較公式綜合 Score、Risk 與 Confidence，僅作研究排序使用。</p></div></>}</section>;
}
