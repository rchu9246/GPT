import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { moneyV14, percentV14 } from "../lib/v14Operations";
import {
  loadCIOReportV18,
  loadCommitteeV18,
} from "../lib/v18FundManager";
import type { CIOReportV18, CommitteeDecisionV18 } from "../types/v18";

export default function AIFundManagerV18() {
  const [committee, setCommittee] = useState<CommitteeDecisionV18[]>([]);
  const [report, setReport] = useState<CIOReportV18 | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([loadCommitteeV18(), loadCIOReportV18()])
      .then(([committeeRows, latestReport]) => {
        setCommittee(committeeRows);
        setReport(latestReport);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const buys = committee.filter((row) => row.decision === "BUY");
  const highConviction = committee.filter(
    (row) => row.conviction === "HIGH",
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V18 AI FUND MANAGER</div>
          <h1>AI 投資委員會與 CIO 日報</h1>
          <p>
            Trend、Momentum、Quality、Risk 與 Liquidity Agent
            共同決定信心、資金配置與候選委託。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <MetricCard
          label="市場狀態"
          value={report?.market_regime ?? "尚未執行"}
          note={`目標現金 ${report?.target_cash_pct?.toFixed(0) ?? "—"}%`}
        />
        <MetricCard
          label="AI 買進建議"
          value={String(buys.length)}
          note={`${highConviction.length} 筆高信心`}
        />
        <MetricCard
          label="投資組合曝險"
          value={percentV14((report?.portfolio_exposure ?? 0) / 100)}
          note={`${report?.positions_count ?? 0} 個持倉`}
        />
        <MetricCard
          label="帳戶淨值"
          value={moneyV14(report?.portfolio_equity)}
          note={`${report?.proposed_orders ?? 0} 筆待核准`}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Chief Investment Officer</div>
          <h2>{report?.chief_message ?? "尚無 CIO 日報"}</h2>
          <p className="report-summary">
            {report?.risk_message ?? "執行 V18 AI Fund Manager 後顯示風險摘要。"}
          </p>
          <div className="regime">
            <span>今日行動計畫</span>
            <strong>{report?.action_plan ?? "—"}</strong>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Agent 決策框架</div>
          <div className="execution-step"><b>T</b><span>Trend Agent：中期趨勢強度</span></div>
          <div className="execution-step"><b>M</b><span>Momentum Agent：近期動能</span></div>
          <div className="execution-step"><b>Q</b><span>Quality Agent：總分與信心品質</span></div>
          <div className="execution-step"><b>R</b><span>Risk Agent：風險調整後評分</span></div>
          <div className="execution-step"><b>L</b><span>Liquidity Agent：成交資料可用性</span></div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">AI 投資委員會排名</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>股票</th><th>Trend</th><th>Momentum</th><th>Quality</th>
                <th>Risk</th><th>委員會分數</th><th>信心</th>
                <th>目標權重</th><th>決策</th>
              </tr>
            </thead>
            <tbody>
              {committee.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.symbol}</strong> {row.name ?? ""}</td>
                  <td>{row.trend_vote.toFixed(1)}</td>
                  <td>{row.momentum_vote.toFixed(1)}</td>
                  <td>{row.quality_vote.toFixed(1)}</td>
                  <td>{row.risk_vote.toFixed(1)}</td>
                  <td>{row.committee_score.toFixed(1)}</td>
                  <td>{row.conviction}</td>
                  <td>{row.target_weight.toFixed(1)}%</td>
                  <td>{row.decision}</td>
                </tr>
              ))}
              {committee.length === 0 && (
                <tr><td colSpan={9}>尚無 AI Committee 資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">投資備忘錄</div>
        <div className="run-list">
          {committee.map((row) => (
            <div className="run-item" key={`memo-${row.id}`}>
              <span>{row.symbol} · {row.conviction} · {row.decision}</span>
              <b>{row.committee_score.toFixed(1)}</b>
              <small>{row.memo ?? "—"}</small>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
