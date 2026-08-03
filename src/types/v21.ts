export type AgentOpinionV21 = {
  id: number;
  council_date: string;
  symbol: string;
  name?: string | null;
  agent_name: string;
  agent_role: string;
  score: number;
  vote: string;
  confidence: number;
  veto: boolean;
  rationale: string;
};

export type CouncilDecisionV21 = {
  id: number;
  council_date: string;
  symbol: string;
  name?: string | null;
  consensus_score: number;
  agreement_pct: number;
  dispersion: number;
  bullish_votes: number;
  neutral_votes: number;
  bearish_votes: number;
  veto_count: number;
  final_decision: string;
  conviction: string;
  target_weight: number;
  cio_memo: string;
  order_id?: string | null;
};

export type CouncilReportV21 = {
  id: number;
  report_date: string;
  market_posture: string;
  symbols_reviewed: number;
  buy_decisions: number;
  hold_decisions: number;
  avoid_decisions: number;
  vetoed_decisions: number;
  average_consensus: number;
  chief_investment_officer_message: string;
  dissent_summary: string;
  execution_guidance: string;
};
