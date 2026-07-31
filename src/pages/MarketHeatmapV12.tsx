import { useEffect, useMemo, useState } from "react";
import { loadLatestSignals } from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

type Metric = "score" | "momentum" | "risk" | "quality";

function metricValue(row: SignalRow, metric: Metric): number {
  if (metric === "momentum") return row.momentum_score;
  if (metric === "risk") return row.risk_score;
  if (metric === "quality") return row.quality_score;
  return row.score;
}

export default function MarketHeatmapV12({
  onOpenStock,
}: {
  onOpenStock: (symbol: string) => void;
}) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [metric, setMetric] = useState<Metric>("score");

  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const sorted = useMemo(
    () =>
      signals
        .slice()
        .sort((a, b) => metricValue(b, metric) - metricValue(a, metric)),
    [signals, metric],
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V12 MARKET HEATMAP</div>
          <h1>台股訊號熱力圖</h1>
          <p>依 Score、動能、品質或風險快速辨識市場領先與落後標的。</p>
        </div>
      </div>

      <div className="panel filter-panel">
        {(["score", "momentum", "quality", "risk"] as Metric[]).map((item) => (
          <button
            className={`nav ${metric === item ? "active" : ""}`}
            key={item}
            onClick={() => setMetric(item)}
          >
            {item === "score" ? "Score" : item === "momentum" ? "動能" : item === "quality" ? "品質" : "風險"}
          </button>
        ))}
      </div>

      <div className="heatmap-grid">
        {sorted.map((row) => {
          const value = metricValue(row, metric);
          const safeValue = Math.max(0, Math.min(100, value));
          const level = Math.max(1, Math.min(5, Math.ceil(safeValue / 20)));
          const riskClass = metric === "risk" ? `risk-level-${level}` : `heat-level-${level}`;

          return (
            <button
              className={`heatmap-cell ${riskClass}`}
              key={row.symbol}
              onClick={() => onOpenStock(row.symbol)}
            >
              <strong>{row.symbol}</strong>
              <span>{row.name ?? "—"}</span>
              <b>{value.toFixed(1)}</b>
              <small>{row.industry ?? "未分類"}</small>
            </button>
          );
        })}
      </div>
    </section>
  );
}
