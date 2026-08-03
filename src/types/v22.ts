export type MarketStateV22 = {
  id: number;
  state_date: string;
  market_state: string;
  opportunity_score: number;
  risk_score: number;
  liquidity_score: number;
  breadth_score: number;
  confidence: number;
  rationale: string;
};

export type TradingDirectiveV22 = {
  id: number;
  directive_date: string;
  directive: string;
  confidence: number;
  target_cash_pct: number;
  deploy_capital_pct: number;
  reduce_exposure_pct: number;
  market_state: string;
  risk_gate: string;
  council_alignment: string;
  portfolio_action: string;
  rationale: string;
};

export type DirectorReasoningV22 = {
  id: number;
  directive_date: string;
  component: string;
  component_status: string;
  score: number;
  weight: number;
  contribution: number;
  explanation: string;
};
