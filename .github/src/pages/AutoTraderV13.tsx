import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadLatestSignals } from "../lib/v9Data";
import {
  accountEquity,
  addProposals,
  fillPaperOrder,
  loadTradingState,
  proposeOrders,
  resetPaperAccount,
  saveTradingState,
  updateOrderStatus,
} from "../lib/v13Trading";
import type { SignalRow } from "../types/v9";
import type { TradingMode, TradingState } from "../types/v13";

function currency(value: number): string {
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency: "TWD",
    maximumFractionDigits: 0,
  }).format(value);
}

export default function AutoTraderV13() {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [state, setState] = useState<TradingState>(loadTradingState);

  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  useEffect(() => {
    saveTradingState(state);
  }, [state]);

  const equity = accountEquity(state);
  const pending = state.orders.filter((order) => order.status === "PROPOSED").length;
  const approved = state.orders.filter((order) => order.status === "APPROVED").length;
  const filled = state.orders.filter((order) => order.status === "FILLED").length;
  const exposure = equity === 0
    ? 0
    : state.positions.reduce((sum, position) => sum + position.marketValue, 0) / equity;

  const riskChecks = useMemo(
    () => [
      { label: "Kill Switch", pass: !state.killSwitch, detail: state.killSwitch ? "已停止所有執行" : "正常" },
      { label: "正式交易鎖", pass: state.mode !== "LIVE_LOCKED", detail: state.mode === "LIVE_LOCKED" ? "券商尚未配置" : "Paper/Approval 模式" },
      { label: "現金保留", pass: state.account.cash / Math.max(1, equity) >= state.policy.reserveCashPct / 100, detail: `最低 ${state.policy.reserveCashPct}%` },
      { label: "持股上限", pass: state.positions.length <= state.policy.maxPositions, detail: `${state.positions.length}/${state.policy.maxPositions}` },
    ],
    [state, equity],
  );

  function update(next: TradingState) {
    setState(next);
  }

  function changeMode(mode: TradingMode) {
    update({ ...state, mode });
  }

  function generate() {
    const proposals = proposeOrders(signals, state);
    update(addProposals(state, proposals));
  }

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V13 SAFE AUTOTRADER</div>
          <h1>自動投資控制中心</h1>
          <p>預設 Paper Trading；正式券商下單保持鎖定，憑證不進入瀏覽器。</p>
        </div>
        <span className={`trading-mode mode-${state.mode.toLowerCase()}`}>{state.mode}</span>
      </div>

      <div className="cards">
        <MetricCard label="帳戶淨值" value={currency(equity)} note="Paper Account" />
        <MetricCard label="可用現金" value={currency(state.account.cash)} note={`保留 ${state.policy.reserveCashPct}%`} />
        <MetricCard label="總曝險" value={`${(exposure * 100).toFixed(1)}%`} note={`${state.positions.length} 檔持倉`} />
        <MetricCard label="待核准/已成交" value={`${pending + approved}/${filled}`} note="Order Pipeline" />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">交易模式與緊急控制</div>
          <div className="mode-switcher">
            {(["PAPER", "APPROVAL", "LIVE_LOCKED"] as TradingMode[]).map((mode) => (
              <button key={mode} className={`nav ${state.mode === mode ? "active" : ""}`} onClick={() => changeMode(mode)}>{mode}</button>
            ))}
          </div>
          <button
            className={`kill-switch ${state.killSwitch ? "armed" : ""}`}
            onClick={() => update({ ...state, killSwitch: !state.killSwitch })}
          >
            {state.killSwitch ? "解除緊急停止" : "啟動 KILL SWITCH"}
          </button>
          <p className="report-summary">
            LIVE_LOCKED 只顯示架構，不會送出真實委託。正式交易必須由本機安全代理程式連接券商 API。
          </p>
        </div>

        <div className="panel">
          <div className="panel-title">風控閘門</div>
          {riskChecks.map((check) => (
            <div className="regime" key={check.label}>
              <span>{check.label}</span>
              <strong className={check.pass ? "status-pass" : "status-block"}>{check.pass ? "PASS" : "BLOCK"}</strong>
              <small>{check.detail}</small>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">自動產生委託</div>
        <div className="trade-actions">
          <button className="primary-action" onClick={generate} disabled={state.killSwitch || state.mode === "LIVE_LOCKED"}>依最新訊號產生候選委託</button>
          <button onClick={() => update(resetPaperAccount(state.mode))}>重設模擬帳戶</button>
        </div>
        <p className="report-summary">
          條件：Score ≥ {state.policy.minScore}、Risk ≤ {state.policy.maxRiskScore}、最多 {state.policy.maxPositions} 檔、單股上限 {state.policy.maxPositionPct}%。
        </p>
      </div>

      <div className="panel">
        <div className="panel-title">委託核准佇列</div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>時間</th><th>股票</th><th>方向</th><th>數量</th><th>參考價</th><th>金額</th><th>理由</th><th>狀態</th><th>操作</th></tr></thead>
            <tbody>
              {state.orders.slice(0, 20).map((order) => (
                <tr key={order.id}>
                  <td>{order.createdAt.slice(11, 19)}</td>
                  <td><strong>{order.symbol}</strong> {order.name ?? ""}</td>
                  <td>{order.side}</td>
                  <td>{order.quantity}</td>
                  <td>{order.referencePrice.toFixed(2)}</td>
                  <td>{currency(order.notional)}</td>
                  <td>{order.reason}</td>
                  <td><span className={`order-status status-${order.status.toLowerCase()}`}>{order.status}</span></td>
                  <td>
                    <div className="inline-actions">
                      {order.status === "PROPOSED" && <button onClick={() => update(updateOrderStatus(state, order.id, "APPROVED"))}>核准</button>}
                      {(order.status === "PROPOSED" || order.status === "APPROVED") && <button onClick={() => update(fillPaperOrder(state, order.id))}>模擬成交</button>}
                      {order.status === "PROPOSED" && <button onClick={() => update(updateOrderStatus(state, order.id, "REJECTED"))}>拒絕</button>}
                    </div>
                  </td>
                </tr>
              ))}
              {!state.orders.length && <tr><td colSpan={9}>尚無委託。先按「依最新訊號產生候選委託」。</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
