import { useEffect, useMemo, useState } from "react";
import {
  formatNum,
  loadLatestSignals,
  ratingLabel,
} from "../lib/v8Data";
import type { SignalRow } from "../types/v8";

export default function DashboardV8({
  onOpenStock,
}: {
  onOpenStock: (symbol: string) => void;
}) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadLatestSignals()
      .then(setSignals)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "資料讀取失敗"),
      )
      .finally(() => setLoading(false));
  }, []);

  const avgScore = useMemo(() => {
    const values = signals
      .map((row) => Number(row.score))
      .filter(Number.isFinite);
    return values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : 0;
  }, [signals]);

  const strong = signals.filter((row) =>
    ["STRONG_BUY", "BUY"].includes(row.rating ?? ""),
  ).length;
  const risky = signals.filter(
    (row) => Number(row.risk_score ?? 0) >= 60,
  ).length;
  const regime = avgScore >= 65 ? "偏多" : avgScore >= 45 ? "中性" : "空頭";
  const health = Math.max(
    0,
    Math.min(100, Math.round(avgScore + strong * 5 - risky * 3)),
  );

  return (
    <section>
      <div className="hero">
        <div>
          <div className="eyebrow">GPT QUANT V8 · AI DECISION ENGINE</div>
          <h1>今日策略總覽</h1>
          <p>去重訊號、AI 評級、風險預算與技術面整合。</p>
        </div>
        <div className="health">
          <span>策略健康度</span>
          <strong>{health}</strong><small>/100</small>
          <div className="health-bar"><i style={{ width: `${health}%` }} /></div>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <div className="metric"><span>市場狀態</span><strong>{loading ? "讀取中" : regime}</strong><small>依去重後訊號平均分數判定</small></div>
        <div className="metric"><span>最新交易日</span><strong>{signals[0]?.trade_date ?? "—"}</strong><small>Supabase 最新資料</small></div>
        <div className="metric"><span>偏多標的</span><strong>{strong}</strong><small>AI 評級為偏多以上</small></div>
        <div className="metric"><span>風險警示</span><strong>{risky}</strong><small>Risk ≥ 60</small></div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">🚀 V8 去重訊號排行榜</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>排名</th><th>股票</th><th>Score</th><th>AI 評級</th><th>趨勢</th><th>動能</th><th>風險</th><th>信心</th></tr>
              </thead>
              <tbody>
                {signals.map((row, index) => (
                  <tr className="clickable" key={row.symbol} onClick={() => onOpenStock(row.symbol)}>
                    <td>{index + 1}</td>
                    <td><strong>{row.symbol}</strong> {row.name ?? ""}</td>
                    <td>{formatNum(row.score)}</td>
                    <td><span className={`rating rating-${row.rating?.toLowerCase()}`}>{ratingLabel(row.rating)}</span></td>
                    <td>{formatNum(row.trend_score)}</td>
                    <td>{formatNum(row.momentum_score)}</td>
                    <td>{formatNum(row.risk_score)}</td>
                    <td>{formatNum(row.confidence)}</td>
                  </tr>
                ))}
                {!loading && !signals.length && <tr><td colSpan={8}>目前沒有訊號資料</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <div className="panel">
            <div className="panel-title">🌐 市場摘要</div>
            <div className="regime"><span>市場狀態</span><strong>{regime}</strong></div>
            <div className="regime"><span>平均 Score</span><strong>{formatNum(avgScore)}</strong></div>
            <div className="regime"><span>去重標的數</span><strong>{signals.length}</strong></div>
            <div className="regime"><span>偏多比例</span><strong>{signals.length ? `${Math.round(strong / signals.length * 100)}%` : "—"}</strong></div>
          </div>
          <div className="panel">
            <div className="panel-title">🤖 V8 AI 決策摘要</div>
            <p className="report-summary">
              {regime === "偏多"
                ? "市場結構偏多，優先觀察高分、低風險且信心較高的標的。"
                : regime === "中性"
                  ? "市場缺乏一致方向，建議降低部位並採取選股優先。"
                  : "風險偏高，應提高現金比例並避免追價。"}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
