export type PortfolioRecommendation30 = {
  id: number;
  recommendation_date: string;
  symbol: string;
  action: string;
  target_weight: number;
  max_weight: number;
  expected_return_score: number;
  risk_score: number;
  conviction: number;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
  suggested_holding_days?: number | null;
  rationale: string;
};

export type ResearchOutcome30 = {
  id: number;
  evaluation_date: string;
  symbol: string;
  original_rating: string;
  original_score: number;
  return_pct?: number | null;
  hit?: boolean | null;
  holding_days: number;
  outcome_status: string;
};

export type ReleaseStatus30 = {
  release_date: string;
  release_version: string;
  readiness_score: number;
  data_ready: boolean;
  research_ready: boolean;
  portfolio_ready: boolean;
  risk_ready: boolean;
  execution_ready: boolean;
  reporting_ready: boolean;
  dashboard_ready: boolean;
  live_trading_enabled: boolean;
  blockers: string[];
};
