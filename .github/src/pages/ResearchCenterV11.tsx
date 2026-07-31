import { useEffect, useMemo, useState } from "react";
import {
  formatNum,
  loadLatestSignals,
  marketIntelligence,
  ratingLabel,
  regimeLabel,
  sectorRotation,
} from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

export default function ResearchCenterV11({
  onOpenStock,
}: {
  onOpenStock: (symbol: string) => void;
}) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const intelligence = useMemo(() => marketIntelligence(signals), [signals]);
  const sectors = useMemo(() => sectorRotation(signals).slice(0, 5), [signals]);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">ENTERPRISE RESEARCH WORKSPACE</div>
          <h1>AI 研究中心</h1>
          <p>把市場、產業與個股訊號整理成可追蹤的研究假設。</p>
        </div>
      </div>

      <div className="panel report-hero">
        <div className="eyebrow">今日研究結論</div>
        <h2>{regimeLabel(intelligence.regime)}</h2>
        <p className="report-summary">
          平均 Score {intelligence.averageScore.toFixed(1)}，平均風險{" "}
          {intelligence.averageRisk.toFixed(1)}。研究重點應放在高分、低風險且信心較高的標的，
          並避免把模型排序當作保證報酬。
        </p>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">產業研究假設</div>
          {sectors.map((sector) => (
            <div className="regime" key={sector.industry}>
              <span>{sector.industry}</span>
              <strong>{formatNum(sector.averageScore)}</strong>
              <small>{sector.count} 檔 · 風險 {formatNum(sector.averageRisk)}</small>
            </div>
          ))}
        </div>

        <div className="panel">
          <div className="panel-title">個股研究佇列</div>
          {signals.slice(0, 8).map((row) => (
            <button
              className="run-item"
              key={row.symbol}
              onClick={() => onOpenStock(row.symbol)}
            >
              <span>{row.symbol} {row.name ?? ""}</span>
              <b>{ratingLabel(row.rating)}</b>
              <small>Score {row.score.toFixed(1)} · Risk {row.risk_score.toFixed(1)}</small>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
