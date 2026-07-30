import { useEffect, useMemo, useState } from "react";
import { loadLatestSignals, formatNum } from "../lib/v7Data";
import type { SignalRow } from "../types/v7";

export default function DailyReportV7() {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  useEffect(() => { loadLatestSignals().then(setSignals).catch(() => setSignals([])); }, []);

  const report = useMemo(() => {
    if (!signals.length) return { title: "等待最新資料", summary: "目前尚未讀取到最新訊號。", action: "請先確認資料管線與 Supabase 更新狀態。" };
    const avg = signals.reduce((sum, s) => sum + Number(s.score ?? 0), 0) / signals.length;
    const top = [...signals].sort((a, b) => Number(b.score ?? 0) - Number(a.score ?? 0)).slice(0, 3);
    const risky = signals.filter((s) => Number(s.risk_score ?? 0) >= 60 || Number(s.score ?? 0) < 40);
    const title = avg >= 70 ? "多頭環境，聚焦強勢股" : avg >= 50 ? "中性環境，選股重於選市" : "風險偏高，防守優先";
    const summary = `最新交易日 ${signals[0].trade_date}，平均 Score ${avg.toFixed(1)}。領先標的是 ${top.map((s) => s.symbol).join("、")}。`;
    const action = risky.length
      ? `目前有 ${risky.length} 檔風險警示，建議降低總曝險並設定停損。`
      : "風險警示有限，但仍應分批進場並限制單一持股權重。";
    return { title, summary, action };
  }, [signals]);

  return (
    <section>
      <div className="page-title"><div><div className="eyebrow">DAILY RESEARCH</div><h1>每日研究報告</h1><p>把訊號轉成可執行的研究摘要。</p></div></div>
      <div className="panel report-hero">
        <div className="eyebrow">今日主題</div>
        <h2>{report.title}</h2>
        <p className="report-summary">{report.summary}</p>
        <div className="report-action">{report.action}</div>
      </div>
      <div className="professional-signal-grid">
        {signals.slice(0, 6).map((s) => (
          <article className="professional-signal-card" key={s.symbol}>
            <div className="signal-card-head"><div><strong>{s.symbol}</strong><span>{s.name ?? ""}</span></div><b>{formatNum(s.score)}</b></div>
            <div className="signal-levels">
              <span>趨勢：{formatNum(s.trend_score)}</span>
              <span>動能：{formatNum(s.momentum_score)}</span>
              <span>風險：{formatNum(s.risk_score)}</span>
              <span>信心：{formatNum(s.confidence)}</span>
            </div>
            <ul>
              <li>高分且低風險時，優先列入觀察。</li>
              <li>價格轉弱或風險升高時，降低部位。</li>
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
