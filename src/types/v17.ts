export type PortfolioDecisionV17 = {
  id: number;
  decision_date: string;
  symbol: string;
  quantity?: number | null;
  average_price?: number | null;
  current_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  score?: number | null;
  risk_score?: number | null;
  decision: string;
  reason_code: string;
  reason_message?: string | null;
  created_at: string;
};
