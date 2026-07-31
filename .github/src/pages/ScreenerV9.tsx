import { useEffect, useState } from "react";
import { formatNum, loadLatestSignals, ratingLabel } from "../lib/v9Data";
import type { SignalRow } from "../types/v9";
export default function ScreenerV9({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
  const [rows, setRows] = useState<SignalRow[]>([]); const [minScore, setMinScore] = useState(35); const [maxRisk, setMaxRisk] = useState(70);
  useEffect(() => { loadLatestSignals().then(setRows).catch(() => setRows([])); }, []);
  const filtered = rows.filter((row) => row.score >= minScore && row.risk_score <= maxRisk);
  return <section><div className="page-title"><div><div className="eyebrow">ENTERPRISE SCREENER</div><h1>多因子選股中心</h1><p>同時控制最低分數與最高風險。</p></div></div><div className="panel filter-grid"><label>最低 Score <strong>{minScore}</strong><input type="range" min="0" max="100" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} /></label><label>最高 Risk <strong>{maxRisk}</strong><input type="range" min="0" max="100" value={maxRisk} onChange={(e) => setMaxRisk(Number(e.target.value))} /></label></div><div className="panel"><div className="table-wrap"><table><thead><tr><th>股票</th><th>Score</th><th>評級</th><th>趨勢</th><th>動能</th><th>品質</th><th>風險</th><th>信心</th></tr></thead><tbody>{filtered.map((row) => <tr key={row.symbol} className="clickable" onClick={() => onOpenStock(row.symbol)}><td><strong>{row.symbol}</strong> {row.name ?? ""}</td><td>{formatNum(row.score)}</td><td>{ratingLabel(row.rating)}</td><td>{formatNum(row.trend_score)}</td><td>{formatNum(row.momentum_score)}</td><td>{formatNum(row.quality_score)}</td><td>{formatNum(row.risk_score)}</td><td>{formatNum(row.confidence)}</td></tr>)}</tbody></table></div></div></section>;
}
