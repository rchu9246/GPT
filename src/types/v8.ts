export type Rating = "STRONG_BUY" | "BUY" | "WATCH" | "REDUCE" | "AVOID";

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
  volume_score?: number | null;
  close?: number | null;
  rating?: Rating;
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

export type TechnicalSnapshot = {
  latest: number | null;
  change20: number | null;
  ma20: number | null;
  ma60: number | null;
  rsi14: number | null;
  volatility20: number | null;
  high60: number | null;
  low60: number | null;
};
