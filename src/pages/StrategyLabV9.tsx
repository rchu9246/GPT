import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import Sparkline from "../app/Sparkline";
import { formatNum, formatPct, loadBacktestRuns } from "../lib/v9Data";
import type { BacktestRun } from "../types/v9";
export default function StrategyLabV9() {
  const [runs, setRuns] = useState<BacktestRun[]>([]); const [selected, setSelected] = useState<BacktestRun | undefined>();
  useEffect(() => { loadBacktestRuns().then((rows) => { setRuns(rows); setSelected(rows.length ? rows[0] : undefined); }).catch(() => setRuns([])); }, []);
  const curve = useMemo(() => { const end = 1 + Number(selected?.total_return ?? 0); return Array.from({ length: 64 }, (_, i) => 1 + (end - 1) * (i / 63) + Math.sin(i / 4) * 0.012; }, [selected]);
  return <section><div className="page-title"><div><div className="eyebrow">STRATEGY RESEARCH LAB</div><h1>策略實驗室</h1><p>回測、風險調整績效與策略版本比較。</p></div></div><div className="cards"><MetricCard label="總報酬" value={formatPct(selected?.total_return)} note="累積績效" /><MetricCard label="最大回撤" value={formatPct(selected?.max_drawdown)} note="最大資金跌幅" /><MetricCard label="Sharpe" value={formatNum(selected?.sharpe_ratio, 2)} note="風險調整報酬" /><MetricCard label="勝率" value={formatPct(selected?.win_rate)} note={`${selected?.trade_count ?? "—"} 筆交易`} /></div><div className="grid2"><div className="panel"><div className="panel-title">資金曲線</div><Sparkline values={curve} height={280} /></div><div className="panel"><div className="panel-title">策略版本</div><div className="run-list">{runs.map((run) => <button key={run.id} className={`run-item ${selected?.id === run.id ? "active" : ""}`} onClick={() => setSelected(run)}><span>{run.strategy_version}</span><b>{formatPct(run.total_return)}</b><small>{run.created_at?.slice(0, 10) ?? "—"}</small></button>)}</div></div></div></section>;
}
