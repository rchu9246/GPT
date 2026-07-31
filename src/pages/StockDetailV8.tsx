import { useEffect, useMemo, useState } from "react";
import Sparkline from "../app/Sparkline";
import {
  formatNum,
  formatPct,
  loadLatestSignals,
  loadPriceHistory,
  ratingLabel,
  technicalSnapshot,
} from "../lib/v8Data";
import type { PriceRow, SignalRow } from "../types/v8";

export default function StockDetailV8({
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
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "資料讀取失敗"),
      );
  }, [symbol]);

  const closes = prices
    .map((row) => Number(row.close))
    .filter(Number.isFinite);
  const snapshot = useMemo(() => technicalSnapshot(prices), [prices]);

  const plan = useMemo(() => {
    const score = Number(signal?.score ?? 0);
    const risk = Number(signal?.risk_score ?? 50);
    if (score >= 70 && risk < 50) return "分批布局：等待拉回 MA20 附近或量價再度轉強，單筆風險控制在總資金 1% 內。";
    if (score >= 50) return "觀察為主：等待 MA20 上穿 MA60、RSI 回到 50 以上再提高部位。";
    return "防守優先：避免追價，若已持有則設定移動停損並降低曝險。";
  }, [signal]);

  const stopLoss =
    snapshot.latest != null && snapshot.low60 != null
      ? Math.max(snapshot.low60, snapshot.latest * 0.92)
      : null;
  const takeProfit =
    snapshot.latest != null ? snapshot.latest * 1.12 : null;

  return (
    <section>
      <button className="nav active" onClick={onBack}>← 返回總覽</button>
      <div className="page-title">
        <div>
          <div className="eyebrow">V8 STOCK INTELLIGENCE</div>
          <h1>{symbol} {signal?.name ?? ""}</h1>
          <p>AI 評級、技術指標、交易計畫與風險控制。</p>
        </div>
        <span className={`rating rating-${signal?.rating?.toLowerCase()}`}>
          {ratingLabel(signal?.rating)}
        </span>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <div className="metric"><span>最新收盤</span><strong>{formatNum(snapshot.latest, 2)}</strong><small>{prices.length ? prices[prices.length - 1].trade_date : "—"}</small></div>
        <div className="metric"><span>20 日報酬</span><strong>{formatPct(snapshot.change20)}</strong><small>近期動能</small></div>
        <div className="metric"><span>RSI 14</span><strong>{formatNum(snapshot.rsi14)}</strong><small>70 以上偏熱、30 以下偏弱</small></div>
        <div className="metric"><span>策略 Score</span><strong>{formatNum(signal?.score)}</strong><small>{signal?.strategy_version ?? "—"}</small></div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">價格趨勢</div>
          <Sparkline values={closes.slice(-180)} height={270} label="近 180 日收盤價" />
        </div>
        <div className="panel">
          <div className="panel-title">技術指標</div>
          <div className="regime"><span>MA20</span><strong>{formatNum(snapshot.ma20, 2)}</strong></div>
          <div className="regime"><span>MA60</span><strong>{formatNum(snapshot.ma60, 2)}</strong></div>
          <div className="regime"><span>20 日波動</span><strong>{formatPct(snapshot.volatility20)}</strong></div>
          <div className="regime"><span>60 日區間</span><strong>{formatNum(snapshot.low60, 1)}–{formatNum(snapshot.high60, 1)}</strong></div>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">AI 交易計畫</div>
          <div className="report-action">{plan}</div>
        </div>
        <div className="panel">
          <div className="panel-title">風險控制</div>
          <div className="regime"><span>參考停損</span><strong>{formatNum(stopLoss, 2)}</strong></div>
          <div className="regime"><span>參考停利</span><strong>{formatNum(takeProfit, 2)}</strong></div>
          <div className="regime"><span>建議單股權重</span><strong>{Number(signal?.risk_score ?? 100) < 40 ? "15%" : Number(signal?.risk_score ?? 100) < 60 ? "10%" : "5%"}</strong></div>
        </div>
      </div>
    </section>
  );
}
