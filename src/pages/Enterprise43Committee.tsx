import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise43 } from "../lib/enterprise43";
import type {
  CommitteeOpinion43,
  CommitteeSession43,
  CommitteeStatus43,
  ExplainableDecision43,
  InvestmentThesis43,
} from "../types/enterprise43";

export default function Enterprise43Committee() {
  const [status, setStatus] = useState<CommitteeStatus43 | null>(null);
  const [sessions, setSessions] = useState<CommitteeSession43[]>([]);
  const [opinions, setOpinions] = useState<CommitteeOpinion43[]>([]);
  const [theses, setTheses] = useState<InvestmentThesis43[]>([]);
  const [decisions, setDecisions] = useState<ExplainableDecision43[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise43()
      .then((data) => {
        setStatus(data.status);
        setSessions(data.sessions);
        setOpinions(data.opinions);
        setTheses(data.theses);
        setDecisions(data.decisions);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const session = sessions[0];
  const thesis = theses[0];
  const decision = decisions[0];

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GPT QUANT ENTERPRISE 4.3 STABLE</div>
          <h1>AI Investment Committee</h1>
          <p>
            Macro、Technical、Quant、Risk、Portfolio 與 Chairman
            多代理投票、投資論點、風險否決及可解釋決策。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="panel">
        <div className="panel-title">Committee Decision</div>
        <h1>{session?.final_action ?? "NO DATA"}</h1>
        <p>
          {session?.summary ??
            "尚未執行 Enterprise 4.3 Investment Committee"}
        </p>
      </div>

      <div className="cards">
        <MetricCard
          label="Confidence"
          value={`${session?.chairman_confidence?.toFixed(1) ?? "0"}%`}
          note={session?.chairman_decision ?? "NO DATA"}
        />
        <MetricCard
          label="Quorum"
          value={String(session?.quorum_reached ?? 0)}
          note={session?.market_regime ?? "UNKNOWN"}
        />
        <MetricCard
          label="Risk Vetoes"
          value={String(status?.risk_vetoes ?? 0)}
          note={session?.final_risk_status ?? "NO DATA"}
        />
        <MetricCard
          label="Opinions"
          value={String(status?.opinions_generated ?? opinions.length)}
          note={`${status?.votes_cast ?? 0} votes`}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Investment Thesis</div>
          <h2>{thesis?.final_recommendation ?? "NO THESIS"}</h2>
          <p>{thesis?.base_case ?? "—"}</p>
          <p><strong>Bull:</strong> {thesis?.bull_case ?? "—"}</p>
          <p><strong>Bear:</strong> {thesis?.bear_case ?? "—"}</p>
          <p>{thesis?.explanation ?? "—"}</p>
        </div>

        <div className="panel">
          <div className="panel-title">Explainable Decision</div>
          <h2>{decision?.final_action ?? "NO DECISION"}</h2>
          <p>{decision?.explanation ?? "—"}</p>
          <p>
            PAPER: {decision?.approved_for_paper ? "APPROVED" : "BLOCKED"} ·
            LIVE: {decision?.approved_for_live ? "APPROVED" : "DISABLED"}
          </p>
          {(decision?.risk_overrides ?? []).map((item) => (
            <div className="run-item" key={item}>
              <span>{item}</span><b>OVERRIDE</b>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Committee Opinions</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Recommendation</th><th>Confidence</th>
                <th>Expected Return</th><th>Downside</th>
                <th>Proposed Weight</th><th>Thesis</th>
              </tr>
            </thead>
            <tbody>
              {opinions.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.recommendation}</strong></td>
                  <td>{row.confidence.toFixed(1)}%</td>
                  <td>{row.expected_return_pct?.toFixed(2) ?? "—"}%</td>
                  <td>{row.downside_risk_pct?.toFixed(2) ?? "—"}%</td>
                  <td>{row.proposed_weight_pct?.toFixed(2) ?? "—"}%</td>
                  <td>{row.thesis_summary}</td>
                </tr>
              ))}
              {opinions.length === 0 && (
                <tr><td colSpan={6}>尚無委員會意見。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
