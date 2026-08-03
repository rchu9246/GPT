import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { formatNum, loadLatestSignals, marketIntelligence, optimizePortfolio } from "../lib/v9Data";
import type { SignalRow } from "../types/v9";
export default function PortfolioV9() {
  const [signals, setSignals] = useState<SignalRow[]>([]); useEffect(() => { loadLatestSignals().then(setSignals).catch(() => setSignals([])); }, []);
  const allocations = useMemo(() => optimizePortfolio(signals), [signals]); const intel = useMemo(() => marketIntelligence(signals), [signals]);
  const weightedRisk = allocations.reduce((sum, row) => sum + row.riskContribution, 0); const concentration = allocations.reduce((sum, row) => sum + row.weight ** 2, 0); const cash = intel.regime === "RISK_OFF" ? 35 : intel.regime === "NEUTRAL" ? 25 : 15;
  return <section><div className="page-title"><div><div className="eyebrow">PORTFOLIO OPERATING SYSTEM</div><h1>投資組合管理</h1><p>風險調整權重、集中度與現金緩衝。</p></div></div><div className="cards"><MetricCard label="持股數" value={allocations.length} note="最多 8 檔" /><MetricCard label="加權風險" value={formatNum(weightedRisk)} note="權重 × Risk" /><MetricCard label="集中度 HHI" value={formatNum(concentration, 3)} note="越低越分散" /><MetricCard label="現金緩衝" value={`${cash}%`} note="依市場狀態調整" /></div><div className="panel"><div className="panel-title">最佳化權重</div><div className="allocation-list">{allocations.map((row) => <div className="allocation-row" key={row.symbol}><div><strong>{row.symbol}</strong><small>{row.name ?? ""}</small></div><div className="allocation-bar"><i style={{ width: `${row.weight * 100}%` }} /></div><b>{(row.weight * 100).toFixed(1)}%</b></div>)}</div></div><div className="panel"><div className="panel-title">投資組合規則</div><div className="risk-rules"><span>單股上限 20%</span><span>高風險市場提高現金</span><span>Score 低於 30 排除</span><span>每日監控、每週再平衡</span></div></div></section>;
}
