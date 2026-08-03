export type AttributionV20 = {
  id: number;
  attribution_date: string;
  component: string;
  contribution: number;
  exposure: number;
  detail?: string | null;
};

export type InstitutionalReportV20 = {
  id: number;
  report_date: string;
  system_health: number;
  data_status: string;
  signal_status: string;
  execution_status: string;
  portfolio_status: string;
  risk_status: string;
  strategy_status: string;
  headline: string;
  executive_summary: string;
  action_items: string;
};
