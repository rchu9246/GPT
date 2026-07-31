export type CommitteeDecisionV18 = {
  id: number;
  decision_date: string;
  symbol: string;
  name?: string | null;
  trend_vote: number;
  momentum_vote: number;
  quality_vote: number;
  risk_vote: number;
  liquidity_vote: number;
  committee_score: number;
  conviction: string;
  target_weight: number;
  cash_regime: string;
  decision: string;
  memo?: string | null;
  created_at: string;
};

export type CIOReportV18 = {
  id: number;
  report_date: string;
  market_regime: string;
  target_cash_pct: number;
  portfolio_equity: number;
  portfolio_exposure: number;
  proposed_orders: number;
  approved_orders: number;
  positions_count: number;
  chief_message: string;
  risk_message: string;
  action_plan: string;
  created_at: string;
};
