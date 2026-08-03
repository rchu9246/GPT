import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise44 } from "../lib/enterprise44";
import type {
  ConfidenceCalibration44,
  DecisionMemory44,
  LearningPattern44,
  LearningStatus44,
  PortfolioBrain44,
  StrategyEvolution44,
} from "../types/enterprise44";

export default function Enterprise44PortfolioBrain() {
  const [status, setStatus] = useState<LearningStatus44 | null>(null);
  const [brains, setBrains] = useState<PortfolioBrain44[]>([]);
  const [memories, setMemories] = useState<DecisionMemory44[]>([]);
  const [patterns, setPatterns] = useState<LearningPattern44[]>([]);
  const [calibrations, setCalibrations] = useState<ConfidenceCalibration44[]>([]);
  const [evolutions, setEvolutions] = useState<StrategyEvolution44[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise44()
      .then((data) => {
        setStatus(data.status);
        setBrains(data.brains);
        setMemories(data.memories);
        setPatterns(data.patterns);
        setCalibrations(data.calibrations);
        setEvolutions(data.evolutions);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const brain = brains[0];
  const calibration = calibrations[0];

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GPT QUANT ENTERPRISE 4.4 STABLE</div>
          <h1>Portfolio Brain & Self-Learning Engine</h1>
          <p>
            決策記憶、Trade Replay、勝負模式學習、信心校準、
            策略演化提案與知識回饋。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="panel">
        <div className="panel-title">Portfolio Brain</div>
        <h1>{brain?.recommended_action ?? "NO DATA"}</h1>
        <p>
          {brain?.summary ??
            "尚未執行 Enterprise 4.4 Portfolio Brain"}
        </p>
      </div>

      <div className="cards">
        <MetricCard
          label="Learning Score"
          value={brain?.learning_score?.toFixed(1) ?? "0"}
          note={brain?.brain_status ?? "NO DATA"}
        />
        <MetricCard
          label="Calibrated Confidence"
          value={`${brain?.calibrated_confidence?.toFixed(1) ?? "0"}%`}
          note={`Original ${calibration?.original_confidence?.toFixed(1) ?? "0"}%`}
        />
        <MetricCard
          label="Patterns"
          value={`${status?.win_patterns_found ?? 0} / ${
            status?.mistake_patterns_found ?? 0
          }`}
          note="Win / Mistake"
        />
        <MetricCard
          label="Evolution Proposals"
          value={String(status?.evolutions_proposed ?? 0)}
          note="PAPER candidates only"
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Decision Memory</div>
          <div className="run-list">
            {memories.map((row) => (
              <div className="run-item" key={row.id}>
                <span>{row.decision_action} · {row.market_regime}</span>
                <b>{row.outcome_status}</b>
                <small>
                  Confidence {row.original_confidence.toFixed(1)}% ·
                  Return {row.realized_return_pct?.toFixed(2) ?? "—"}% ·
                  {row.lesson_summary ?? "Awaiting lesson"}
                </small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Learning Patterns</div>
          <div className="run-list">
            {patterns.map((row) => (
              <div className="run-item" key={row.pattern_key}>
                <span>{row.pattern_key}</span>
                <b>{row.pattern_type}</b>
                <small>
                  Success {row.success_rate.toFixed(1)}% · Confidence{" "}
                  {row.confidence_score.toFixed(1)} · {row.lesson}
                </small>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Strategy Evolution Proposals</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Candidate</th><th>Action</th><th>Current</th>
                <th>Candidate Score</th><th>Learning</th>
                <th>PAPER</th><th>LIVE</th><th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {evolutions.map((row) => (
                <tr key={row.candidate_version}>
                  <td><strong>{row.candidate_version}</strong></td>
                  <td>{row.evolution_action}</td>
                  <td>{row.current_score.toFixed(1)}</td>
                  <td>{row.candidate_score.toFixed(1)}</td>
                  <td>{row.learning_score.toFixed(1)}</td>
                  <td>{row.paper_approved ? "APPROVED" : "NO"}</td>
                  <td>{row.live_approved ? "APPROVED" : "DISABLED"}</td>
                  <td>{row.rationale}</td>
                </tr>
              ))}
              {evolutions.length === 0 && (
                <tr><td colSpan={8}>尚無策略演化提案。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
