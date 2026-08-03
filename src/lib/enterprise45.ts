import { supabase } from "./supabase";
import type {
  DecisionMemory45,
  LearningCycleStatus45,
  LearningFeedback45,
  StrategyRating45,
} from "../types/enterprise45";

export async function loadEnterprise45() {
  if (!supabase) {
    return {
      status: null as LearningCycleStatus45 | null,
      memories: [] as DecisionMemory45[],
      feedback: [] as LearningFeedback45[],
      ratings: [] as StrategyRating45[],
    };
  }

  const [statusResult, memoryResult, feedbackResult, ratingResult] =
    await Promise.all([
      supabase
        .from("learning_cycle_status_v45")
        .select("*")
        .order("status_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("decision_memory_v45")
        .select("*")
        .order("decision_date", { ascending: false })
        .limit(100),
      supabase
        .from("learning_feedback_v45")
        .select("*")
        .order("feedback_date", { ascending: false })
        .limit(100),
      supabase
        .from("strategy_rating_v45")
        .select("*")
        .order("rating_date", { ascending: false })
        .order("overall_score", { ascending: false })
        .limit(100),
    ]);

  const error =
    statusResult.error ??
    memoryResult.error ??
    feedbackResult.error ??
    ratingResult.error;
  if (error) throw error;

  const status = statusResult.data
    ? ({
        ...statusResult.data,
        decisions_captured: Number(statusResult.data.decisions_captured ?? 0),
        decisions_evaluated: Number(statusResult.data.decisions_evaluated ?? 0),
        open_decisions: Number(statusResult.data.open_decisions ?? 0),
        wins: Number(statusResult.data.wins ?? 0),
        losses: Number(statusResult.data.losses ?? 0),
        neutrals: Number(statusResult.data.neutrals ?? 0),
        feedback_records: Number(statusResult.data.feedback_records ?? 0),
        strategy_ratings: Number(statusResult.data.strategy_ratings ?? 0),
        blockers: Array.isArray(statusResult.data.blockers)
          ? statusResult.data.blockers
          : [],
      } as LearningCycleStatus45)
    : null;

  const memories = (memoryResult.data ?? []).map((row) => ({
    ...row,
    confidence: Number(row.confidence ?? 0),
    expected_return_pct:
      row.expected_return_pct == null ? null : Number(row.expected_return_pct),
    realized_return_pct:
      row.realized_return_pct == null ? null : Number(row.realized_return_pct),
    learning_score: Number(row.learning_score ?? 0),
  })) as DecisionMemory45[];

  const feedback = (feedbackResult.data ?? []).map((row) => ({
    ...row,
    expected_return_pct:
      row.expected_return_pct == null ? null : Number(row.expected_return_pct),
    actual_return_pct:
      row.actual_return_pct == null ? null : Number(row.actual_return_pct),
    prediction_error_pct:
      row.prediction_error_pct == null
        ? null
        : Number(row.prediction_error_pct),
    confidence_before: Number(row.confidence_before ?? 0),
    confidence_after: Number(row.confidence_after ?? 0),
    confidence_delta: Number(row.confidence_delta ?? 0),
  })) as LearningFeedback45[];

  const ratings = (ratingResult.data ?? []).map((row) => ({
    ...row,
    sample_count: Number(row.sample_count ?? 0),
    wins: Number(row.wins ?? 0),
    losses: Number(row.losses ?? 0),
    win_rate: Number(row.win_rate ?? 0),
    prediction_accuracy: Number(row.prediction_accuracy ?? 0),
    calibration_score: Number(row.calibration_score ?? 0),
    overall_score: Number(row.overall_score ?? 0),
  })) as StrategyRating45[];

  return { status, memories, feedback, ratings };
}
