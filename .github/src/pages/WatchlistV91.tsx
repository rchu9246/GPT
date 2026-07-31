import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { buildDecisionAlerts, formatNum, loadLatestSignals, ratingLabel } from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

const STORAGE_KEY = "gpt-quant-v91-watchlist";

export default function WatchlistV91({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [symbols, setSymbols] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as string[]; } catch { return []; }
  });
  useEffect(() => { loadLatestSignals().then(setSignals).catch(() => setSignals([])); }, []);
  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols)); }, [symbols]);
  const selected = signals.filter((row) => symbols.includes(row.symbol));
  const alerts = useMemo(() => buildDecisionAlerts(selected), [selected]);
  const toggle = (symbol: string) => setSymbols((current) => current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]);
  return <section>
    <div className="page-title"><div><div className="eyebrow">PERSONAL DECISION DESK</div><h1>自選監控</h1><p>保存關注標的、集中查看分數變化與風險警示。</p></div></div>
    <div className="cards"><MetricCard label="自選數量" value={String(selected.length)} note="儲存在目前瀏覽器" /><MetricCard label="警示數量" value={String(alerts.length)} note="依最新訊號產生" /><MetricCard label="平均 Score" value={formatNum(selected.length ? selected.reduce((sum,row)=>sum+row.score,0)/selected.length : 0)} note="自選清單品質" /><MetricCard label="高風險" value={String(selected.filter((row)=>row.risk_score>=60).length)} note="Risk ≥ 60" /></div>
    <div className="grid2"><div className="panel"><div className="panel-title">全部標的</div><div className="watch-grid">{signals.map((row)=><button className={`watch-chip ${symbols.includes(row.symbol)?"active":""}`} key={row.symbol} onClick={()=>toggle(row.symbol)}><strong>{row.symbol}</strong><span>{row.name ?? ""}</span><b>{formatNum(row.score)}</b></button>)}</div></div>
    <div className="panel"><div className="panel-title">自選警示</div><div className="alert-list">{alerts.map((alert)=><button className={`decision-alert severity-${alert.severity.toLowerCase()}`} key={alert.id} onClick={()=>alert.symbol && onOpenStock(alert.symbol)}><strong>{alert.title}</strong><span>{alert.message}</span></button>)}{!alerts.length && <p>加入自選後，這裡會顯示決策警示。</p>}</div></div></div>
    <div className="panel"><div className="panel-title">自選清單</div><div className="table-wrap"><table><thead><tr><th>股票</th><th>Score</th><th>評級</th><th>趨勢</th><th>風險</th><th>信心</th></tr></thead><tbody>{selected.map((row)=><tr className="clickable" key={row.symbol} onClick={()=>onOpenStock(row.symbol)}><td><strong>{row.symbol}</strong> {row.name ?? ""}</td><td>{formatNum(row.score)}</td><td>{ratingLabel(row.rating)}</td><td>{formatNum(row.trend_score)}</td><td>{formatNum(row.risk_score)}</td><td>{formatNum(row.confidence)}</td></tr>)}</tbody></table></div></div>
  </section>;
}
