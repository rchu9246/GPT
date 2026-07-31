import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { moneyV14, percentV14 } from "../lib/v14Operations";
import { loadHedgeFundV19 } from "../lib/v19HedgeFund";
import type {
  HedgeAllocationV19,
  HedgeFundReportV19,
  RiskSnapshotV19,
} from "../types/v19";

export default function HedgeFundV19() {
  const [allocations, setAllocations] = useState<HedgeAllocationV19[]>([]);
  const [risk, setRisk] = useState<RiskSnapshotV19 | null>(null);
  const [report, setReport] = useState<HedgeFundReportV19 | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadHedgeFundV19()
      .then((data) => {
        setAllocations(data.allocations);
        setRisk(data.risk);
        setReport(data.report);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V19 HEDGE FUND EDITION</div>
          <h1>多策略基金與企業風控中心</h1>
          <p>
            Regime、Risk Parity、Kelly Cap、VaR、Expected Shortfall
            與基金級曝險管理。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <MetricCard
          label="市場 Regime"
          value={report?.market_regime ?? "尚未執行"}
          note={report?.portfolio_style ?? "—"}
        />
        <MetricCard
          label="VaR 95%"
          value={moneyV14(risk?.daily_var_95)}
          note={`VaR 99% ${moneyV14(risk?.daily_var_99)}`}
        />
        <MetricCard
          label="最大回撤"
          value={percentV14((risk?.max_drawdown ?? 0) / 100)}
          note={`Sharpe ${risk?.sharpe_20d?.toFixed(2) ?? "—"}`}
        />
        <MetricCard
          label="目標現金"
          value={`${report?.target_cash_pct?.toFixed(1) ?? "—"}%`}
          note={`Gross ${report?.recommended_gross_exposure?.toFixed(1) ?? "—"}%`}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Portfolio Manager</div>
          <h2>{report?.portfolio_manager_message ?? "尚無基金報告"}</h2>
          <p className="report-summary">
            {report?.execution_plan ?? "執行 V19 Hedge Fund Manager 後顯示。"}
          </p>
        </div>

        <div className="panel">
          <div className="panel-title">Chief Risk Officer</div>
          <h2>{risk?.risk_status ?? "尚未執行"}</h2>
          <p className="report-summary">
            {report?.chief_risk_officer_message ?? risk?.risk_message ?? "—"}
          </p>
          <div className="regime">
            <span>Gross / Net Exposure</span>
            <strong>
              {risk?.gross_exposure?.toFixed(1) ?? "—"}% /{" "}
              {risk?.net_exposure?.toFixed(1) ?? "—"}%
            </strong>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">多策略 Risk Parity 配置</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>策略</th>
                <th>權重</th>
                <th>預期報酬</th>
                <th>預期波動</th>
                <th>風險貢獻</th>
                <th>Regime</th>
              </tr>
            </thead>
            <tbody>
              {allocations.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.strategy_name}</strong></td>
                  <td>{row.strategy_weight.toFixed(1)}%</td>
                  <td>{row.expected_return.toFixed(1)}%</td>
                  <td>{row.expected_volatility.toFixed(1)}%</td>
                  <td>{row.risk_contribution.toFixed(2)}%</td>
                  <td>{row.regime}</td>
                </tr>
              ))}
              {allocations.length === 0 && (
                <tr><td colSpan={6}>尚無 V19 配置資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">風險指標</div>
        <div className="grid2">
          <div>
            <div className="regime">
              <span>Expected Shortfall 95%</span>
              <strong>{moneyV14(risk?.expected_shortfall_95)}</strong>
            </div>
            <div className="regime">
              <span>20 日年化波動</span>
              <strong>{risk?.volatility_20d?.toFixed(2) ?? "—"}%</strong>
            </div>
          </div>
          <div>
            <div className="regime">
              <span>建議 Gross Exposure</span>
              <strong>
                {report?.recommended_gross_exposure?.toFixed(1) ?? "—"}%
              </strong>
            </div>
            <div className="regime">
              <span>建議 Net Exposure</span>
              <strong>
                {report?.recommended_net_exposure?.toFixed(1) ?? "—"}%
              </strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
