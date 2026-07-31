export type OperationalStatus21 = {
  status_date: string;
  pipeline_status: string;
  data_freshness_status: string;
  signals_status: string;
  orders_status: string;
  portfolio_status: string;
  risk_status: string;
  reports_status: string;
  overall_score: number;
  latest_data_date?: string | null;
  latest_signal_date?: string | null;
  proposed_orders: number;
  approved_orders: number;
  filled_orders: number;
  open_positions: number;
  issues: string[];
};

export type RiskEvent21 = {
  id: number;
  event_date: string;
  event_type: string;
  severity: string;
  metric_value?: number | null;
  limit_value?: number | null;
  message: string;
  status: string;
};

export type DailyBrief21 = {
  brief_date: string;
  brief_type: string;
  headline: string;
  summary: string;
  market_view: string;
  portfolio_view: string;
  risk_view: string;
  action_plan: string;
};
