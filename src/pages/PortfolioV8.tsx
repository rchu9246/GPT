import { useEffect, useMemo, useState } from "react";
import { formatNum, loadLatestSignals } from "../lib/v8Data";
import type { SignalRow } from "../types/v8";

export default function PortfolioV8() {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  useEffect(() => { loadLatestSignals().then(setSignals).catch(() => setSignals([])); }, []);

  const holdings = useMemo(() => {
    const selected = signals.filter((row) => Number(row.score ?? 0) >= 35).slice(0, 8);
    const raw = selected.map((row) =>
      Math.max(1, Number(row.score ?? 0)) /
      Math.max(15, Number(row.risk_score ?? 50)),
    );
    const sum = raw.reduce((a, b) => a + b, 0) || 1;
    return selected.map((row, index) => ({ ...row, weight: raw[index] / sum }));
  }, [signals]);

  const weightedRisk = holdings.reduce(
    (sum, row) => sum + row.weight * Number(row.risk_score ?? 0),
    0,
  );
  const cash = weightedRisk >= 60 ? 35 : weightedRisk >= 45 ? 25 : 15;

  return (
    <section>
      <div className="page-title"><div><div className="eyebrow">V8 PORTFOLIO ENGINE</div><h1>投資組合最佳化</h1><p>依 Score、Risk 與去重後訊號分配權重。</p></div></div>
      <div className="cards">
        <div className="metric"><span>建議持股數</span><strong>{holdings.length}</strong><small>上限 8 檔</small></div>
        <div className="metric"><span>加權風險</span><strong>{formatNum(weightedRisk)}</strong><small>越低越防守</small></div>
        <div className="metric"><span>現金部位</span><strong>{cash}%</strong><small>隨市場風險調整</small></div>
        <div className="metric"><span>單股上限</span><strong>20%</strong><small>避免集中風險</small></div>
      </div>
      <div className="panel">
        <div className="panel-title">建議配置</div>
        <div className="allocation-list">
          {holdings.map((row) => (
            <div className="allocation-row" key={row.symbol}>
              <div><strong>{row.symbol}</strong><small>{row.name ?? ""}</small></div>
              <div className="allocation-bar"><i style={{ width: `${Math.min(100, row.weight * 100)}%` }} /></div>
              <b>{(row.weight * 100).toFixed(1)}%</b>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
