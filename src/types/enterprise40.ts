export type Portfolio40 = {
  id: string;
  portfolio_key: string;
  portfolio_name: string;
  account_name: string;
  portfolio_type: string;
  lifecycle_status: string;
  starting_cash: number;
  reserve_cash_pct: number;
  max_positions: number;
  max_position_pct: number;
};

export type Strategy40 = {
  id: string;
  strategy_key: string;
  strategy_name: string;
  strategy_family: string;
  lifecycle_status: string;
  enabled: boolean;
  paper_approved: boolean;
  live_approved: boolean;
};

export type Regime40 = {
  regime_date: string;
  market_key: string;
  regime: string;
  confidence: number;
  rationale: string;
};

export type Run40 = {
  id: string;
  run_date: string;
  run_type: string;
  release_version: string;
  status: string;
  current_stage?: string | null;
  started_at: string;
  completed_at?: string | null;
  blockers: string[];
};

export type Release40 = {
  release_date: string;
  release_version: string;
  readiness_score: number;
  foundation_ready: boolean;
  registry_ready: boolean;
  run_tracking_ready: boolean;
  audit_ready: boolean;
  regime_ready: boolean;
  compatibility_ready: boolean;
  live_trading_enabled: boolean;
  blockers: string[];
};
