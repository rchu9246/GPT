import { supabase } from "./supabase";
import type {
  ConfidenceCalibration44,
  DecisionMemory44,
  LearningPattern44,
  LearningStatus44,
  PortfolioBrain44,
  StrategyEvolution44,
} from "../types/enterprise44";

export async function loadEnterprise44() {
  if (!supabase) {
    return {
      status: null as LearningStatus44 | null,
      brains: [] as PortfolioBrain44[],
      memories: [] as DecisionMemory44[],
      patterns: [] as LearningPattern44[],
      calibrations: [] as ConfidenceCalibration44[],
      evolutions: [] as StrategyEvolution44[],
    };
  }

  const [statusResult, brainResult, memoryResult, patternResult, calibrationResult, evolutionResult] =
    await Promise.all([
      supabase
        .from("self_learning_status_v44")
        .select("*")
        .order("status_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("portfolio_brain_snapshots_v44")
        .select("*")
        .order("snapshot_date", { ascending: false })
        .limit(20),
      supabase
        .from("decision_memory_v44")
        .select("*")
        .order("memory_date", { ascending: false })
        .limit(100),
      supabase
        .from("learning_patterns_v44")
        .select("*")
        .order("pattern_date", { ascending: false })
        .order("confidence_score", { ascending: false })
        .limit(100),
      supabase
        .from("confidence_calibration_v44")
        .select("*")
        .order("calibration_date", { ascending: false })
        .limit(50),
      supabase
        .from("strategy_evolution_v44")
        .select("*")
        .order("evolution_date", { ascending: false })
        .limit(50),
    ]);

  const error =
    statusResult.error ??
    brainResult.error ??
    memoryResult.error ??
    patternResult.error ??
    calibrationResult.error ??
    evolutionResult.error;
  if (error) throw error;

  const status = statusResult.data
    ? ({
        ...statusResult.data,
        portfolios_processed: Number(statusResult.data.portfolios_processed ?? 0),
        memories_captured: Number(statusResult.data.memories_captured ?? 0),
        replays_completed: Number(statusResult.data.replays_completed ?? 0),
        win_patterns_found: Number(statusResult.data.win_patterns_found ?? 0),
        mistake_patterns_found: Number(statusResult.data.mistake_patterns_found ?? 0),
        calibrations_generated: Number(statusResult.data.calibrations_generated ?? 0),
        evolutions_proposed: Number(statusResult.data.evolutions_proposed ?? 0),
        blockers: Array.isArray(statusResult.data.blockers)
          ? statusResult.data.blockers
          : [],
      } as LearningStatus44)
    : null;

  const brains = (brainResult.data ?? []).map((row) => ({
    ...row,
    memory_records: Number(row.memory_records ?? 0),
    replay_records: Number(row.replay_records ?? 0),
    win_patterns: Number(row.win_patterns ?? 0),
    mistake_patterns: Number(row.mistake_patterns ?? 0),
    calibrated_confidence: Number(row.calibrated_confidence ?? 0),
    learning_score: Number(row.learning_score ?? 0),
  })) as PortfolioBrain44[];

  const memories = (memoryResult.data ?? []).map((row) => ({
    ...row,
    original_confidence: Number(row.original_confidence ?? 0),
    expected_return_pct:
      row.expected_return_pct == null ? null : Number(row.expected_return_pct),
    downside_risk_pct:
      row.downside_risk_pct == null ? null : Number(row.downside_risk_pct),
    realized_return_pct:
      row.realized_return_pct == null ? null : Number(row.realized_return_pct),
  })) as DecisionMemory44[];

  const patterns = (patternResult.data ?? []).map((row) => ({
    ...row,
    sample_count: Number(row.sample_count ?? 0),
    success_rate: Number(row.success_rate ?? 0),
    average_return_pct: Number(row.average_return_pct ?? 0),
    average_drawdown_pct: Number(row.average_drawdown_pct ?? 0),
    confidence_score: Number(row.confidence_score ?? 0),
  })) as LearningPattern44[];

  const calibrations = (calibrationResult.data ?? []).map((row) => ({
    ...row,
    original_confidence: Number(row.original_confidence ?? 0),
    calibrated_confidence: Number(row.calibrated_confidence ?? 0),
    reliability_score: Number(row.reliability_score ?? 0),
    sample_count: Number(row.sample_count ?? 0),
    win_rate: Number(row.win_rate ?? 0),
    average_error: Number(row.average_error ?? 0),
  })) as ConfidenceCalibration44[];

  const evolutions = (evolutionResult.data ?? []).map((row) => ({
    ...row,
    current_score: Number(row.current_score ?? 0),
    candidate_score: Number(row.candidate_score ?? 0),
    learning_score: Number(row.learning_score ?? 0),
  })) as StrategyEvolution44[];

  return { status, brains, memories, patterns, calibrations, evolutions };
}
