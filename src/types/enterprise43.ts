export type CommitteeStatus43 = {
  status_date: string;
  overall_status: string;
  sessions_completed: number;
  opinions_generated: number;
  votes_cast: number;
  theses_generated: number;
  decisions_generated: number;
  risk_vetoes: number;
  live_trading_enabled: boolean;
  blockers: string[];
  summary: string;
};

export type CommitteeSession43 = {
  id: string;
  session_date: string;
  session_status: string;
  market_regime: string;
  quorum_reached: number;
  chairman_decision?: string | null;
  chairman_confidence?: number | null;
  final_risk_status?: string | null;
  final_action?: string | null;
  summary?: string | null;
};

export type CommitteeOpinion43 = {
  id: string;
  recommendation: string;
  confidence: number;
  expected_return_pct?: number | null;
  downside_risk_pct?: number | null;
  proposed_weight_pct?: number | null;
  thesis_summary: string;
};

export type InvestmentThesis43 = {
  id: string;
  thesis_date: string;
  final_recommendation: string;
  confidence: number;
  recommended_weight_pct?: number | null;
  expected_return_pct?: number | null;
  downside_risk_pct?: number | null;
  bull_case: string;
  base_case: string;
  bear_case: string;
  explanation: string;
};

export type ExplainableDecision43 = {
  id: string;
  decision_date: string;
  requested_action: string;
  final_action: string;
  confidence: number;
  supporting_reasons: string[];
  opposing_reasons: string[];
  risk_overrides: string[];
  explanation: string;
  approved_for_paper: boolean;
  approved_for_live: boolean;
};
