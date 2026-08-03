export type LearningCycleStatus45 = {
  status_date: string;
  overall_status: string;
  decisions_captured: number;
  decisions_evaluated: number;
  open_decisions: number;
  wins: number;
  losses: number;
  neutrals: number;
  feedback_records: number;
  strategy_ratings: number;
  live_learning_enabled: boolean;
  live_trading_enabled: boolean;
  blockers: string[];
  summary: string;
};

export type DecisionMemory45 = {
  id: string;
  decision_date: string;
  recommendation: string;
  confidence: number;
  market_regime: string;
  risk_status: string;
  expected_return_pct?: number | null;
  realized_return_pct?: number | null;
  outcome_status: string;
  learning_score: number;
  lesson_summary?: string | null;
};

export type LearningFeedback45 = {
  id: string;
  feedback_date: string;
  prediction: string;
  expected_return_pct?: number | null;
  actual_return_pct?: number | null;
  prediction_error_pct?: number | null;
  outcome_status: string;
  confidence_before: number;
  confidence_after: number;
  confidence_delta: number;
  lesson: string;
};

export type StrategyRating45 = {
  strategy_key: string;
  sample_count: number;
  wins: number;
  losses: number;
  win_rate: number;
  prediction_accuracy: number;
  calibration_score: number;
  overall_score: number;
  rating_status: string;
  recommended_action: string;
};
