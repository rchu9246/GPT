import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise21 } from "../lib/enterprise21";
import type {
  DailyBrief21,
  OperationalStatus21,
  RiskEvent21,
} from "../types/enterprise21";

export default function Enterprise21Operational() {
  const [operational, setOperational] =
    useState<OperationalStatus21 | null>(null);
  const [events, setEvents] = useState<RiskEvent21[]>([]);
  const [brief, setBrief] = useState<DailyBrief21 | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise21()
      .then((data) => {
        setOperational(data.operational);
        setEvents(data.events);
        setBrief(data.brief);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">ENTERPRISE 2.1 OPERATIONAL PLATFORM</div>
          <h1>每日營運、集中風控與管理簡報</h1>
          <p>
            將資料新鮮度、訊號、委託、投組、風險、報告與問題清單
            集中到同一個作業畫面。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="enterprise21-hero panel">
        <div>
          <div className="panel-title">Operational Status</div>
          <div className="enterprise21-status">
            {operational?.pipeline_status ?? "尚未執行"}
          </div>
          <p className="report-summary">
            {brief?.summary ??
              "執行 Enterprise 2.1 Operational Daily Cycle 後顯示。"}
          </p>
        </div>
        <div className="enterprise21-score">
          <span>Operational Score</span>
          <strong>{operational?.overall_score?.toFixed(0) ?? "0"}</strong>
          <small>/100</small>
        </div>
      </div>

      <div className="cards">
        <MetricCard
          label="資料 / 訊號"
          value={`${operational?.data_freshness_status ?? "—"} / ${
            operational?.signals_status ?? "—"
          }`}
          note={`${operational?.latest_data_date ?? "—"} · ${
            operational?.latest_signal_date ?? "—"
          }`}
        />
        <MetricCard
          label="委託"
          value={`${operational?.proposed_orders ?? 0} / ${
            operational?.approved_orders ?? 0
          } / ${operational?.filled_orders ?? 0}`}
          note="Proposed / Approved / Filled"
        />
        <MetricCard
          label="持倉"
          value={String(operational?.open_positions ?? 0)}
          note={operational?.portfolio_status ?? "—"}
        />
        <MetricCard
          label="集中風控"
          value={operational?.risk_status ?? "—"}
          note={`${events.length} 筆事件`}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">CEO Daily Brief</div>
          <h2>{brief?.headline ?? "尚無管理簡報"}</h2>
          <p className="report-summary">{brief?.market_view ?? "—"}</p>
          <p className="report-summary">{brief?.portfolio_view ?? "—"}</p>
          <p className="report-summary">{brief?.risk_view ?? "—"}</p>
        </div>

        <div className="panel">
          <div className="panel-title">Action Plan</div>
          <h2>{brief?.action_plan ?? "尚無行動項目"}</h2>
          <div className="run-list">
            {(operational?.issues ?? []).map((issue) => (
              <div className="run-item" key={issue}>
                <span>Operational Issue</span>
                <b>REVIEW</b>
                <small>{issue}</small>
              </div>
            ))}
            {(operational?.issues ?? []).length === 0 && (
              <div className="run-item">
                <span>Platform</span><b>HEALTHY</b>
                <small>目前沒有未處理的營運問題。</small>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Centralized Risk Events</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th><th>嚴重度</th><th>事件</th>
                <th>數值</th><th>限制</th><th>狀態</th><th>訊息</th>
              </tr>
            </thead>
            <tbody>
              {events.map((row) => (
                <tr key={row.id}>
                  <td>{row.event_date}</td>
                  <td><strong>{row.severity}</strong></td>
                  <td>{row.event_type}</td>
                  <td>{row.metric_value?.toFixed(2) ?? "—"}</td>
                  <td>{row.limit_value?.toFixed(2) ?? "—"}</td>
                  <td>{row.status}</td>
                  <td>{row.message}</td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr><td colSpan={7}>目前沒有集中風控事件。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
