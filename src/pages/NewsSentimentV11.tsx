import { useEffect, useMemo, useState } from "react";
import {
  formatNum,
  loadLatestSignals,
  ratingLabel,
} from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

export default function NewsSentimentV11({
  onOpenStock,
}: {
  onOpenStock: (symbol: string) => void;
}) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const events = useMemo(
    () =>
      signals.slice(0, 10).map((row) => ({
        ...row,
        sentiment:
          row.rating === "STRONG_BUY" || row.rating === "BUY"
            ? "偏多"
            : row.rating === "WATCH"
              ? "中性"
              : "偏空",
        reason:
          row.risk_score >= 60
            ? "風險分數偏高"
            : row.momentum_score >= 50
              ? "動能與趨勢改善"
              : "訊號仍待確認",
      })),
    [signals],
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">EVENT & SENTIMENT INTELLIGENCE</div>
          <h1>事件與情緒中心</h1>
          <p>目前內容是量化訊號衍生的研究事件，不冒充尚未接入的即時新聞。</p>
        </div>
      </div>

      <div className="professional-signal-grid">
        {events.map((row) => (
          <button
            className="professional-signal-card clickable"
            key={row.symbol}
            onClick={() => onOpenStock(row.symbol)}
          >
            <div className="signal-card-head">
              <div><strong>{row.symbol}</strong><span>{row.name ?? ""}</span></div>
              <b>{row.sentiment}</b>
            </div>
            <span className={`rating rating-${row.rating.toLowerCase()}`}>
              {ratingLabel(row.rating)}
            </span>
            <p>{row.reason}。Score {formatNum(row.score)}，風險 {formatNum(row.risk_score)}，信心 {formatNum(row.confidence)}。</p>
          </button>
        ))}
      </div>
    </section>
  );
}
