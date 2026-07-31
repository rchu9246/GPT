import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import {
  formatNum,
  loadLatestSignals,
  marketIntelligence,
  optimizePortfolio,
  scenarioLoss,
} from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

export default function PortfolioOSV11() {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const intelligence = useMemo(() => marketIntelligence(signals), [signals]);
  const allocations = useMemo(() => optimizePortfolio(signals, 8), [signals]);
  const cash =
    intelligence.regime === "RISK_OFF"
      ? 45
      : intelligence.regime === "NEUTRAL"
        ? 30
        : 15;
  const hhi = allocations.reduce((sum, row) => sum + row.weight ** 2, 0);
  const weightedRisk = allocations.reduce(
    (sum, row) => sum + row.weight * row.risk_score,
    0,
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">PORTFOLIO OPERATING SYSTEM</div>
          <h1>Portfolio OS</h1>
          <p>風險預算、集中度、情境損失與再平衡建議。</p>
        </div>
      </div>

      <div className="cards">
        <MetricCard label="建議現金" value={`${cash}%`} note="依市場狀態調整" />
        <MetricCard label="加權風險" value={formatNum(weightedRisk)} note="持股風險加權" />
        <MetricCard label="集中度 HHI" value={formatNum(hhi, 3)} note="越高越集中" />
        <MetricCard label="-10% 情境損失" value={`${scenarioLoss(allocations, -10).toFixed(1)}%`} note="模型壓力測試" />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">風險調整配置</div>
          <div className="allocation-list">
            {allocations.map((row) => (
              <div className="allocation-row" key={row.symbol}>
                <div><strong>{row.symbol}</strong><small>{row.name ?? ""}</small></div>
                <div className="allocation-bar"><i style={{ width: `${row.weight * 100}%` }} /></div>
                <b>{(row.weight * 100).toFixed(1)}%</b>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">再平衡規則</div>
          <div className="regime"><span>單股上限</span><strong>20%</strong></div>
          <div className="regime"><span>高風險標的上限</span><strong>5%</strong></div>
          <div className="regime"><span>再平衡頻率</span><strong>每週</strong></div>
          <div className="regime"><span>觸發門檻</span><strong>偏離 25%</strong></div>
          <p className="report-summary">
            權重是依 Score、Risk 與 Confidence 產生的研究配置，不等同實際交易委託。
          </p>
        </div>
      </div>
    </section>
  );
}
