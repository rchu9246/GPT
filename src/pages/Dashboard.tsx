import { useEffect, useMemo, useState } from "react";
import { supabase } from "../lib/supabase";
import type { Signal } from "../types/quant";

type LoadState =
  | "loading"
  | "connected"
  | "empty"
  | "error"
  | "not-configured";

type FeatureRow = {
  stock_id: number;
  trade_date: string;
  close: number | null;
  return_1d: number | null;
  return_5d: number | null;
  return_20d: number | null;
  ma20: number | null;
  ma60: number | null;
  rsi14: number | null;
  volatility_20d: number | null;
};

type MarketSummary = {
  label: string;
  detail: string;
  healthScore: number;
  averageScore: number;
  averageReturn20d: number;
  bullishRatio: number;
};

const STRATEGY_VERSION = "V2.5-AUTO";

export default function Dashboard() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [features, setFeatures] = useState<FeatureRow[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      if (!supabase) {
        if (active) setState("not-configured");
        return;
      }

      setState("loading");
      setErrorMessage("");

      const signalResult = await supabase
        .from("signals")
        .select(`
          *,
          stocks (
            symbol,
            name,
            industry
          )
        `)
        .eq("strategy_version", STRATEGY_VERSION)
        .order("trade_date", { ascending: false })
        .order("total_score", { ascending: false })
        .limit(200);

      if (!active) return;

      if (signalResult.error) {
        console.error("Dashboard signal query failed:", signalResult.error);
        setErrorMessage(signalResult.error.message);
        setState("error");
        return;
      }

      const loadedSignals =
        (signalResult.data ?? []) as unknown as Signal[];

      if (loadedSignals.length === 0) {
        setSignals([]);
        setFeatures([]);
        setState("empty");
        return;
      }

      const latestDate = loadedSignals[0].trade_date;
      const latestSignals = loadedSignals.filter(
        (signal) => signal.trade_date === latestDate,
      );
      const stockIds = latestSignals.map((signal) => signal.stock_id);

      const featureResult = await supabase
        .from("features")
        .select(`
          stock_id,
          trade_date,
          close,
          return_1d,
          return_5d,
          return_20d,
          ma20,
          ma60,
          rsi14,
          volatility_20d
        `)
        .eq("trade_date", latestDate)
        .in("stock_id", stockIds);

      if (!active) return;

      if (featureResult.error) {
        console.warn(
          "Dashboard feature query failed:",
          featureResult.error,
        );
      }

      setSignals(latestSignals);
      setFeatures((featureResult.data ?? []) as FeatureRow[]);
      setState("connected");
    }

    loadDashboard();

    return () => {
      active = false;
    };
  }, []);

  const latestDate = signals[0]?.trade_date ?? null;

  const candidateCount = useMemo(
    () => signals.filter((signal) => signal.total_score >= 70).length,
    [signals],
  );

  const strongBuyCount = useMemo(
    () => signals.filter((signal) => signal.total_score >= 90).length,
    [signals],
  );

  const riskCount = useMemo(
    () =>
      signals.filter(
        (signal) =>
          signal.risk_score < 45 ||
          signal.total_score < 40,
      ).length,
    [signals],
  );

  const marketSummary = useMemo<MarketSummary>(() => {
    if (signals.length === 0) {
      return {
        label: "等待資料",
        detail: "尚無可計算訊號",
        healthScore: 0,
        averageScore: 0,
        averageReturn20d: 0,
        bullishRatio: 0,
      };
    }

    const averageScore =
      signals.reduce(
        (sum, signal) => sum + Number(signal.total_score || 0),
        0,
      ) / signals.length;

    const bullishSignals = signals.filter(
      (signal) =>
        signal.total_score >= 60 &&
        signal.trend_score >= 50,
    ).length;

    const bullishRatio = bullishSignals / signals.length;

    const validReturns = features
      .map((feature) => Number(feature.return_20d))
      .filter((value) => Number.isFinite(value));

    const averageReturn20d =
      validReturns.length > 0
        ? validReturns.reduce((sum, value) => sum + value, 0) /
          validReturns.length
        : 0;

    const averageRisk =
      signals.reduce(
        (sum, signal) => sum + Number(signal.risk_score || 0),
        0,
      ) / signals.length;

    const healthScore = clamp(
      averageScore * 0.5 +
        averageRisk * 0.25 +
        bullishRatio * 100 * 0.25,
    );

    let label = "空頭";
    if (averageScore >= 70 && bullishRatio >= 0.6) {
      label = "強勢多頭";
    } else if (averageScore >= 55 && bullishRatio >= 0.5) {
      label = "偏多";
    } else if (averageScore >= 45) {
      label = "中性整理";
    } else if (averageScore >= 35) {
      label = "偏空";
    }

    return {
      label,
      detail: `平均分數 ${averageScore.toFixed(1)} · 20日平均報酬 ${formatPercent(
        averageReturn20d,
      )}`,
      healthScore: Math.round(healthScore),
      averageScore,
      averageReturn20d,
      bullishRatio,
    };
  }, [signals, features]);

  const statusText = {
    loading: "正在讀取 Supabase 最新量化資料…",
    connected: `Supabase 已連線 · 策略 ${STRATEGY_VERSION} · 最新訊號日 ${
      latestDate ?? "—"
    } · ${signals.length} 檔`,
    empty: `Supabase 已連線，但目前沒有 ${STRATEGY_VERSION} 訊號`,
    error: `Supabase 查詢失敗：${errorMessage}`,
    "not-configured":
      "找不到 Supabase 環境變數，請檢查 GitHub Actions Secrets",
  }[state];

  return (
    <section>
      <div className="hero">
        <div>
          <div className="eyebrow">
            GPT QUANT V3 · LIVE DATA
          </div>
          <h1>今日策略總覽</h1>
          <p>{statusText}</p>
        </div>

        <div className="health">
          <span>策略健康度</span>
          <strong>{marketSummary.healthScore}</strong>
          <small>
            {" "}
            / 100 · {healthLabel(marketSummary.healthScore)}
          </small>
        </div>
      </div>

      <div className="cards">
        <Metric
          title="市場狀態"
          value={marketSummary.label}
          sub={marketSummary.detail}
        />
        <Metric
          title="今日候選"
          value={String(candidateCount)}
          sub="Score ≥ 70"
        />
        <Metric
          title="S級強多"
          value={String(strongBuyCount)}
          sub="Score ≥ 90"
        />
        <Metric
          title="風險警示"
          value={String(riskCount)}
          sub="Risk < 45 或 Score < 40"
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">
            🚀 最新自動量化訊號
          </div>

          {state === "loading" && <p>載入中…</p>}

          {state === "empty" && (
            <p>
              尚無自動訊號。請執行 GitHub Actions 的
              「Update Taiwan Market Data」。
            </p>
          )}

          {state === "error" && (
            <p>無法讀取資料：{errorMessage}</p>
          )}

          {state === "not-configured" && (
            <p>尚未設定 Supabase 連線。</p>
          )}

          {signals.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>股票</th>
                    <th>Score</th>
                    <th>趨勢</th>
                    <th>動能</th>
                    <th>風險</th>
                    <th>訊號</th>
                    <th>信心</th>
                  </tr>
                </thead>
                <tbody>
                  {signals
                    .slice()
                    .sort(
                      (a, b) =>
                        Number(b.total_score) -
                        Number(a.total_score),
                    )
                    .slice(0, 20)
                    .map((signal, index) => (
                      <tr
                        key={signal.id}
                        className="clickable"
                        onClick={() => {
                          const symbol =
                            signal.stocks?.symbol;
                          if (symbol) {
                            location.hash = `#/stock/${symbol}`;
                          }
                        }}
                      >
                        <td>{index + 1}</td>
                        <td>
                          <b>
                            {signal.stocks?.symbol ?? "—"}
                          </b>{" "}
                          {signal.stocks?.name ?? "未知股票"}
                        </td>
                        <td>
                          <strong>
                            {formatNumber(
                              signal.total_score,
                            )}
                          </strong>
                        </td>
                        <td>
                          {formatNumber(signal.trend_score)}
                        </td>
                        <td>
                          {formatNumber(
                            signal.momentum_score,
                          )}
                        </td>
                        <td>
                          {formatNumber(signal.risk_score)}
                        </td>
                        <td>{signal.signal}</td>
                        <td>
                          {formatNumber(signal.confidence)}%
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div>
          <div className="panel">
            <div className="panel-title">
              🌎 真實市場摘要
            </div>
            <Regime
              name="市場狀態"
              state={marketSummary.label}
            />
            <Regime
              name="平均 Score"
              state={marketSummary.averageScore.toFixed(1)}
            />
            <Regime
              name="多頭比例"
              state={formatPercent(
                marketSummary.bullishRatio * 100,
              )}
            />
            <Regime
              name="20日平均報酬"
              state={formatPercent(
                marketSummary.averageReturn20d,
              )}
            />
            <Regime
              name="最新交易日"
              state={latestDate ?? "—"}
            />
          </div>

          <div className="panel">
            <div className="panel-title">
              ⚙️ 資料品質
            </div>
            <Regime
              name="策略版本"
              state={STRATEGY_VERSION}
            />
            <Regime
              name="訊號筆數"
              state={String(signals.length)}
            />
            <Regime
              name="特徵筆數"
              state={String(features.length)}
            />
            <Regime
              name="資料狀態"
              state={
                signals.length > 0 &&
                features.length === signals.length
                  ? "完整"
                  : "部分缺漏"
              }
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function clamp(
  value: number,
  minimum = 0,
  maximum = 100,
) {
  return Math.max(minimum, Math.min(maximum, value));
}

function formatNumber(value: number | null | undefined) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1) : "—";
}

function formatPercent(value: number | null | undefined) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${number >= 0 ? "+" : ""}${number.toFixed(1)}%`;
}

function healthLabel(score: number) {
  if (score >= 80) return "🟢 HEALTHY";
  if (score >= 60) return "🟡 WATCH";
  if (score >= 40) return "🟠 WEAK";
  return "🔴 RISK";
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

function Regime({
  name,
  state,
}: {
  name: string;
  state: string;
}) {
  return (
    <div className="regime">
      <span>{name}</span>
      <b>{state}</b>
    </div>
  );
}
