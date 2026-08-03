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

function portfolioVaR(risk: number, confidenceMultiplier: number): number {
  return Math.max(0, (risk / 100) * confidenceMultiplier * 10);
}

export default function RiskAnalyticsV12() {
  const [signals, setSignals] = useState<SignalRow[]>([]);

  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const intelligence = useMemo(() => marketIntelligence(signals), [signals]);
  const allocations = useMemo(() => optimizePortfolio(signals, 8), [signals]);
  const weightedRisk = allocations.reduce(
    (sum, row) => sum + row.weight * row.risk_score,
    0,
  );
  const var95 = portfolioVaR(weightedRisk, 1.65);
  const cvar95 = var95 * 1.35;
  const hhi = allocations.reduce((sum, row) => sum + row.weight ** 2, 0);
  const concentration = hhi >= 0.25 ? "集中" : hhi >= 0.16 ? "中等" : "分散";

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V12 ADVANCED RISK ANALYTICS</div>
          <h1>進階風險分析</h1>
          <p>VaR、CVaR、集中度與市場情境損失的研究估算。</p>
        </div>
      </div>

      <div className="cards">
        <MetricCard label="模型 VaR 95%" value={`${var95.toFixed(1)}%`} note="代理估算，不是正式風控報表" />
        <MetricCard label="模型 CVaR 95%" value={`${cvar95.toFixed(1)}%`} note="尾端損失估算" />
        <MetricCard label="集中度 HHI" value={formatNum(hhi, 3)} note={concentration} />
        <MetricCard label="市場健康度" value={formatNum(intelligence.health, 0)} note="/100" />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">壓力測試</div>
          {[-5, -10, -15, -20].map((shock) => (
            <div className="regime" key={shock}>
              <span>市場 {shock}%</span>
              <strong>{scenarioLoss(allocations, shock).toFixed(1)}%</strong>
              <small>風險調整配置估算</small>
            </div>
          ))}
        </div>

        <div className="panel">
          <div className="panel-title">風險預算貢獻</div>
          {allocations.map((row) => (
            <div className="regime" key={row.symbol}>
              <span>{row.symbol} {row.name ?? ""}</span>
              <strong>{row.riskContribution.toFixed(1)}</strong>
              <small>權重 {(row.weight * 100).toFixed(1)}%</small>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">使用限制</div>
        <p className="report-summary">
          目前 VaR 與 CVaR 是依量化 Risk Score 建立的代理估算，並非由完整歷史報酬協方差矩陣計算。
          正式下單或合規風控前，仍需接入實際持倉、報酬序列與交易成本。
        </p>
      </div>
    </section>
  );
}
