import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { formatNum, loadLatestSignals, marketIntelligence, ratingLabel, regimeLabel } from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

export default function CommandCenterV9({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => { loadLatestSignals().then(setSignals).catch((err: unknown) => setError(err instanceof Error ? err.message : "資料讀取失敗")).finally(() => setLoading(false)); }, []);
  const intel = useMemo(() => marketIntelligence(signals), [signals]);
  return <section>
    <div className="hero"><div><div className="eyebrow">GPT QUANT V9 · ENTERPRISE COMMAND CENTER</div><h1>投資決策指揮中心</h1><p>市場狀態、去重訊號、策略風險與執行優先級整合。</p></div><div className="health"><span>系統健康度</span><strong>{Math.round(intel.health)}</strong><small>/100</small><div className="health-bar"><i style={{ width: `${intel.health}%` }} /></div></div></div>
    {error && <div className="alert">{error}</div>}
    <div className="cards"><MetricCard label="市場狀態" value={loading ? "讀取中" : regimeLabel(intel.regime)} note="由廣度、分數與風險綜合判定" /><MetricCard label="最新交易日" value={signals.length ? signals[0].trade_date : "—"} note="Supabase 最新同步日" /><MetricCard label="偏多標的" value={intel.bullishCount} note="偏多以上 AI 評級" /><MetricCard label="風險警示" value={intel.warningCount} note="高風險或避開標的" /></div>
    <div className="grid-main"><div className="panel"><div className="panel-title">企業級訊號排行榜</div><div className="table-wrap"><table><thead><tr><th>#</th><th>股票</th><th>Score</th><th>評級</th><th>趨勢</th><th>動能</th><th>品質</th><th>風險</th></tr></thead><tbody>{signals.map((row, index) => <tr key={row.symbol} className="clickable" onClick={() => onOpenStock(row.symbol)}><td>{index + 1}</td><td><strong>{row.symbol}</strong> {row.name ?? ""}</td><td>{formatNum(row.score)}</td><td><span className={`rating rating-${row.rating.toLowerCase()}`}>{ratingLabel(row.rating)}</span></td><td>{formatNum(row.trend_score)}</td><td>{formatNum(row.momentum_score)}</td><td>{formatNum(row.quality_score)}</td><td>{formatNum(row.risk_score)}</td></tr>)}</tbody></table></div></div>
    <aside><div className="panel"><div className="panel-title">市場情報</div><div className="regime"><span>平均 Score</span><strong>{formatNum(intel.averageScore)}</strong></div><div className="regime"><span>平均風險</span><strong>{formatNum(intel.averageRisk)}</strong></div><div className="regime"><span>市場廣度</span><strong>{Math.round(intel.breadth * 100)}%</strong></div><div className="regime"><span>標的數</span><strong>{signals.length}</strong></div></div><div className="panel"><div className="panel-title">執行優先級</div><ol className="decision-list"><li>先確認市場狀態與系統健康度。</li><li>選擇高品質、低風險且信心充足的標的。</li><li>進入個股頁檢查趨勢與停損。</li><li>最後由風險中心決定總曝險。</li></ol></div></aside></div>
  </section>;
}
