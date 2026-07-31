import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { accountEquity, loadTradingState, saveTradingState } from "../lib/v13Trading";
import type { TradingState } from "../types/v13";

function currency(value: number): string {
  return new Intl.NumberFormat("zh-TW", { style: "currency", currency: "TWD", maximumFractionDigits: 0 }).format(value);
}

export default function TradeLedgerV13() {
  const [state, setState] = useState<TradingState>(loadTradingState);
  useEffect(() => saveTradingState(state), [state]);
  const equity = accountEquity(state);
  const pnl = equity - state.account.initialEquity;
  const filled = state.orders.filter((order) => order.status === "FILLED");

  return (
    <section>
      <div className="page-title">
        <div><div className="eyebrow">V13 PAPER PORTFOLIO LEDGER</div><h1>持倉與成交帳本</h1><p>模擬成交、持倉、市值與損益紀錄。</p></div>
      </div>
      <div className="cards">
        <MetricCard label="帳戶淨值" value={currency(equity)} note="Cash + Positions" />
        <MetricCard label="累計損益" value={currency(pnl)} note={`${(pnl / Math.max(1, state.account.initialEquity) * 100).toFixed(2)}%`} />
        <MetricCard label="持倉數" value={String(state.positions.length)} note="Paper Positions" />
        <MetricCard label="成交筆數" value={String(filled.length)} note="Filled Orders" />
      </div>
      <div className="panel">
        <div className="panel-title">目前持倉</div>
        <div className="table-wrap"><table><thead><tr><th>股票</th><th>數量</th><th>均價</th><th>最新價</th><th>市值</th><th>未實現損益</th></tr></thead><tbody>
          {state.positions.map((position) => <tr key={position.symbol}><td><strong>{position.symbol}</strong> {position.name ?? ""}</td><td>{position.quantity}</td><td>{position.averagePrice.toFixed(2)}</td><td>{position.lastPrice.toFixed(2)}</td><td>{currency(position.marketValue)}</td><td>{currency(position.unrealizedPnl)} ({(position.unrealizedPnlPct * 100).toFixed(2)}%)</td></tr>)}
          {!state.positions.length && <tr><td colSpan={6}>目前沒有模擬持倉。</td></tr>}
        </tbody></table></div>
      </div>
      <div className="panel">
        <div className="panel-title">成交紀錄</div>
        <div className="table-wrap"><table><thead><tr><th>時間</th><th>股票</th><th>方向</th><th>數量</th><th>價格</th><th>金額</th><th>模式</th></tr></thead><tbody>
          {filled.map((order) => <tr key={order.id}><td>{order.createdAt.replace("T", " ").slice(0, 19)}</td><td>{order.symbol}</td><td>{order.side}</td><td>{order.quantity}</td><td>{order.referencePrice.toFixed(2)}</td><td>{currency(order.notional)}</td><td>{order.mode}</td></tr>)}
          {!filled.length && <tr><td colSpan={7}>尚無成交紀錄。</td></tr>}
        </tbody></table></div>
      </div>
    </section>
  );
}
