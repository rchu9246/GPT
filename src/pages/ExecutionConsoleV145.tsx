import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import Sparkline from "../app/Sparkline";
import {
  loadPaperOperationsV14,
  maxDrawdownV145,
  moneyV14,
  percentV14,
  tradeStatsV145,
} from "../lib/v14Operations";
import type { PaperOperationsV14 } from "../types/v14";

const EMPTY: PaperOperationsV14 = {
  account: null,
  positions: [],
  orders: [],
  fills: [],
  snapshots: [],
  runs: [],
};

export default function ExecutionConsoleV145() {
  const [data, setData] = useState<PaperOperationsV14>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setData(await loadPaperOperationsV14());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "讀取失敗");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const pending = data.orders.filter((order) => order.status === "PROPOSED");
  const approved = data.orders.filter((order) => order.status === "APPROVED");
  const equity = data.snapshots.map((row) => row.equity);
  const drawdown = maxDrawdownV145(equity);
  const stats = useMemo(() => tradeStatsV145(data.fills), [data.fills]);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V14.5 EXECUTION CONSOLE</div>
          <h1>委託審核與績效中心</h1>
          <p>核准佇列、模擬成交、交易日誌、勝率與最大回撤監控。</p>
        </div>
        <button className="nav active" onClick={() => void refresh()}>
          {loading ? "讀取中" : "重新整理"}
        </button>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <MetricCard label="待核准" value={String(pending.length)} note="PROPOSED" />
        <MetricCard label="待成交" value={String(approved.length)} note="APPROVED" />
        <MetricCard
          label="已平倉勝率"
          value={percentV14(stats.winRate)}
          note={`${stats.wins} 勝 / ${stats.losses} 負`}
        />
        <MetricCard
          label="最大回撤"
          value={percentV14(drawdown)}
          note={`Profit Factor ${stats.profitFactor.toFixed(2)}`}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Paper 淨值曲線</div>
          <Sparkline values={equity} height={250} />
        </div>

        <div className="panel">
          <div className="panel-title">安全執行流程</div>
          <div className="execution-step"><b>1</b><span>在下方複製完整 Order ID</span></div>
          <div className="execution-step"><b>2</b><span>Actions → V14.5 Review Paper Order</span></div>
          <div className="execution-step"><b>3</b><span>選 APPROVE 或 REJECT</span></div>
          <div className="execution-step"><b>4</b><span>Actions → V14.5 Fill Approved Orders</span></div>
          <p className="report-summary">
            公開網站保持唯讀，核准與成交只能由 GitHub Actions 使用 Service Role 執行。
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">候選委託佇列</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>完整 Order ID</th><th>股票</th><th>方向</th><th>數量</th>
                <th>參考價</th><th>Score</th><th>風險</th><th>狀態</th>
              </tr>
            </thead>
            <tbody>
              {data.orders.slice(0, 30).map((order) => (
                <tr key={order.id}>
                  <td><code>{order.id}</code></td>
                  <td><strong>{order.symbol}</strong></td>
                  <td>{order.side}</td>
                  <td>{order.quantity}</td>
                  <td>{moneyV14(order.reference_price)}</td>
                  <td>{order.score?.toFixed(1) ?? "—"}</td>
                  <td>{order.risk_score?.toFixed(1) ?? "—"}</td>
                  <td><span className={`order-status status-${order.status.toLowerCase()}`}>{order.status}</span></td>
                </tr>
              ))}
              {!loading && data.orders.length === 0 && (
                <tr><td colSpan={8}>目前沒有委託。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">交易日誌</div>
          <div className="run-list">
            {data.fills.slice(0, 20).map((fill) => (
              <div className="run-item" key={fill.id}>
                <span>{fill.side} {fill.symbol} × {fill.quantity}</span>
                <b>{moneyV14(fill.realized_pnl)}</b>
                <small>{moneyV14(fill.fill_price)} · {fill.trade_date}</small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">每日績效</div>
          <div className="run-list">
            {data.snapshots.slice().reverse().slice(0, 20).map((row) => (
              <div className="run-item" key={row.snapshot_date}>
                <span>{row.snapshot_date}</span>
                <b>{moneyV14(row.equity)}</b>
                <small>總報酬 {percentV14(row.total_return)} · 持倉 {row.positions_count}</small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
