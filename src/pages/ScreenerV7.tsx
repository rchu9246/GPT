import { useEffect, useState } from "react";
import { loadLatestSignals, formatNum } from "../lib/v7Data";
import type { SignalRow } from "../types/v7";
export default function ScreenerV7({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [minScore, setMinScore] = useState(40);
  useEffect(() => { loadLatestSignals().then(setRows).catch(() => setRows([])); }, []);
  const filtered = rows.filter(r => Number(r.score ?? 0) >= minScore);
  return <section>
    <div className="page-title"><div><div className="eyebrow">SCREENER</div><h1>選股中心</h1><p>依多因子分數快速篩選候選標的。</p></div></div>
    <div className="panel filter-panel"><label>最低 Score：<strong>{minScore}</strong></label><input type="range" min="0" max="100" value={minScore} onChange={e => setMinScore(Number(e.target.value))}/></div>
    <div className="panel"><div className="table-wrap"><table><thead><tr><th>股票</th><th>Score</th><th>趨勢</th><th>動能</th><th>風險</th><th>信心</th></tr></thead>
    <tbody>{filtered.map(r => <tr className="clickable" key={r.symbol} onClick={() => onOpenStock(r.symbol)}><td><strong>{r.symbol}</strong> {r.name ?? ""}</td><td>{formatNum(r.score)}</td><td>{formatNum(r.trend_score)}</td><td>{formatNum(r.momentum_score)}</td><td>{formatNum(r.risk_score)}</td><td>{formatNum(r.confidence)}</td></tr>)}</tbody></table></div></div>
  </section>;
}
