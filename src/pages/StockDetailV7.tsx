import { useEffect, useMemo, useState } from "react";
import Sparkline from "../app/Sparkline";
import {
  loadLatestSignals,
  loadPriceHistory,
  formatNum,
  formatPct,
} from "../lib/v7Data";
import type { PriceRow, SignalRow } from "../types/v7";

export default function StockDetailV7({
  symbol,
  onBack,
}: {
  symbol: string;
  onBack: () => void;
}) {
  const [prices, setPrices] = useState<PriceRow[]>([]);
  const [signal, setSignal] = useState<SignalRow | undefined>();
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([loadPriceHistory(symbol), loadLatestSignals()])
      .then(([priceRows, signalRows]) => {
        setPrices(priceRows);
        setSignal(signalRows.find((row) => row.symbol === symbol));
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "資料讀取失敗");
      });
  }, [symbol]);

  const closes = prices
    .map((price) => Number(price.close))
    .filter((value) => Number.isFinite(value));

  const latest =
    closes.length > 0 ? closes[closes.length - 1] : undefined;

  const prev20 =
    closes.length > 20
      ? closes[closes.length - 21]
      : closes.length > 0
        ? closes[0]
        : undefined;

  const latestPriceRow =
    prices.length > 0 ? prices[prices.length - 1] : undefined;

  const return20 =
    latest !== undefined && prev20 !== undefined && prev20 !== 0
      ? latest / prev20 - 1
      : null;

  const recent60 = closes.slice(-60);
  const high60 = recent60.length > 0 ? Math.max(...recent60) : null;
  const low60 = recent60.length > 0 ? Math.min(...recent60) : null;

  const plan = useMemo(() => {
    const score = Number(signal?.score ?? 0);
    const risk = Number(signal?.risk_score ?? 50);

    if (score >= 70 && risk < 60) {
      return "偏多觀察：等待回測支撐或量價再度轉強，分批建立部位。";
    }

    if (score >= 50) {
      return "中性觀察：保留現金，等待趨勢與動能同步改善。";
    }

    return "防守優先：避免追價，等待風險下降與結構重新轉強。";
  }, [signal]);

  return (
    <section>
      <button className="nav active" onClick={onBack}>
        ← 返回總覽
      </button>

      <div className="page-title">
        <div>
          <div className="eyebrow">STOCK INTELLIGENCE</div>
          <h1>{symbol} 個股分析</h1>
          <p>價格趨勢、多因子分數、風險與交易計畫。</p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <div className="metric">
          <span>最新收盤</span>
          <strong>{formatNum(latest, 2)}</strong>
          <small>{latestPriceRow?.trade_date ?? "—"}</small>
        </div>

        <div className="metric">
          <span>20 日報酬</span>
          <strong>{formatPct(return20)}</strong>
          <small>近期趨勢強弱</small>
        </div>

        <div className="metric">
          <span>60 日區間</span>
          <strong>
            {formatNum(low60, 1)}–{formatNum(high60, 1)}
          </strong>
          <small>支撐與壓力參考</small>
        </div>

        <div className="metric">
          <span>策略 Score</span>
          <strong>{formatNum(signal?.score)}</strong>
          <small>{signal?.strategy_version ?? "尚無最新訊號"}</small>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">價格趨勢</div>
          <Sparkline
            values={closes.slice(-180)}
            height={260}
            label={`${symbol} 近 180 日收盤價`}
          />
        </div>

        <div className="panel">
          <div className="panel-title">多因子雷達</div>

          {[
            ["趨勢", signal?.trend_score],
            ["動能", signal?.momentum_score],
            ["價值", signal?.value_score],
            ["風險", signal?.risk_score],
            ["信心", signal?.confidence],
          ].map(([label, value]) => (
            <div className="factor-row" key={String(label)}>
              <span>{label}</span>
              <i
                style={{
                  width: `${Math.min(100, Number(value ?? 0))}%`,
                }}
              />
              <strong>{formatNum(Number(value))}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">V7 交易計畫</div>
        <div className="report-action">{plan}</div>
        <p>
          此內容由規則式量化模型生成，只作研究用途，不構成投資建議。
        </p>
      </div>
    </section>
  );
}
