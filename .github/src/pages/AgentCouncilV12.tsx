import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import {
  formatNum,
  loadLatestSignals,
  marketIntelligence,
  regimeLabel,
} from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

type AgentView = {
  name: string;
  score: number;
  stance: string;
  thesis: string;
};

export default function AgentCouncilV12({
  onOpenStock,
}: {
  onOpenStock: (symbol: string) => void;
}) {
  const [signals, setSignals] = useState<SignalRow[]>([]);

  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const intelligence = useMemo(() => marketIntelligence(signals), [signals]);

  const agents = useMemo<AgentView[]>(() => {
    const averageTrend = signals.length
      ? signals.reduce((sum, row) => sum + row.trend_score, 0) / signals.length
      : 0;
    const averageMomentum = signals.length
      ? signals.reduce((sum, row) => sum + row.momentum_score, 0) / signals.length
      : 0;
    const averageQuality = signals.length
      ? signals.reduce((sum, row) => sum + row.quality_score, 0) / signals.length
      : 0;
    const riskControl = Math.max(0, 100 - intelligence.averageRisk);

    return [
      {
        name: "Trend Agent",
        score: averageTrend,
        stance: averageTrend >= 55 ? "順勢偏多" : averageTrend >= 40 ? "等待突破" : "趨勢偏弱",
        thesis: "觀察市場趨勢分數與高分標的擴散程度。",
      },
      {
        name: "Momentum Agent",
        score: averageMomentum,
        stance: averageMomentum >= 50 ? "動能改善" : averageMomentum >= 30 ? "動能分化" : "動能不足",
        thesis: "比較近期動能與市場廣度是否同步。",
      },
      {
        name: "Quality Agent",
        score: averageQuality,
        stance: averageQuality >= 50 ? "品質可接受" : "品質仍弱",
        thesis: "綜合 Score、趨勢、動能、量能與風險。",
      },
      {
        name: "Risk Agent",
        score: riskControl,
        stance: intelligence.averageRisk < 45 ? "風險可控" : intelligence.averageRisk < 60 ? "控制部位" : "防守優先",
        thesis: "以平均風險與高風險標的數量調整總曝險。",
      },
    ];
  }, [signals, intelligence]);

  const chiefScore = agents.length
    ? agents.reduce((sum, agent) => sum + agent.score, 0) / agents.length
    : 0;
  const chiefDecision =
    chiefScore >= 60 && intelligence.regime === "RISK_ON"
      ? "積極選股、分批進場"
      : chiefScore >= 42
        ? "中性配置、等待確認"
        : "提高現金、風險趨避";

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V12 MULTI-AGENT DECISION COUNCIL</div>
          <h1>AI Agent 決策議會</h1>
          <p>趨勢、動能、品質與風控代理共同產生可解釋決策。</p>
        </div>
      </div>

      <div className="cards">
        <MetricCard label="Chief AI 分數" value={formatNum(chiefScore, 0)} note="/100" />
        <MetricCard label="市場狀態" value={regimeLabel(intelligence.regime)} note="量化代理結論" />
        <MetricCard label="偏多標的" value={String(intelligence.bullishCount)} note="BUY 以上評級" />
        <MetricCard label="風險警示" value={String(intelligence.warningCount)} note="需降低曝險" />
      </div>

      <div className="panel report-hero">
        <div className="eyebrow">CHIEF AI CONSENSUS</div>
        <h2>{chiefDecision}</h2>
        <p className="report-summary">
          Agent 平均分數 {chiefScore.toFixed(1)}，市場健康度 {intelligence.health.toFixed(1)}。
          所有結論都由目前 Supabase 量化資料推導，不依賴未配置的外部模型。
        </p>
      </div>

      <div className="professional-signal-grid">
        {agents.map((agent) => (
          <article className="professional-signal-card" key={agent.name}>
            <div className="signal-card-head">
              <div><strong>{agent.name}</strong><span>{agent.stance}</span></div>
              <b>{agent.score.toFixed(0)}</b>
            </div>
            <div className="health-bar"><i style={{ width: `${Math.max(0, Math.min(100, agent.score))}%` }} /></div>
            <p>{agent.thesis}</p>
          </article>
        ))}
      </div>

      <div className="panel">
        <div className="panel-title">Chief AI 優先研究清單</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>#</th><th>股票</th><th>Score</th><th>趨勢</th><th>動能</th><th>品質</th><th>風險</th></tr>
            </thead>
            <tbody>
              {signals.slice(0, 8).map((row, index) => (
                <tr className="clickable" key={row.symbol} onClick={() => onOpenStock(row.symbol)}>
                  <td>{index + 1}</td>
                  <td><strong>{row.symbol}</strong> {row.name ?? ""}</td>
                  <td>{row.score.toFixed(1)}</td>
                  <td>{row.trend_score.toFixed(1)}</td>
                  <td>{row.momentum_score.toFixed(1)}</td>
                  <td>{row.quality_score.toFixed(1)}</td>
                  <td>{row.risk_score.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
