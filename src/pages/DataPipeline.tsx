import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";

type PipelineStatus = {
  latestPriceDate: string | null;
  priceRows: number;
  featureRows: number;
  signalRows: number;
  latestSignalDate: string | null;
  latestStrategy: string | null;
};

export default function DataPipeline() {
  const [status, setStatus] = useState<PipelineStatus>({
    latestPriceDate: null,
    priceRows: 0,
    featureRows: 0,
    signalRows: 0,
    latestSignalDate: null,
    latestStrategy: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadStatus() {
      if (!supabase) {
        setError("Supabase 尚未設定");
        setLoading(false);
        return;
      }

      const [
        pricesCount,
        latestPrice,
        featuresCount,
        signalsCount,
        latestSignal,
      ] = await Promise.all([
        supabase
          .from("daily_prices")
          .select("id", { count: "exact", head: true }),
        supabase
          .from("daily_prices")
          .select("trade_date")
          .order("trade_date", { ascending: false })
          .limit(1),
        supabase
          .from("features")
          .select("id", { count: "exact", head: true }),
        supabase
          .from("signals")
          .select("id", { count: "exact", head: true }),
        supabase
          .from("signals")
          .select("trade_date,strategy_version")
          .order("trade_date", { ascending: false })
          .order("created_at", { ascending: false })
          .limit(1),
      ]);

      if (!active) return;

      const firstError =
        pricesCount.error ||
        latestPrice.error ||
        featuresCount.error ||
        signalsCount.error ||
        latestSignal.error;

      if (firstError) {
        setError(firstError.message);
        setLoading(false);
        return;
      }

      setStatus({
        latestPriceDate: latestPrice.data?.[0]?.trade_date ?? null,
        priceRows: pricesCount.count ?? 0,
        featureRows: featuresCount.count ?? 0,
        signalRows: signalsCount.count ?? 0,
        latestSignalDate: latestSignal.data?.[0]?.trade_date ?? null,
        latestStrategy: latestSignal.data?.[0]?.strategy_version ?? null,
      });
      setLoading(false);
    }

    loadStatus();

    return () => {
      active = false;
    };
  }, []);

  return (
    <section>
      <div className="page-title">
        <h1>資料管線中心</h1>
        <p>
          FinMind → GitHub Actions → Supabase → Features → Signals → Backtest
        </p>
      </div>

      {loading && <div className="panel">正在讀取資料狀態…</div>}
      {error && <div className="panel">錯誤：{error}</div>}

      {!loading && !error && (
        <>
          <div className="cards">
            <Metric
              title="歷史行情"
              value={String(status.priceRows)}
              sub={`最新 ${status.latestPriceDate ?? "—"}`}
            />
            <Metric
              title="Feature 筆數"
              value={String(status.featureRows)}
              sub="技術與量價特徵"
            />
            <Metric
              title="Signal 筆數"
              value={String(status.signalRows)}
              sub={`最新 ${status.latestSignalDate ?? "—"}`}
            />
            <Metric
              title="最新策略"
              value={status.latestStrategy ?? "—"}
              sub="目前資料庫最新版本"
            />
          </div>

          <div className="grid2">
            <div className="panel">
              <div className="panel-title">⚙️ 每日自動更新流程</div>
              <PipelineStep
                index="1"
                title="抓取市場資料"
                detail="GitHub Actions：Update Taiwan Market Data"
              />
              <PipelineStep
                index="2"
                title="寫入 daily_prices"
                detail="保存 OHLCV 歷史行情"
              />
              <PipelineStep
                index="3"
                title="計算 Features"
                detail="EMA、RSI、KD、MACD、ATR、量能與突破"
              />
              <PipelineStep
                index="4"
                title="產生 Signals"
                detail="V3.1-MULTI 多因子分數與風險控制"
              />
              <PipelineStep
                index="5"
                title="執行回測"
                detail="GitHub Actions：Run Quant Backtest"
              />
            </div>

            <div className="panel">
              <div className="panel-title">🧭 操作方式</div>
              <p>
                市場資料更新：到 GitHub Actions 執行
                「Update Taiwan Market Data」。
              </p>
              <p>
                歷史回測：到 GitHub Actions 執行
                「Run Quant Backtest」。
              </p>
              <p>
                GitHub Actions 排程可能因平台負載延遲數分鐘，這是正常現象。
              </p>
              <p>
                Service Role Key 僅用於 GitHub Actions，不會傳送到前端網站。
              </p>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Metric({
  title,
  value,
  sub,
}: {
  title: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="metric">
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function PipelineStep({
  index,
  title,
  detail,
}: {
  index: string;
  title: string;
  detail: string;
}) {
  return (
    <div className="regime">
      <span>
        <b>{index}</b> · {title}
      </span>
      <small>{detail}</small>
    </div>
  );
}
