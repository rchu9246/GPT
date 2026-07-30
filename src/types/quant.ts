export type Signal = {
  id: number;
  stock_id: number;
  trade_date: string;
  strategy_version: string;
  total_score: number;
  trend_score: number;
  momentum_score: number;
  volume_score: number;
  institutional_score: number;
  breakout_score: number;
  relative_strength_score: number;
  market_score: number;
  risk_score: number;
  signal: string;
  confidence: number;
  stocks?: { symbol: string; name: string; industry: string | null };
};

export type BacktestConfig = {
  startDate: string;
  endDate: string;
  scoreThreshold: number;
  takeProfit: number;
  stopLoss: number;
  maxHoldingDays: number;
  maxPositions: number;
  positionSize: number;
  commissionRate: number;
  taxRate: number;
  slippageRate: number;
  initialCapital: number;
};
