export type LearningStatus44 = {
  status_date: string;
  overall_status: string;
  portfolios_processed: number;
  memories_captured: number;
  replays_completed: number;
  win_patterns_found: number;
  mistake_patterns_found: number;
  calibrations_generated: number;
  evolutions_proposed: number;
  live_learning_enabled: boolean;
  live_trading_enabled: boolean;
  blockers: string[];
  summary: string;
};

export type PortfolioBrain44 = {
  snapshot_date: string;
  market_regime: string;
  brain_status: string;
  memory_records: number;
  replay_records: number;
  win_patterns: number;
  mistake_patterns: number;
  calibrated_confidence: number;
  learning_score: number;
  recommended_action: string;
  risk_override: boolean;
  summary: string;
};

export type DecisionMemory44 = {
  id: string;
  memory_date: string;
  decision_action: string;
  original_confidence: number;
  market_regime: string;
  risk_status: string;
  expected_return_pct?: number | null;
  downside_risk_pct?: number | null;
  realized_return_pct?: number | null;
  outcome_status: string;
  lesson_type?: string | null;
  lesson_summary?: string | null;
};

export type LearningPattern44 = {
  pattern_key: string;
  pattern_type: string;
  market_regime?: string | null;
  sample_count: number;
  success_rate: number;
  average_return_pct: number;
  average_drawdown_pct: number;
  confidence_score: number;
  lesson: string;
};

export type ConfidenceCalibration44 = {
  calibration_date: string;
  original_confidence: number;
  calibrated_confidence: number;
  reliability_score: number;
  sample_count: number;
  win_rate: number;
  average_error: number;
  calibration_status: string;
  rationale: string;
};

export type StrategyEvolution44 = {
  evolution_date: string;
  current_version?: string | null;
  candidate_version: string;
  current_score: number;
  candidate_score: number;
  learning_score: number;
  evolution_action: string;
  paper_approved: boolean;
  live_approved: boolean;
  rationale: string;
};
