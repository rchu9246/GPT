export type Rating = "STRONG_BUY" | "BUY" | "WATCH" | "REDUCE" | "AVOID";

export type SignalRow = {
  symbol: string;
  name?: string | null;
  industry?: string | null;
  trade_date: string;
  strategy_version: string;
  score: number;
  confidence: number;
  signal?: string | null;
  risk_score: number;
  momentum_score: number;
  trend_score: number;
  volume_score: number;
  quality_score: number;
  rating: Rating;
};

export type PriceRow = {
  symbol: string;
  trade_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type BacktestRun = {
  id: string;
  strategy_version: string;
  created_at?: string | null;
  total_return?: number | null;
  annual_return?: number | null;
  max_drawdown?: number | null;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  win_rate?: number | null;
  trade_count?: number | null;
};

export type TechnicalSnapshot = {
  latest: number | null;
  change5: number | null;
  change20: number | null;
  ma5: number | null;
  ma20: number | null;
  ma60: number | null;
  rsi14: number | null;
  volatility20: number | null;
  high60: number | null;
  low60: number | null;
  drawdown60: number | null;
};

export type PortfolioAllocation = SignalRow & {
  weight: number;
  riskContribution: number;
};

export type MarketIntelligence = {
  regime: "RISK_ON" | "NEUTRAL" | "RISK_OFF";
  averageScore: number;
  averageRisk: number;
  breadth: number;
  health: number;
  bullishCount: number;
  warningCount: number;
};


export type AlertSeverity = "INFO" | "WARNING" | "CRITICAL";

export type DecisionAlert = {
  id: string;
  symbol?: string;
  title: string;
  message: string;
  severity: AlertSeverity;
};


export type SectorSnapshot = {
  industry: string;
  count: number;
  averageScore: number;
  averageRisk: number;
  bullishRatio: number;
};

export type StrategyScorecard = BacktestRun & {
  compositeScore: number;
  stabilityLabel: string;
};

export type AssistantInsight = {
  title: string;
  message: string;
  tone: "POSITIVE" | "NEUTRAL" | "CAUTION";
};
