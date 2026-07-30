import { useEffect, useMemo, useState } from "react";
import { loadLatestSignals, formatNum } from "../lib/v7Data";
import type { SignalRow } from "../types/v7";

export default function PortfolioV7() {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  useEffect(() => { loadLatestSignals().then(setSignals).catch(() => setSignals([])); }, []);

  const holdings = useMemo(() => {
    const selected = [...signals]
      .filter((s) => Number(s.score ?? 0) >= 40)
      .sort((a, b) => Number(b.score ?? 0) - Number(a.score ?? 0))
      .slice(0, 8);
    const raw = selected.map((s) => Math.max(1, Number(s.score ?? 0)) / Math.max(20, Number(s.risk_score ?? 20)));
    const total = raw.reduce((a, b) => a + b, 0) || 1;
    return selected.map((s, i) => ({ ...s, weight: raw[i] / total }));
  }, [signals]);

  const concentration = holdings.reduce((sum, h) => sum + h.weight ** 2, 0);
  const riskBudget = holdings.reduce((sum, h) => sum + h.weight * Number(h.risk_score ?? 0), 0);

  return (
    <section>
      <div className="page-title"><div><div className="eyebrow">PORTFOLIO ENGINE</div><h1>投資組合</h1><p>依訊號強度與風險分數配置權重。</p></div></div>
      <div className="cards">
        <div className="metric"><span>建議持股數</span><strong>{holdings.length}</strong><small>避免過度集中</small></div>
        <div className="metric"><span>加權風險</span><strong>{formatNum(riskBudget)}</strong><small>越低越防守</small></div>
        <div className="metric"><span>集中度 HHI</span><strong>{formatNum(concentration, 3)}</strong><small>越低越分散</small></div>
        <div className="metric"><span>現金緩衝</span><strong>{riskBudget > 55 ? "30%" : riskBudget > 40 ? "20%" : "10%"}</strong><small>隨市場風險調整</small></div>
      </div>
      <div className="panel">
        <div className="panel-title">建議權重</div>
        <div className="allocation-list">
          {holdings.map((h) => (
            <div className="allocation-row" key={h.symbol}>
              <div><strong>{h.symbol}</strong><small>{h.name ?? ""}</small></div>
              <div className="allocation-bar"><i style={{ width: `${h.weight * 100}%` }} /></div>
              <b>{(h.weight * 100).toFixed(1)}%</b>
            </div>
          ))}
          {!holdings.length && <p>目前沒有足夠訊號可建立投資組合。</p>}
        </div>
      </div>
      <div className="panel">
        <div className="panel-title">風險規則</div>
        <div className="risk-rules"><span>單一持股上限 20%</span><span>高風險市場提高現金</span><span>Score 低於 40 排除</span><span>每週重新平衡</span></div>
      </div>
    </section>
  );
}
