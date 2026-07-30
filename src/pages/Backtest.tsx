import { useEffect, useMemo, useState } from "react";
import { supabase } from "../lib/supabase";
import type { BacktestRun, BacktestTrade } from "../types/quant";

export default function Backtest() {
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null);
  const [trades, setTrades] = useState<BacktestTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadRuns();
  }, []);

  async function loadRuns() {
    if (!supabase) {
      setError("Supabase 尚未設定");
      setLoading(false);
      return;
    }

    const { data, error: queryError } = await supabase
      .from("backtest_runs")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(30);

    if (queryError) {
      setError(queryError.message);
      setLoading(false);
      return;
    }

    const loaded = (data ?? []) as BacktestRun[];
    setRuns(loaded);
    setLoading(false);
    if (loaded[0]) selectRun(loaded[0]);
  }

  async function selectRun(run: BacktestRun) {
    setSelectedRun(run);
    setTrades([]);
    if (!supabase) return;

    const { data, error: queryError } = await supabase
      .from("backtest_trades")
      .select("*, stocks(symbol,name,industry)")
      .eq("run_id", run.id)
      .order("entry_date", { ascending: false })
      .limit(200);

    if (queryError) {
      setError(queryError.message);
      return;
    }
    setTrades((data ?? []) as unknown as BacktestTrade[]);
  }

  const curve = selectedRun?.equity_curve ?? [];
  const minEquity = Math.min(...curve.map((point) => point.equity), 0);
  const maxEquity = Math.max(...curve.map((point) => point.equity), 1);
  const curvePoints = useMemo(
    () =>
      curve.map((point, index) => ({
        ...point,
        width: curve.length <= 1 ? 100 : (index / (curve.length - 1)) * 100,
        height:
          maxEquity === minEquity
            ? 50
            : ((point.equity - minEquity) / (maxEquity - minEquity)) * 100,
      })),
    [curve, minEquity, maxEquity],
  );

  return (
    <section>
      <div className="page-title">
        <h1>GPT Quant V4 回測中心</h1>
        <p>
          T 日產生訊號、T+1 開盤成交，納入手續費、證交稅與滑價。
          回測由 GitHub Actions 執行並寫入 Supabase。
        </p>
      </div>

      {loading && <div className="panel">載入回測結果中…</div>}
      {error && <div className="panel">錯誤：{error}</div>}

      {!loading && runs.length === 0 && (
        <div className="panel">
          尚無回測結果。到 GitHub Actions 執行「Run Quant Backtest」。
        </div>
      )}

      {selectedRun && (
        <>
          <div className="cards">
            <Metric title="總報酬" value={percent(selectedRun.total_return)} sub={selectedRun.strategy_version} />
            <Metric title="年化報酬" value={percent(selectedRun.annual_return)} sub={`${selectedRun.start_date} → ${selectedRun.end_date}`} />
            <Metric title="勝率" value={percent(selectedRun.win_rate)} sub={`${selectedRun.total_trades ?? 0} 筆交易`} />
            <Metric title="Profit Factor" value={number(selectedRun.profit_factor)} sub="總獲利 / 總虧損" />
            <Metric title="最大回撤" value={percent(selectedRun.max_drawdown, true)} sub="資金高點至低點" />
            <Metric title="Sharpe" value={number(selectedRun.sharpe_ratio)} sub="風險調整報酬" />
          </div>

          <div className="grid2">
            <div className="panel">
              <div className="panel-title">📈 資金曲線</div>
              {curvePoints.length > 1 ? (
                <div className="equity-chart">
                  {curvePoints.map((point) => (
                    <span
                      key={point.trade}
                      title={`交易 ${point.trade}: ${point.equity.toLocaleString()}`}
                      style={{
                        left: `${point.width}%`,
                        bottom: `${point.height}%`,
                      }}
                    />
                  ))}
                </div>
              ) : (
                <p>尚無足夠交易繪製資金曲線。</p>
              )}
              <div className="regime">
                <span>初始資金</span>
                <b>{money(selectedRun.initial_capital)}</b>
              </div>
              <div className="regime">
                <span>期末資金</span>
                <b>{money(selectedRun.final_capital)}</b>
              </div>
            </div>

            <div className="panel">
              <div className="panel-title">🧪 回測執行紀錄</div>
              <div className="run-list">
                {runs.map((run) => (
                  <button
                    key={run.id}
                    className={`run-item ${run.id === selectedRun.id ? "active" : ""}`}
                    onClick={() => selectRun(run)}
                  >
                    <b>{run.strategy_version}</b>
                    <span>{run.created_at.slice(0, 10)}</span>
                    <span>{percent(run.total_return)}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-title">📋 最近交易明細</div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>股票</th>
                    <th>訊號日</th>
                    <th>進場</th>
                    <th>出場</th>
                    <th>Score</th>
                    <th>淨報酬</th>
                    <th>P&L</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade) => (
                    <tr key={trade.id}>
                      <td>
                        <b>{trade.stocks?.symbol ?? trade.stock_id}</b>{" "}
                        {trade.stocks?.name ?? ""}
                      </td>
                      <td>{trade.signal_date}</td>
                      <td>{trade.entry_date} · {number(trade.entry_price)}</td>
                      <td>{trade.exit_date ?? "—"} · {number(trade.exit_price)}</td>
                      <td>{number(trade.score)}</td>
                      <td>{percent(trade.net_return)}</td>
                      <td>{money(trade.pnl)}</td>
                      <td>{exitReason(trade.exit_reason)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Metric({ title, value, sub }: { title: string; value: string; sub: string }) {
  return (
    <div className="metric">
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function percent(value: number | null | undefined, negative = false) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "—";
  const adjusted = negative ? -Math.abs(numberValue) : numberValue;
  return `${adjusted >= 0 ? "+" : ""}${(adjusted * 100).toFixed(2)}%`;
}

function number(value: number | null | undefined) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue.toFixed(2) : "—";
}

function money(value: number | null | undefined) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 0 }).format(numberValue)
    : "—";
}

function exitReason(value: string) {
  return value === "TARGET" ? "停利" : value === "STOP" ? "停損" : "時間出場";
}
