import { useEffect, useMemo, useState } from "react";
import { supabase } from "../lib/supabase";
import type { Signal } from "../types/quant";

type ConnectionState = "loading" | "connected" | "empty" | "error" | "not-configured";

export default function Dashboard() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("loading");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let active = true;

    async function loadSignals() {
      if (!supabase) {
        if (active) setConnectionState("not-configured");
        return;
      }

      const { data, error } = await supabase
        .from("signals")
        .select(`
          *,
          stocks (
            symbol,
            name,
            industry
          )
        `)
        .order("total_score", { ascending: false })
        .limit(10);

      if (!active) return;

      if (error) {
        console.error("Supabase signals query failed:", error);
        setErrorMessage(error.message);
        setConnectionState("error");
        return;
      }

      setSignals((data ?? []) as unknown as Signal[]);
      setConnectionState(data?.length ? "connected" : "empty");
    }

    loadSignals();

    return () => {
      active = false;
    };
  }, []);

  const candidateCount = useMemo(
    () => signals.filter((signal) => signal.total_score >= 70).length,
    [signals],
  );

  const strongBuyCount = useMemo(
    () => signals.filter((signal) => signal.total_score >= 90).length,
    [signals],
  );

  const statusText = {
    loading: "正在連線 Supabase…",
    connected: `Supabase 已連線，目前載入 ${signals.length} 筆訊號`,
    empty: "Supabase 已連線，但 signals 資料表目前沒有資料",
    error: `Supabase 查詢失敗：${errorMessage}`,
    "not-configured":
      "找不到 Supabase 環境變數，請檢查 GitHub Actions Secrets 並重新部署",
  }[connectionState];

  return (
    <section>
      <div className="hero">
        <div>
          <div className="eyebrow">QUANT TRADING CENTER</div>
          <h1>今日策略總覽</h1>
          <p>{statusText}</p>
        </div>

        <div className="health">
          <span>策略健康度</span>
          <strong>84</strong>
          <small> / 100 · 🟢 HEALTHY</small>
        </div>
      </div>

      <div className="cards">
        <Metric title="市場狀態" value="🟢 偏多" sub="TAIEX / SOX / Nasdaq" />
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
        <Metric title="風險警示" value="0" sub="需人工檢視" />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">🚀 今日 TOP 訊號</div>

          {connectionState === "loading" && <p>載入中…</p>}

          {connectionState === "error" && (
            <p>
              無法讀取 Supabase。請檢查 RLS Policy、資料表名稱與 GitHub
              Secrets。
            </p>
          )}

          {connectionState === "not-configured" && (
            <p>目前沒有載入 Demo 資料，以避免誤判為真實訊號。</p>
          )}

          {connectionState === "empty" && (
            <p>目前尚無訊號。請先在 Supabase 的 signals 表新增資料。</p>
          )}

          {signals.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>股票</th>
                    <th>Score</th>
                    <th>訊號</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((signal, index) => (
                    <tr
                      key={signal.id}
                      onClick={() => {
                        const symbol = signal.stocks?.symbol;
                        if (symbol) location.hash = `#/stock/${symbol}`;
                      }}
                      className="clickable"
                    >
                      <td>{index + 1}</td>
                      <td>
                        <b>{signal.stocks?.symbol ?? "—"}</b>{" "}
                        {signal.stocks?.name ?? "未知股票"}
                      </td>
                      <td>
                        <strong>{signal.total_score}</strong>
                      </td>
                      <td>{signal.signal}</td>
                      <td>{signal.confidence}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">🌎 Market Regime</div>
          <Regime name="TAIEX" state="🟢 多頭" />
          <Regime name="SOX" state="🟢 多頭" />
          <Regime name="Nasdaq" state="🟢 多頭" />
          <Regime name="USD/TWD" state="🟡 中性" />
          <Regime name="Strategy" state="🟢 Healthy" />
        </div>
      </div>
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

function Regime({ name, state }: { name: string; state: string }) {
  return (
    <div className="regime">
      <span>{name}</span>
      <b>{state}</b>
    </div>
  );
}
