import { useEffect, useMemo, useState } from "react";
import { loadLatestSignals, formatNum } from "../lib/v7Data";
import type { SignalRow } from "../types/v7";

export default function DashboardV7({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLatestSignals()
      .then(setSignals)
      .catch((e) => setError(e instanceof Error ? e.message : "資料讀取失敗"))
      .finally(() => setLoading(false));
  }, []);

  const latestDate = signals[0]?.trade_date ?? "—";
  const avgScore = useMemo(() => {
    const values = signals.map((s) => Number(s.score)).filter(Number.isFinite);
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  }, [signals]);
  const strong = signals.filter((s) => Number(s.score ?? 0) >= 70).length;
  const risk = signals.filter((s) => Number(s.risk_score ?? 0) >= 60 || Number(s.score ?? 0) < 40).length;
  const regime = avgScore >= 70 ? "多頭" : avgScore >= 50 ? "中性" : "空頭";
  const health = Math.max(0, Math.min(100, Math.round(avgScore - risk * 5)));

  return (
    <section>
      <div className="hero">
        <div>
          <div className="eyebrow">GPT QUANT V7 · DECISION INTELLIGENCE</div>
          <h1>今日策略總覽</h1>
          <p>Supabase 即時資料、V3.1 多因子策略、回測與風險整合決策。</p>
        </div>
        <div className="health">
          <span>策略健康度</span>
          <strong>{health}</strong><small>/100</small>
          <div className="health-bar"><i style={{ width: `${health}%` }} /></div>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <div className="metric"><span>市場狀態</span><strong>{loading ? "讀取中" : regime}</strong><small>依最新訊號平均分數判定</small></div>
        <div className="metric"><span>最新交易日</span><strong>{latestDate}</strong><small>策略與特徵資料同步日</small></div>
        <div className="metric"><span>強勢訊號</span><strong>{strong}</strong><small>Score ≥ 70</small></div>
        <div className="metric"><span>風險警示</span><strong>{risk}</strong><small>高風險或低分訊號</small></div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">🚀 最新多因子訊號</div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>排名</th><th>股票</th><th>Score</th><th>趨勢</th><th>動能</th><th>風險</th><th>信心</th></tr></thead>
              <tbody>
                {signals.slice(0, 12).map((row, index) => (
                  <tr className="clickable" key={`${row.symbol}-${row.trade_date}`} onClick={() => onOpenStock(row.symbol)}>
                    <td>{index + 1}</td>
                    <td><strong>{row.symbol}</strong> {row.name ?? ""}</td>
                    <td>{formatNum(row.score)}</td>
                    <td>{formatNum(row.trend_score)}</td>
                    <td>{formatNum(row.momentum_score)}</td>
                    <td>{formatNum(row.risk_score)}</td>
                    <td>{formatNum(row.confidence)}</td>
                  </tr>
                ))}
                {!loading && signals.length === 0 && <tr><td colSpan={7}>目前沒有訊號資料</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel">
            <div className="panel-title">🌎 市場摘要</div>
            <div className="regime"><span>市場狀態</span><strong>{regime}</strong></div>
            <div className="regime"><span>平均 Score</span><strong>{formatNum(avgScore)}</strong></div>
            <div className="regime"><span>多頭比例</span><strong>{signals.length ? `${Math.round(strong / signals.length * 100)}%` : "—"}</strong></div>
            <div className="regime"><span>訊號筆數</span><strong>{signals.length}</strong></div>
          </div>
          <div className="panel">
            <div className="panel-title">🧭 V7 決策框架</div>
            <ol className="decision-list">
              <li>先看市場狀態與策略健康度。</li>
              <li>再比較 Score、風險與信心。</li>
              <li>點選股票查看價格趨勢與交易計畫。</li>
              <li>最後到投資組合頁控制總體曝險。</li>
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
