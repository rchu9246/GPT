import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadCouncilV21 } from "../lib/v21Council";
import type {
  AgentOpinionV21,
  CouncilDecisionV21,
  CouncilReportV21,
} from "../types/v21";

export default function MultiAgentCouncilV21() {
  const [decisions, setDecisions] = useState<CouncilDecisionV21[]>([]);
  const [opinions, setOpinions] = useState<AgentOpinionV21[]>([]);
  const [report, setReport] = useState<CouncilReportV21 | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadCouncilV21()
      .then((data) => {
        setDecisions(data.decisions);
        setOpinions(data.opinions);
        setReport(data.report);
        setSelected(data.decisions[0]?.symbol ?? null);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const selectedOpinions = useMemo(
    () => opinions.filter((row) => row.symbol === selected),
    [opinions, selected],
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V21 MULTI-AGENT INVESTMENT COUNCIL</div>
          <h1>多代理投資委員會</h1>
          <p>
            技術、動能、品質、流動性與風險 Agent 獨立投票，
            CIO 依共識、分歧與否決權形成最終決策。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <MetricCard
          label="市場姿態"
          value={report?.market_posture ?? "尚未執行"}
          note={`${report?.symbols_reviewed ?? 0} 檔受審`}
        />
        <MetricCard
          label="平均共識"
          value={`${report?.average_consensus?.toFixed(1) ?? "0"}`}
          note="0–100"
        />
        <MetricCard
          label="BUY 決策"
          value={String(report?.buy_decisions ?? 0)}
          note={`${report?.vetoed_decisions ?? 0} 筆遭否決`}
        />
        <MetricCard
          label="HOLD / WATCH"
          value={String(
            (report?.hold_decisions ?? 0) + (report?.avoid_decisions ?? 0),
          )}
          note="人工審核仍保留"
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Chief Investment Officer</div>
          <h2>
            {report?.chief_investment_officer_message ?? "尚無委員會報告"}
          </h2>
          <p className="report-summary">
            {report?.execution_guidance ??
              "執行 V21 Multi-Agent Investment Council 後顯示。"}
          </p>
        </div>

        <div className="panel">
          <div className="panel-title">Dissent Monitor</div>
          <p className="report-summary">
            {report?.dissent_summary ?? "尚無分歧資料。"}
          </p>
          <div className="execution-step">
            <b>V</b><span>Risk / Liquidity Agent 可直接否決</span>
          </div>
          <div className="execution-step">
            <b>C</b><span>共識與同意比例必須同時通過</span>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">委員會最終決策</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>股票</th><th>共識</th><th>同意率</th><th>分歧</th>
                <th>多 / 中 / 空</th><th>否決</th><th>信心</th>
                <th>目標權重</th><th>最終決策</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => setSelected(row.symbol)}
                  className={selected === row.symbol ? "selected-row" : ""}
                >
                  <td><strong>{row.symbol}</strong> {row.name ?? ""}</td>
                  <td>{row.consensus_score.toFixed(1)}</td>
                  <td>{row.agreement_pct.toFixed(1)}%</td>
                  <td>{row.dispersion.toFixed(1)}</td>
                  <td>
                    {row.bullish_votes} / {row.neutral_votes} / {row.bearish_votes}
                  </td>
                  <td>{row.veto_count}</td>
                  <td>{row.conviction}</td>
                  <td>{row.target_weight.toFixed(1)}%</td>
                  <td>{row.final_decision}</td>
                </tr>
              ))}
              {decisions.length === 0 && (
                <tr><td colSpan={9}>尚無 V21 委員會資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">
            Agent 意見 {selected ? `· ${selected}` : ""}
          </div>
          <div className="run-list">
            {selectedOpinions.map((row) => (
              <div className="run-item" key={row.id}>
                <span>
                  {row.agent_role} · {row.vote}
                  {row.veto ? " · VETO" : ""}
                </span>
                <b>{row.score.toFixed(1)}</b>
                <small>
                  信心 {row.confidence.toFixed(1)} · {row.rationale}
                </small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">CIO Memo</div>
          <div className="run-list">
            {decisions.slice(0, 12).map((row) => (
              <div className="run-item" key={`memo-${row.id}`}>
                <span>
                  {row.symbol} · {row.final_decision} · {row.conviction}
                </span>
                <b>{row.consensus_score.toFixed(1)}</b>
                <small>{row.cio_memo}</small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
