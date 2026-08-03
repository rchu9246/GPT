export type ResearchReport30 = {
  id: number;
  report_date: string;
  symbol: string;
  rating: string;
  research_score: number;
  confidence: number;
  trend_view: string;
  momentum_view: string;
  risk_view: string;
  catalyst_view: string;
  thesis: string;
  invalidation_conditions: string;
};

export type StrategyMarket30 = {
  id: number;
  strategy_key: string;
  strategy_version: string;
  strategy_name: string;
  strategy_type: string;
  lifecycle_status: string;
  enabled: boolean;
  signal_count: number;
  latest_signal_date?: string | null;
  quality_score: number;
  validation_status: string;
  cagr?: number | null;
  sharpe?: number | null;
  max_drawdown?: number | null;
  win_rate?: number | null;
};

export type CeoSnapshot30 = {
  snapshot_date: string;
  platform_status: string;
  market_posture: string;
  director_action: string;
  research_confidence: number;
  system_health: number;
  operational_score: number;
  equity: number;
  cash: number;
  total_return: number;
  max_drawdown: number;
  risk_events: number;
  proposed_orders: number;
  approved_orders: number;
  filled_orders: number;
  top_ideas: Array<Record<string, unknown>>;
  latest_actions: Array<Record<string, unknown>>;
};
