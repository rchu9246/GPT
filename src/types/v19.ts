export type HedgeAllocationV19 = {
  id: number;
  allocation_date: string;
  strategy_name: string;
  strategy_weight: number;
  expected_return: number;
  expected_volatility: number;
  risk_contribution: number;
  regime: string;
  allocation_reason?: string | null;
};

export type RiskSnapshotV19 = {
  id: number;
  snapshot_date: string;
  equity: number;
  cash: number;
  gross_exposure: number;
  net_exposure: number;
  daily_var_95: number;
  daily_var_99: number;
  expected_shortfall_95: number;
  max_drawdown: number;
  volatility_20d: number;
  sharpe_20d: number;
  risk_status: string;
  risk_message?: string | null;
};

export type HedgeFundReportV19 = {
  id: number;
  report_date: string;
  market_regime: string;
  portfolio_style: string;
  target_cash_pct: number;
  recommended_gross_exposure: number;
  recommended_net_exposure: number;
  chief_risk_officer_message: string;
  portfolio_manager_message: string;
  execution_plan: string;
};
