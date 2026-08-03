export type PaperAccountV14 = {
  account_name: string;
  starting_cash: number;
  cash: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_fees: number;
  total_tax: number;
  updated_at: string;
};

export type PaperPositionV14 = {
  account_name: string;
  symbol: string;
  name?: string | null;
  quantity: number;
  average_price: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl?: number | null;
  holding_days?: number | null;
  updated_at: string;
};

export type PaperOrderV14 = {
  id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  reference_price: number;
  fill_price?: number | null;
  notional: number;
  score?: number | null;
  risk_score?: number | null;
  confidence?: number | null;
  status: string;
  reason?: string | null;
  exit_reason?: string | null;
  signal_date?: string | null;
  created_at: string;
  filled_at?: string | null;
};

export type PaperFillV14 = {
  id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  fill_price: number;
  gross_amount: number;
  commission: number;
  transaction_tax: number;
  realized_pnl: number;
  trade_date: string;
  filled_at: string;
};

export type EquitySnapshotV14 = {
  snapshot_date: string;
  cash: number;
  market_value: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_return: number;
  positions_count: number;
};

export type EngineRunV14 = {
  id: string;
  run_date: string;
  status: string;
  signals_date?: string | null;
  buy_orders: number;
  sell_orders: number;
  fills: number;
  message?: string | null;
  started_at: string;
  finished_at?: string | null;
};

export type PaperOperationsV14 = {
  account: PaperAccountV14 | null;
  positions: PaperPositionV14[];
  orders: PaperOrderV14[];
  fills: PaperFillV14[];
  snapshots: EquitySnapshotV14[];
  runs: EngineRunV14[];
};
