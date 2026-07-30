export type SignalRow = {
  symbol: string;
  name?: string | null;
  trade_date: string;
  strategy_version: string;
  score?: number | null;
  confidence?: number | null;
  signal?: string | null;
  risk_score?: number | null;
  momentum_score?: number | null;
  trend_score?: number | null;
  value_score?: number | null;
  close?: number | null;
};

export type PriceRow = {
  symbol: string;
  trade_date: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
};

export type BacktestRun = {
  id: string;
  strategy_version: string;
  created_at?: string | null;
  total_return?: number | null;
  annual_return?: number | null;
  max_drawdown?: number | null;
  sharpe_ratio?: number | null;
  win_rate?: number | null;
  trade_count?: number | null;
};

export type PortfolioHolding = {
  symbol: string;
  name?: string;
  weight: number;
  expectedReturn: number;
  volatility: number;
  riskContribution: number;
};
