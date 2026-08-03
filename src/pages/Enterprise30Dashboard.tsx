import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { moneyV14, percentV14 } from "../lib/v14Operations";
import { loadEnterprise30 } from "../lib/enterprise30";
import type {
  CeoSnapshot30,
  ResearchReport30,
  StrategyMarket30,
} from "../types/enterprise30";

export default function Enterprise30Dashboard() {
  const [snapshot, setSnapshot] = useState<CeoSnapshot30 | null>(null);
  const [research, setResearch] = useState<ResearchReport30[]>([]);
  const [strategies, setStrategies] = useState<StrategyMarket30[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise30()
      .then((data) => {
        setSnapshot(data.snapshot);
        setResearch(data.research);
        setStrategies(data.strategies);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GPT QUANT ENTERPRISE 3.0 ALPHA 1</div>
          <h1>AI Investment Operating System</h1>
          <p>
            Research Intelligence、策略市集、最高決策、營運狀態與
            投資組合資訊整合在單一 CEO 工作台。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="enterprise30-hero panel">
        <div>
          <div className="panel-title">Executive Command</div>
          <div className="enterprise30-action">
            {snapshot?.director_action ?? "尚未執行"}
          </div>
          <p className="report-summary">
            Market {snapshot?.market_posture ?? "—"} · Platform{" "}
            {snapshot?.platform_status ?? "—"}
          </p>
        </div>
        <div className="enterprise30-confidence">
          <span>Research Confidence</span>
          <strong>{snapshot?.research_confidence?.toFixed(0) ?? "0"}</strong>
          <small>/100</small>
        </div>
      </div>

      <div className="cards">
        <MetricCard
          label="帳戶淨值"
          value={moneyV14(snapshot?.equity)}
          note={`Cash ${moneyV14(snapshot?.cash)}`}
        />
        <MetricCard
          label="總報酬"
          value={percentV14(snapshot?.total_return)}
          note={`MDD ${snapshot?.max_drawdown?.toFixed(2) ?? "—"}%`}
        />
        <MetricCard
          label="平台健康度"
          value={`${snapshot?.system_health?.toFixed(0) ?? "0"}/100`}
          note={`Operational ${snapshot?.operational_score?.toFixed(0) ?? "0"}`}
        />
        <MetricCard
          label="風險與委託"
          value={`${snapshot?.risk_events ?? 0} / ${
            snapshot?.proposed_orders ?? 0
          }`}
          note="Open Risk / Proposed"
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Top Research Ideas</div>
          <div className="run-list">
            {research.slice(0, 8).map((row) => (
              <div className="run-item" key={row.id}>
                <span>
                  {row.symbol} · {row.rating} · Risk {row.risk_view}
                </span>
                <b>{row.research_score.toFixed(1)}</b>
                <small>
                  信心 {row.confidence.toFixed(1)} · {row.thesis}
                </small>
              </div>
            ))}
            {research.length === 0 && (
              <div className="run-item">
                <span>Research Center</span><b>NO DATA</b>
                <small>執行 Enterprise 3.0 Alpha 1 Research Cycle。</small>
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Strategy Marketplace</div>
          <div className="run-list">
            {strategies.slice(0, 8).map((row) => (
              <div className="run-item" key={row.id}>
                <span>
                  {row.strategy_name} · {row.lifecycle_status}
                </span>
                <b>{row.quality_score.toFixed(1)}</b>
                <small>
                  {row.signal_count} signals · {row.validation_status}
                </small>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Research Reports</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th><th>股票</th><th>評級</th><th>研究分數</th>
                <th>信心</th><th>趨勢</th><th>動能</th><th>風險</th>
              </tr>
            </thead>
            <tbody>
              {research.map((row) => (
                <tr key={row.id}>
                  <td>{row.report_date}</td>
                  <td><strong>{row.symbol}</strong></td>
                  <td>{row.rating}</td>
                  <td>{row.research_score.toFixed(1)}</td>
                  <td>{row.confidence.toFixed(1)}</td>
                  <td>{row.trend_view}</td>
                  <td>{row.momentum_view}</td>
                  <td>{row.risk_view}</td>
                </tr>
              ))}
              {research.length === 0 && (
                <tr><td colSpan={8}>尚無 Enterprise 3.0 研究報告。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
