import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise30RC } from "../lib/enterprise30rc";
import type {
  PortfolioRecommendation30,
  ReleaseStatus30,
  ResearchOutcome30,
} from "../types/enterprise30rc";

export default function Enterprise30Release() {
  const [recommendations, setRecommendations] =
    useState<PortfolioRecommendation30[]>([]);
  const [outcomes, setOutcomes] = useState<ResearchOutcome30[]>([]);
  const [release, setRelease] = useState<ReleaseStatus30 | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise30RC()
      .then((data) => {
        setRecommendations(data.recommendations);
        setOutcomes(data.outcomes);
        setRelease(data.release);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const evaluated = outcomes.filter((row) => row.outcome_status === "EVALUATED");
  const hits = evaluated.filter((row) => row.hit === true).length;
  const hitRate = evaluated.length ? (hits / evaluated.length) * 100 : 0;

  const allocation = useMemo(
    () =>
      recommendations
        .filter((row) => row.action === "BUY")
        .reduce((sum, row) => sum + row.target_weight, 0),
    [recommendations],
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">ENTERPRISE 3.0 RELEASE CANDIDATE</div>
          <h1>Daily Investment Command Center</h1>
          <p>
            統一研究、可解釋決策、建議權重、研究成效、風險治理與
            正式版就緒狀態。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="release30-hero panel">
        <div>
          <div className="panel-title">Release Readiness</div>
          <div className="release30-score">
            {release?.readiness_score?.toFixed(0) ?? "0"}%
          </div>
          <p className="report-summary">
            {release?.blockers?.length
              ? `Blockers: ${release.blockers.join(", ")}`
              : "所有核心 PAPER 模組已就緒。"}
          </p>
        </div>
        <div className="release30-badge">
          <span>{release?.release_version ?? "3.0.0-rc.1"}</span>
          <strong>
            {release?.live_trading_enabled ? "LIVE" : "PAPER ONLY"}
          </strong>
        </div>
      </div>

      <div className="cards">
        <MetricCard
          label="建議部署權重"
          value={`${allocation.toFixed(1)}%`}
          note={`${recommendations.filter((r) => r.action === "BUY").length} BUY`}
        />
        <MetricCard
          label="研究命中率"
          value={`${hitRate.toFixed(1)}%`}
          note={`${evaluated.length} 筆已評估`}
        />
        <MetricCard
          label="平均信心"
          value={`${
            recommendations.length
              ? (
                  recommendations.reduce((s, r) => s + r.conviction, 0) /
                  recommendations.length
                ).toFixed(1)
              : "0"
          }`}
          note="Portfolio Conviction"
        />
        <MetricCard
          label="最高風險"
          value={`${
            recommendations.length
              ? Math.max(...recommendations.map((r) => r.risk_score)).toFixed(0)
              : "0"
          }`}
          note="0–100"
        />
      </div>

      <div className="panel">
        <div className="panel-title">Portfolio Recommendations</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th><th>股票</th><th>動作</th><th>目標權重</th>
                <th>研究分數</th><th>風險</th><th>信心</th>
                <th>停損</th><th>停利</th><th>持有天數</th>
              </tr>
            </thead>
            <tbody>
              {recommendations.map((row) => (
                <tr key={row.id}>
                  <td>{row.recommendation_date}</td>
                  <td><strong>{row.symbol}</strong></td>
                  <td>{row.action}</td>
                  <td>{row.target_weight.toFixed(1)}%</td>
                  <td>{row.expected_return_score.toFixed(1)}</td>
                  <td>{row.risk_score.toFixed(1)}</td>
                  <td>{row.conviction.toFixed(1)}</td>
                  <td>{row.stop_loss_pct?.toFixed(1) ?? "—"}%</td>
                  <td>{row.take_profit_pct?.toFixed(1) ?? "—"}%</td>
                  <td>{row.suggested_holding_days ?? "—"}</td>
                </tr>
              ))}
              {recommendations.length === 0 && (
                <tr><td colSpan={10}>尚無投資組合建議。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Research Outcome Tracking</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>評估日</th><th>股票</th><th>原評級</th>
                <th>原分數</th><th>報酬</th><th>命中</th><th>持有天數</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.slice(0, 50).map((row) => (
                <tr key={row.id}>
                  <td>{row.evaluation_date}</td>
                  <td><strong>{row.symbol}</strong></td>
                  <td>{row.original_rating}</td>
                  <td>{row.original_score.toFixed(1)}</td>
                  <td>{row.return_pct?.toFixed(2) ?? "—"}%</td>
                  <td>{row.hit == null ? "—" : row.hit ? "YES" : "NO"}</td>
                  <td>{row.holding_days}</td>
                </tr>
              ))}
              {outcomes.length === 0 && (
                <tr><td colSpan={7}>尚無研究成效資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
