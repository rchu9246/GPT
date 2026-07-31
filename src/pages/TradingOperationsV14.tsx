import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import Sparkline from "../app/Sparkline";
import {
  loadPaperOperationsV14,
  moneyV14,
  percentV14,
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

export default function TradingOperationsV14() {
  const [data, setData] = useState<PaperOperationsV14>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setData(await loadPaperOperationsV14());
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "無法讀取 Paper Engine 後端資料",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const pending = data.orders.filter((order) =>
    ["PROPOSED", "APPROVED"].includes(order.status),
  ).length;
  const lastRun = data.runs.length > 0 ? data.runs[0] : undefined;
  const totalReturn =
    data.account && data.account.starting_cash !== 0
      ? data.account.equity / data.account.starting_cash - 1
      : 0;
  const equityCurve = useMemo(
    () => data.snapshots.map((snapshot) => snapshot.equity),
    [data.snapshots],
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V14 TRADING OPERATIONS</div>
          <h1>Paper Trading 營運中心</h1>
          <p>直接監控伺服器端帳戶、委託、成交、持倉、淨值與引擎排程。</p>
        </div>
        <button className="nav active" onClick={() => void refresh()}>
          {loading ? "讀取中" : "重新整理"}
        </button>
      </div>

      {error && (
        <div className="alert">
          {error}。請先在 Supabase 執行 V14 單一安裝 SQL，並確認唯讀政策已建立。
        </div>
      )}

      <div className="cards">
        <MetricCard
          label="帳戶淨值"
          value={moneyV14(data.account?.equity)}
          note="伺服器端 Paper Account"
        />
        <MetricCard
          label="可用現金"
          value={moneyV14(data.account?.cash)}
          note={`${data.positions.length} 個持倉`}
        />
        <MetricCard
          label="總報酬"
          value={percentV14(totalReturn)}
          note={`未實現 ${moneyV14(data.account?.unrealized_pnl)}`}
        />
        <MetricCard
          label="待處理委託"
          value={String(pending)}
          note={lastRun ? `最後執行 ${lastRun.status}` : "尚無執行紀錄"}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">帳戶淨值曲線</div>
          <Sparkline values={equityCurve} height={260} />
          <div className="regime">
            <span>已實現損益</span>
            <strong>{moneyV14(data.account?.realized_pnl)}</strong>
          </div>
          <div className="regime">
            <span>手續費／交易稅</span>
            <strong>
              {moneyV14(
                (data.account?.total_fees ?? 0) +
                  (data.account?.total_tax ?? 0),
              )}
            </strong>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">引擎狀態</div>
          <div className="regime">
            <span>最新狀態</span>
            <strong>{lastRun?.status ?? "尚未執行"}</strong>
          </div>
          <div className="regime">
            <span>訊號日期</span>
            <strong>{lastRun?.signals_date ?? "—"}</strong>
          </div>
          <div className="regime">
            <span>買單／賣單／成交</span>
            <strong>
              {lastRun
                ? `${lastRun.buy_orders}/${lastRun.sell_orders}/${lastRun.fills}`
                : "—"}
            </strong>
          </div>
          <p className="report-summary">
            {lastRun?.message ??
              "完成 Supabase 與 GitHub Secrets 設定後，可從 GitHub Actions 手動啟動。"}
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">伺服器端持倉</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>股票</th>
                <th>數量</th>
                <th>均價</th>
                <th>最新價</th>
                <th>市值</th>
                <th>未實現損益</th>
                <th>持有天數</th>
              </tr>
            </thead>
            <tbody>
              {data.positions.map((position) => (
                <tr key={position.symbol}>
                  <td>
                    <strong>{position.symbol}</strong> {position.name ?? ""}
                  </td>
                  <td>{position.quantity}</td>
                  <td>{moneyV14(position.average_price)}</td>
                  <td>{moneyV14(position.last_price)}</td>
                  <td>{moneyV14(position.market_value)}</td>
                  <td>{moneyV14(position.unrealized_pnl)}</td>
                  <td>{position.holding_days ?? "—"}</td>
                </tr>
              ))}
              {!loading && data.positions.length === 0 && (
                <tr>
                  <td colSpan={7}>目前沒有伺服器端模擬持倉。</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">最新委託</div>
          <div className="run-list">
            {data.orders.slice(0, 12).map((order) => (
              <div className="run-item" key={order.id}>
                <span>
                  {order.side} {order.symbol} × {order.quantity}
                </span>
                <b>{order.status}</b>
                <small>
                  {moneyV14(order.fill_price ?? order.reference_price)} ·{" "}
                  {order.signal_date ?? order.created_at.slice(0, 10)}
                </small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">最新成交</div>
          <div className="run-list">
            {data.fills.slice(0, 12).map((fill) => (
              <div className="run-item" key={fill.id}>
                <span>
                  {fill.side} {fill.symbol} × {fill.quantity}
                </span>
                <b>{moneyV14(fill.realized_pnl)}</b>
                <small>
                  {moneyV14(fill.fill_price)} · {fill.trade_date}
                </small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
