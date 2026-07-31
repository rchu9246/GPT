import { useEffect, useMemo, useState } from "react";
import { formatNum, loadLatestSignals, ratingLabel } from "../lib/v8Data";
import type { SignalRow } from "../types/v8";

export default function DailyReportV8() {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  useEffect(() => { loadLatestSignals().then(setSignals).catch(() => setSignals([])); }, []);

  const summary = useMemo(() => {
    const avg = signals.length
      ? signals.reduce((sum, row) => sum + Number(row.score ?? 0), 0) / signals.length
      : 0;
    const top = signals.slice(0, 3);
    return {
      title: avg >= 60 ? "多頭機會增加" : avg >= 45 ? "中性選股環境" : "風險控管優先",
      text: signals.length
        ? `最新交易日 ${signals[0].trade_date}，平均 Score ${avg.toFixed(1)}。今日領先標的為 ${top.map((row) => row.symbol).join("、")}。`
        : "目前尚無最新訊號。",
    };
  }, [signals]);

  return (
    <section>
      <div className="page-title"><div><div className="eyebrow">V8 AI RESEARCH</div><h1>每日 AI 研究報告</h1><p>將量化訊號轉換成研究摘要與執行重點。</p></div></div>
      <div className="panel report-hero"><div className="eyebrow">今日主題</div><h2>{summary.title}</h2><p className="report-summary">{summary.text}</p></div>
      <div className="professional-signal-grid">
        {signals.slice(0, 6).map((row) => (
          <article className="professional-signal-card" key={row.symbol}>
            <div className="signal-card-head"><div><strong>{row.symbol}</strong><span>{row.name ?? ""}</span></div><b>{formatNum(row.score)}</b></div>
            <span className={`rating rating-${row.rating?.toLowerCase()}`}>{ratingLabel(row.rating)}</span>
            <p>趨勢 {formatNum(row.trend_score)} · 動能 {formatNum(row.momentum_score)} · 風險 {formatNum(row.risk_score)} · 信心 {formatNum(row.confidence)}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
