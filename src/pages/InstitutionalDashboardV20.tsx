import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadInstitutionalV20 } from "../lib/v20Institutional";
import type {
  AttributionV20,
  InstitutionalReportV20,
} from "../types/v20";

function statusClass(status?: string): string {
  if (status === "PASS") return "positive";
  if (status === "FAIL" || status === "REDUCE_RISK") return "negative";
  return "";
}

export default function InstitutionalDashboardV20() {
  const [report, setReport] = useState<InstitutionalReportV20 | null>(null);
  const [attribution, setAttribution] = useState<AttributionV20[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadInstitutionalV20()
      .then((data) => {
        setReport(data.report);
        setAttribution(data.attribution);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V20 INSTITUTIONAL EDITION</div>
          <h1>機構級投資決策總控中心</h1>
          <p>
            將資料、訊號、委託、投資組合、AI 委員會、避險配置、
            風險與績效歸因整合在同一個日常工作台。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <MetricCard
          label="系統健康度"
          value={`${report?.system_health?.toFixed(0) ?? "0"}/100`}
          note={report?.headline ?? "尚未執行 V20"}
        />
        <MetricCard
          label="資料與訊號"
          value={`${report?.data_status ?? "—"} / ${report?.signal_status ?? "—"}`}
          note="Data / Signal"
        />
        <MetricCard
          label="交易與投組"
          value={`${report?.execution_status ?? "—"} / ${report?.portfolio_status ?? "—"}`}
          note="Execution / Portfolio"
        />
        <MetricCard
          label="風險與策略"
          value={`${report?.risk_status ?? "—"} / ${report?.strategy_status ?? "—"}`}
          note="Risk / Strategy"
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Executive Summary</div>
          <h2>{report?.headline ?? "尚無機構報告"}</h2>
          <p className="report-summary">
            {report?.executive_summary ??
              "執行 V20 Institutional Daily Cycle 後顯示整體摘要。"}
          </p>
        </div>

        <div className="panel">
          <div className="panel-title">Today Action Items</div>
          <p className="report-summary">
            {report?.action_items ?? "尚無行動項目。"}
          </p>
          <div className="institutional-status-grid">
            {[
              ["Data", report?.data_status],
              ["Signal", report?.signal_status],
              ["Execution", report?.execution_status],
              ["Portfolio", report?.portfolio_status],
              ["Risk", report?.risk_status],
              ["Strategy", report?.strategy_status],
            ].map(([label, value]) => (
              <div className="regime" key={label}>
                <span>{label}</span>
                <strong className={statusClass(value)}>{value ?? "—"}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">績效歸因</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>來源</th>
                <th>績效貢獻</th>
                <th>曝險</th>
                <th>說明</th>
              </tr>
            </thead>
            <tbody>
              {attribution.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.component}</strong></td>
                  <td className={row.contribution >= 0 ? "positive" : "negative"}>
                    {row.contribution.toFixed(2)}%
                  </td>
                  <td>{row.exposure.toFixed(2)}%</td>
                  <td>{row.detail ?? "—"}</td>
                </tr>
              ))}
              {attribution.length === 0 && (
                <tr><td colSpan={4}>尚無 V20 績效歸因資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">每日機構工作流程</div>
        <div className="execution-step"><b>1</b><span>V16 Explainable Order Engine</span></div>
        <div className="execution-step"><b>2</b><span>V17 Portfolio OS</span></div>
        <div className="execution-step"><b>3</b><span>V18 AI Fund Manager</span></div>
        <div className="execution-step"><b>4</b><span>V19 Hedge Fund & Risk Manager</span></div>
        <div className="execution-step"><b>5</b><span>V20 Institutional Report & Attribution</span></div>
      </div>
    </section>
  );
}
