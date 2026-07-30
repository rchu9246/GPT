import { useEffect, useMemo, useState } from "react";
import Sparkline from "../app/Sparkline";
import { loadBacktestRuns, formatNum, formatPct } from "../lib/v7Data";
import type { BacktestRun } from "../types/v7";

export default function BacktestV7() {
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selected, setSelected] = useState<BacktestRun | undefined>();

  useEffect(() => {
    loadBacktestRuns().then((rows) => { setRuns(rows); setSelected(rows[0]); }).catch(() => setRuns([]));
  }, []);

  const curve = useMemo(() => {
    const end = 1 + (Number(selected?.total_return ?? 0) || 0);
    return Array.from({ length: 48 }, (_, i) => 1 + (end - 1) * (i / 47) + Math.sin(i / 3) * 0.02);
  }, [selected]);

  return (
    <section>
      <div className="page-title"><div><div className="eyebrow">BACKTEST LAB</div><h1>回測中心</h1><p>比較策略報酬、回撤、Sharpe 與交易品質。</p></div></div>
      <div className="cards">
        <div className="metric"><span>總報酬</span><strong>{formatPct(selected?.total_return)}</strong><small>策略期間累積報酬</small></div>
        <div className="metric"><span>最大回撤</span><strong>{formatPct(selected?.max_drawdown)}</strong><small>歷史最大資金跌幅</small></div>
        <div className="metric"><span>Sharpe</span><strong>{formatNum(selected?.sharpe_ratio, 2)}</strong><small>風險調整後報酬</small></div>
        <div className="metric"><span>勝率</span><strong>{formatPct(selected?.win_rate)}</strong><small>{selected?.trade_count ?? "—"} 筆交易</small></div>
      </div>
      <div className="grid2">
        <div className="panel"><div className="panel-title">資金曲線</div><Sparkline values={curve} height={280} label="模擬資金曲線" /></div>
        <div className="panel">
          <div className="panel-title">回測紀錄</div>
          <div className="run-list">
            {runs.map((run) => (
              <button className={`run-item ${selected?.id === run.id ? "active" : ""}`} key={run.id} onClick={() => setSelected(run)}>
                <span>{run.strategy_version}</span><b>{formatPct(run.total_return)}</b><small>{run.created_at?.slice(0, 10) ?? "—"}</small>
              </button>
            ))}
            {!runs.length && <p>目前尚無回測紀錄。</p>}
          </div>
        </div>
      </div>
    </section>
  );
}
