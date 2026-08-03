export type EnterpriseHealth = {
  health_date: string;
  overall_score: number;
  data_score: number;
  signal_score: number;
  execution_score: number;
  portfolio_score: number;
  risk_score: number;
  automation_score: number;
  status: string;
  issues: string[];
};

export type EnterpriseDecision = {
  id: number;
  decision_date: string;
  decision_scope: string;
  entity_type: string;
  entity_key: string;
  module_key: string;
  engine_version: string;
  action: string;
  score?: number | null;
  confidence?: number | null;
  risk_score?: number | null;
  target_weight?: number | null;
  target_cash_pct?: number | null;
  rationale: string;
  status: string;
};

export type EnterpriseRun = {
  id: string;
  run_date: string;
  run_type: string;
  status: string;
  started_at: string;
  completed_at?: string | null;
  module_count: number;
  success_count: number;
  failure_count: number;
  summary: Record<string, unknown>;
};

export type EnterprisePortfolio = {
  snapshot_date: string;
  equity: number;
  cash: number;
  market_value: number;
  gross_exposure_pct: number;
  net_exposure_pct: number;
  unrealized_pnl: number;
  total_return: number;
  max_drawdown: number;
  var_95: number;
  sharpe: number;
  positions_count: number;
};
