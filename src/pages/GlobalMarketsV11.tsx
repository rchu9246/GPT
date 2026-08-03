import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import {
  formatNum,
  loadLatestSignals,
  marketIntelligence,
  regimeLabel,
} from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

type ProxyMarket = {
  name: string;
  score: number;
  state: string;
  note: string;
};

export default function GlobalMarketsV11() {
  const [signals, setSignals] = useState<SignalRow[]>([]);

  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const intelligence = useMemo(() => marketIntelligence(signals), [signals]);

  const markets: ProxyMarket[] = useMemo(() => {
    const base = intelligence.health;
    return [
      { name: "台股風險代理", score: base, state: regimeLabel(intelligence.regime), note: "由台股多因子訊號計算" },
      { name: "科技風格代理", score: Math.max(0, Math.min(100, base + 6)), state: base >= 50 ? "相對強勢" : "動能不足", note: "依電子與高動能標的推估" },
      { name: "防禦風格代理", score: Math.max(0, Math.min(100, 100 - intelligence.averageRisk)), state: intelligence.averageRisk < 50 ? "穩定" : "承壓", note: "依整體風險分數反向計算" },
      { name: "市場廣度", score: intelligence.breadth * 100, state: intelligence.breadth >= 0.5 ? "擴散" : "集中", note: "偏多標的占比" },
    ];
  }, [intelligence]);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GLOBAL RISK CONSOLE</div>
          <h1>全球市場與跨資產代理</h1>
          <p>目前版本顯示量化代理指標；尚未接入的外部即時行情不會被偽裝成真實報價。</p>
        </div>
      </div>

      <div className="cards">
        <MetricCard label="市場健康度" value={formatNum(intelligence.health, 0)} note="/100" />
        <MetricCard label="平均風險" value={formatNum(intelligence.averageRisk)} note="越高越需防守" />
        <MetricCard label="市場廣度" value={`${Math.round(intelligence.breadth * 100)}%`} note="偏多標的占比" />
        <MetricCard label="風險警示" value={String(intelligence.warningCount)} note="高風險或避開評級" />
      </div>

      <div className="professional-signal-grid">
        {markets.map((market) => (
          <article className="professional-signal-card" key={market.name}>
            <div className="signal-card-head">
              <div><strong>{market.name}</strong><span>{market.state}</span></div>
              <b>{market.score.toFixed(0)}</b>
            </div>
            <div className="health-bar"><i style={{ width: `${market.score}%` }} /></div>
            <p>{market.note}</p>
          </article>
        ))}
      </div>

      <div className="panel">
        <div className="panel-title">正式資料接入準備</div>
        <p className="report-summary">
          V11 已預留全球市場服務層。未來可在 Supabase 建立 market_snapshots 表，
          再由排程寫入指數、VIX、美元、黃金、原油與加密資產資料；前端不需要存放供應商秘密金鑰。
        </p>
      </div>
    </section>
  );
}
