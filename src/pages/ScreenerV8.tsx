import { useEffect, useState } from "react";
import { formatNum, loadLatestSignals, ratingLabel } from "../lib/v8Data";
import type { SignalRow } from "../types/v8";

export default function ScreenerV8({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [minScore, setMinScore] = useState(35);
  useEffect(() => { loadLatestSignals().then(setRows).catch(() => setRows([])); }, []);
  const filtered = rows.filter((row) => Number(row.score ?? 0) >= minScore);

  return (
    <section>
      <div className="page-title"><div><div className="eyebrow">V8 SCREENER</div><h1>AI 選股中心</h1><p>依 Score、AI 評級與風險篩選去重標的。</p></div></div>
      <div className="panel filter-panel"><label>最低 Score：<strong>{minScore}</strong></label><input type="range" min="0" max="100" value={minScore} onChange={(event) => setMinScore(Number(event.target.value))} /></div>
      <div className="panel"><div className="table-wrap"><table><thead><tr><th>股票</th><th>Score</th><th>評級</th><th>趨勢</th><th>動能</th><th>風險</th><th>信心</th></tr></thead><tbody>{filtered.map((row) => <tr className="clickable" key={row.symbol} onClick={() => onOpenStock(row.symbol)}><td><strong>{row.symbol}</strong> {row.name ?? ""}</td><td>{formatNum(row.score)}</td><td>{ratingLabel(row.rating)}</td><td>{formatNum(row.trend_score)}</td><td>{formatNum(row.momentum_score)}</td><td>{formatNum(row.risk_score)}</td><td>{formatNum(row.confidence)}</td></tr>)}</tbody></table></div></div>
    </section>
  );
}
