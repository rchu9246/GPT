import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import {
  buildDecisionAlerts,
  formatNum,
  loadLatestSignals,
  ratingLabel,
} from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

const STORAGE_KEY = "gpt-quant-v12-watchlist";

function readWatchlist(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export default function AIWatchlistV12({
  onOpenStock,
}: {
  onOpenStock: (symbol: string) => void;
}) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [symbols, setSymbols] = useState<string[]>(readWatchlist);

  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols));
  }, [symbols]);

  const selected = useMemo(
    () => signals.filter((row) => symbols.includes(row.symbol)),
    [signals, symbols],
  );
  const alerts = useMemo(() => buildDecisionAlerts(selected), [selected]);
  const averageScore = selected.length
    ? selected.reduce((sum, row) => sum + row.score, 0) / selected.length
    : 0;
  const averageRisk = selected.length
    ? selected.reduce((sum, row) => sum + row.risk_score, 0) / selected.length
    : 0;

  function toggle(symbol: string) {
    setSymbols((current) =>
      current.includes(symbol)
        ? current.filter((item) => item !== symbol)
        : [...current, symbol],
    );
  }

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V12 AI WATCHLIST</div>
          <h1>AI 自選監控</h1>
          <p>追蹤評級、風險、信心與決策警示；清單保存在目前瀏覽器。</p>
        </div>
      </div>

      <div className="cards">
        <MetricCard label="追蹤標的" value={String(selected.length)} note="瀏覽器本機保存" />
        <MetricCard label="平均 Score" value={formatNum(averageScore)} note="自選平均分數" />
        <MetricCard label="平均風險" value={formatNum(averageRisk)} note="越高越需防守" />
        <MetricCard label="決策警示" value={String(alerts.length)} note="自選清單警示" />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">全部候選股票</div>
          <div className="watchlist-picker">
            {signals.map((row) => (
              <button
                className={`watchlist-chip ${symbols.includes(row.symbol) ? "selected" : ""}`}
                key={row.symbol}
                onClick={() => toggle(row.symbol)}
              >
                <strong>{row.symbol}</strong>
                <span>{row.name ?? ""}</span>
                <small>{ratingLabel(row.rating)}</small>
              </button>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">AI 追蹤警示</div>
          {alerts.map((alert) => (
            <button
              className={`alert-row severity-${alert.severity.toLowerCase()}`}
              key={alert.id}
              onClick={() => alert.symbol && onOpenStock(alert.symbol)}
            >
              <strong>{alert.title}</strong>
              <span>{alert.message}</span>
            </button>
          ))}
          {!alerts.length && <p>目前沒有自選警示，請先加入股票。</p>}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">自選股票</div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>股票</th><th>評級</th><th>Score</th><th>信心</th><th>風險</th><th>品質</th></tr></thead>
            <tbody>
              {selected.map((row) => (
                <tr className="clickable" key={row.symbol} onClick={() => onOpenStock(row.symbol)}>
                  <td><strong>{row.symbol}</strong> {row.name ?? ""}</td>
                  <td>{ratingLabel(row.rating)}</td>
                  <td>{row.score.toFixed(1)}</td>
                  <td>{row.confidence.toFixed(1)}</td>
                  <td>{row.risk_score.toFixed(1)}</td>
                  <td>{row.quality_score.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
