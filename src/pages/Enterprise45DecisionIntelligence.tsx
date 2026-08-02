import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise45 } from "../lib/enterprise45";
import type {
  DecisionMemory45,
  LearningCycleStatus45,
  LearningFeedback45,
  StrategyRating45,
} from "../types/enterprise45";

export default function Enterprise45DecisionIntelligence() {
  const [status, setStatus] = useState<LearningCycleStatus45 | null>(null);
  const [memories, setMemories] = useState<DecisionMemory45[]>([]);
  const [feedback, setFeedback] = useState<LearningFeedback45[]>([]);
  const [ratings, setRatings] = useState<StrategyRating45[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise45()
      .then((data) => {
        setStatus(data.status);
        setMemories(data.memories);
        setFeedback(data.feedback);
        setRatings(data.ratings);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const latestMemory = memories[0];
  const topRating = ratings[0];
  const evaluated = (status?.wins ?? 0) + (status?.losses ?? 0) + (status?.neutrals ?? 0);
  const winRate = evaluated ? ((status?.wins ?? 0) / evaluated) * 100 : 0;

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GPT QUANT ENTERPRISE 4.5 FOUNDATION</div>
          <h1>Decision Intelligence & Learning Engine</h1>
          <p>
            將委員會決策、信心、預期報酬、實際結果、學習回饋與策略評分串成可追蹤的決策記憶。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="panel">
        <div className="panel-title">Learning Cycle</div>
        <h1>{status?.overall_status ?? "NO DATA"}</h1>
        <p>{status?.summary ?? "尚未執行 Enterprise 4.5 Learning Cycle"}</p>
      </div>

      <div className="cards">
        <MetricCard
          label="Open Decisions"
          value={String(status?.open_decisions ?? 0)}
          note={latestMemory?.recommendation ?? "NO DATA"}
        />
        <MetricCard
          label="Evaluated"
          value={String(status?.decisions_evaluated ?? 0)}
          note={`${status?.feedback_records ?? 0} feedback`}
        />
        <MetricCard
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          note={`${status?.wins ?? 0}W / ${status?.losses ?? 0}L`}
        />
        <MetricCard
          label="Top Strategy"
          value={topRating?.strategy_key ?? "NO DATA"}
          note={`${topRating?.overall_score?.toFixed(1) ?? "0"} score`}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Decision Memory</div>
          <div className="run-list">
            {memories.map((row) => (
              <div className="run-item" key={row.id}>
                <span>
                  {row.decision_date} · {row.recommendation} · {row.market_regime}
                </span>
                <b>{row.outcome_status}</b>
                <small>
                  Confidence {row.confidence.toFixed(1)}% · Expected{" "}
                  {row.expected_return_pct?.toFixed(2) ?? "—"}% · Actual{" "}
                  {row.realized_return_pct?.toFixed(2) ?? "OPEN"}% ·{" "}
                  {row.lesson_summary ?? "Awaiting evaluation"}
                </small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Learning Feedback</div>
          <div className="run-list">
            {feedback.map((row) => (
              <div className="run-item" key={row.id}>
                <span>{row.feedback_date} · {row.prediction}</span>
                <b>{row.outcome_status}</b>
                <small>
                  Confidence {row.confidence_before.toFixed(1)}% →{" "}
                  {row.confidence_after.toFixed(1)}% · {row.lesson}
                </small>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Strategy Ratings</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Strategy</th><th>Status</th><th>Score</th>
                <th>Samples</th><th>Win Rate</th>
                <th>Accuracy</th><th>Calibration</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {ratings.map((row) => (
                <tr key={row.strategy_key}>
                  <td><strong>{row.strategy_key}</strong></td>
                  <td>{row.rating_status}</td>
                  <td>{row.overall_score.toFixed(1)}</td>
                  <td>{row.sample_count}</td>
                  <td>{row.win_rate.toFixed(1)}%</td>
                  <td>{row.prediction_accuracy.toFixed(1)}%</td>
                  <td>{row.calibration_score.toFixed(1)}%</td>
                  <td>{row.recommended_action}</td>
                </tr>
              ))}
              {ratings.length === 0 && (
                <tr><td colSpan={8}>尚無策略評分資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
