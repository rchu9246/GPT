import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { moneyV14 } from "../lib/v14Operations";
import { loadPortfolioDecisionsV17 } from "../lib/v17Portfolio";
import type { PortfolioDecisionV17 } from "../types/v17";

export default function PortfolioOSV17() {
  const [rows, setRows] = useState<PortfolioDecisionV17[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadPortfolioDecisionsV17()
      .then(setRows)
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const sells = rows.filter((row) => row.decision === "SELL");
  const holds = rows.filter((row) => row.decision === "HOLD");
  const totalValue = rows.reduce(
    (sum, row) => sum + Number(row.market_value ?? 0),
    0,
  );
  const totalPnl = rows.reduce(
    (sum, row) => sum + Number(row.unrealized_pnl ?? 0),
    0,
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V17 ENTERPRISE PORTFOLIO OS</div>
          <h1>投資組合生命週期管理</h1>
          <p>
            持倉監控、停損、停利、Trailing Stop、持有天數與可解釋退出決策。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <MetricCard label="投資組合市值" value={moneyV14(totalValue)} note={`${rows.length} 筆決策`} />
        <MetricCard label="未實現損益" value={moneyV14(totalPnl)} note="Mark-to-Market" />
        <MetricCard label="退出建議" value={String(sells.length)} note="SELL" />
        <MetricCard label="續抱建議" value={String(holds.length)} note="HOLD" />
      </div>

      <div className="panel">
        <div className="panel-title">可解釋投資組合決策</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th><th>股票</th><th>決策</th><th>原因</th>
                <th>數量</th><th>均價</th><th>現價</th><th>未實現損益</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.id}-${row.reason_code}`}>
                  <td>{row.decision_date}</td>
                  <td><strong>{row.symbol}</strong></td>
                  <td>{row.decision}</td>
                  <td>{row.reason_message ?? row.reason_code}</td>
                  <td>{row.quantity ?? 0}</td>
                  <td>{moneyV14(row.average_price)}</td>
                  <td>{moneyV14(row.current_price)}</td>
                  <td>{moneyV14(row.unrealized_pnl)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={8}>尚無 Portfolio OS 決策資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">V17 自動流程</div>
        <div className="execution-step"><b>1</b><span>V16 產生可解釋買進委託</span></div>
        <div className="execution-step"><b>2</b><span>Review / Fill 建立 Paper 持倉</span></div>
        <div className="execution-step"><b>3</b><span>V17 每日更新持倉市值與高水位</span></div>
        <div className="execution-step"><b>4</b><span>自動產生停損、停利與 Trailing Stop 賣單</span></div>
      </div>
    </section>
  );
}
