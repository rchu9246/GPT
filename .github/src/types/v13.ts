export type TradingMode = "PAPER" | "APPROVAL" | "LIVE_LOCKED";
export type OrderSide = "BUY" | "SELL";
export type OrderStatus = "PROPOSED" | "APPROVED" | "REJECTED" | "FILLED" | "CANCELLED";

export type RiskPolicy = {
  startingCash: number;
  reserveCashPct: number;
  maxPositions: number;
  maxPositionPct: number;
  maxDailyOrders: number;
  minScore: number;
  maxRiskScore: number;
  requireApproval: boolean;
};

export type TradeOrder = {
  id: string;
  createdAt: string;
  symbol: string;
  name?: string | null;
  side: OrderSide;
  quantity: number;
  referencePrice: number;
  notional: number;
  score: number;
  riskScore: number;
  confidence: number;
  reason: string;
  status: OrderStatus;
  mode: TradingMode;
};

export type PaperPosition = {
  symbol: string;
  name?: string | null;
  quantity: number;
  averagePrice: number;
  lastPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  updatedAt: string;
};

export type TradingAccount = {
  cash: number;
  initialEquity: number;
  realizedPnl: number;
};

export type TradingState = {
  mode: TradingMode;
  killSwitch: boolean;
  policy: RiskPolicy;
  account: TradingAccount;
  orders: TradeOrder[];
  positions: PaperPosition[];
};
