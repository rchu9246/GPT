export type StockRef = {
  symbol: string;
  name: string;
  industry: string | null;
};

export type Signal = {
  id: number;
  stock_id: number;
  trade_date: string;
  strategy_version: string;
  total_score: number;
  trend_score: number;
  momentum_score: number;
  volume_score: number;
  institutional_score: number;
  breakout_score: number;
  relative_strength_score: number;
  market_score: number;
  risk_score: number;
  signal: string;
  confidence: number;
  analysis_reasons?: string[];
  entry_low?: number | null;
  entry_high?: number | null;
  stop_loss_price?: number | null;
  target_price_1?: number | null;
  target_price_2?: number | null;
  stocks?: StockRef;
};

export type PipelineRun = {
  id: string;
  job_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  trade_date: string | null;
  rows_read: number;
  rows_written: number;
  message: string | null;
};

export type MarketRegime = {
  trade_date: string;
  regime: string;
  total_score: number;
  taiex_score: number | null;
};

export type BacktestRun = {
  id: string;
  strategy_version: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number | null;
  score_threshold: number | null;
  take_profit: number | null;
  stop_loss: number | null;
  total_return: number | null;
  annual_return: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  total_trades: number | null;
  average_return: number | null;
  average_holding_days: number | null;
  best_trade: number | null;
  worst_trade: number | null;
  status: string;
  created_at: string;
  completed_at: string | null;
  equity_curve: Array<{ trade: number; equity: number }>;
};

export type BacktestTrade = {
  id: number;
  run_id: string;
  stock_id: number;
  signal_date: string;
  entry_date: string;
  exit_date: string | null;
  entry_price: number;
  exit_price: number;
  gross_return: number;
  net_return: number;
  pnl: number;
  exit_reason: string;
  score: number | null;
  signal: string | null;
  holding_days: number | null;
  stocks?: StockRef;
};

export type StrategyLeaderboardRow = {
  strategy_version: string;
  run_count: number;
  latest_run_at: string;
  avg_total_return: number;
  avg_annual_return: number;
  avg_win_rate: number;
  avg_profit_factor: number;
  avg_max_drawdown: number;
  avg_sharpe_ratio: number;
  avg_total_trades: number;
  best_total_return: number;
};


export type Portfolio = {
  id: string;
  name: string;
  description: string | null;
  initial_capital: number;
  cash_balance: number;
  is_active: boolean;
  created_at: string;
};

export type PortfolioPosition = {
  id: number;
  portfolio_id: string;
  stock_id: number;
  quantity: number;
  average_cost: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_return: number | null;
  weight: number | null;
  opened_at: string;
  stocks?: StockRef;
};

export type PortfolioSnapshot = {
  id: number;
  portfolio_id: string;
  snapshot_date: string;
  cash_balance: number;
  market_value: number;
  total_equity: number;
  daily_return: number | null;
  cumulative_return: number | null;
  max_drawdown: number | null;
  volatility_20d: number | null;
  var_95: number | null;
};

export type DailyReport = {
  id: number;
  report_date: string;
  market_state: string;
  market_score: number;
  strategy_health: number;
  top_signals: Array<{
    symbol: string;
    name: string;
    score: number;
    signal: string;
    confidence: number;
    entry_low: number | null;
    entry_high: number | null;
    stop_loss: number | null;
    target_1: number | null;
    reasons: string[];
  }>;
  risk_flags: Array<{
    symbol: string;
    name: string;
    score: number;
    risk_score: number;
    message: string;
  }>;
  summary: string;
  action_plan: string;
  generated_by: string;
  created_at: string;
};

export type RiskSnapshot = {
  id: number;
  snapshot_date: string;
  average_score: number;
  bullish_ratio: number;
  average_volatility: number;
  average_drawdown: number | null;
  risk_level: string;
  var_95: number | null;
  concentration_risk: number | null;
};
