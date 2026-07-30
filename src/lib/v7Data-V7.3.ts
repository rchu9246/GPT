import { supabase } from "./supabase";
import type { BacktestRun, PriceRow, SignalRow } from "../types/v7";

type DatabaseSignalRow = {
  id?: number;
  stock_id?: number | string | null;
  trade_date: string;
  strategy_version?: string | null;
  total_score?: number | string | null;
  score?: number | string | null;
  trend_score?: number | string | null;
  momentum_score?: number | string | null;
  volume_score?: number | string | null;
  risk_score?: number | string | null;
  signal?: string | null;
  confidence?: number | string | null;
};

type DatabaseStockRow = {
  id: number | string;
  symbol?: string | null;
  name?: string | null;
  industry?: string | null;
};

function numeric(value: unknown, fallback = 0): number {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value));
}

function stockKey(value: unknown): string {
  return value == null ? "" : String(value);
}

function mapSignal(
  row: DatabaseSignalRow,
  stocksById: Map<string, DatabaseStockRow>,
): SignalRow {
  const stock = stocksById.get(stockKey(row.stock_id));

  // 舊資料庫使用 total_score；若未來新增 score 也可自動相容。
  const totalScore = numeric(row.total_score ?? row.score);
  const trendScore = numeric(row.trend_score);
  const momentumScore = numeric(row.momentum_score);
  const volumeScore = numeric(row.volume_score);
  const riskScore = numeric(row.risk_score);
  const confidence = numeric(row.confidence);

  const derivedValueScore = clamp(
    totalScore * 0.45 +
      trendScore * 0.2 +
      momentumScore * 0.2 +
      volumeScore * 0.15,
  );

  return {
    symbol: stock?.symbol?.trim() || stockKey(row.stock_id),
    name: stock?.name?.trim() || null,
    trade_date: row.trade_date,
    strategy_version: row.strategy_version ?? "UNKNOWN",
    score: totalScore,
    trend_score: trendScore,
    momentum_score: momentumScore,
    value_score: derivedValueScore,
    risk_score: riskScore,
    confidence,
    signal: row.signal ?? null,
  };
}

export async function loadLatestSignals(): Promise<SignalRow[]> {
  if (!supabase) return [];

  /*
   * V7.3 不依賴 Supabase Foreign Key / nested relation。
   * signals 與 stocks 分開讀取，再以前端 Map 配對 stock_id。
   */
  const [signalResult, stockResult] = await Promise.all([
    supabase
      .from("signals")
      .select(
        "id,stock_id,trade_date,strategy_version,total_score,trend_score,momentum_score,volume_score,risk_score,signal,confidence",
      )
      .order("trade_date", { ascending: false })
      .order("total_score", { ascending: false })
      .limit(200),
    supabase
      .from("stocks")
      .select("id,symbol,name,industry")
      .limit(5000),
  ]);

  if (signalResult.error) throw signalResult.error;
  if (stockResult.error) throw stockResult.error;

  const signalRows =
    (signalResult.data ?? []) as unknown as DatabaseSignalRow[];
  const stockRows =
    (stockResult.data ?? []) as unknown as DatabaseStockRow[];

  const stocksById = new Map<string, DatabaseStockRow>();
  for (const stock of stockRows) {
    stocksById.set(stockKey(stock.id), stock);
  }

  const latestDate = signalRows[0]?.trade_date;

  return signalRows
    .filter((row) => !latestDate || row.trade_date === latestDate)
    .map((row) => mapSignal(row, stocksById))
    .sort((a, b) => numeric(b.score) - numeric(a.score));
}

export async function loadPriceHistory(symbol: string): Promise<PriceRow[]> {
  if (!supabase) return [];

  const { data: stock, error: stockError } = await supabase
    .from("stocks")
    .select("id,symbol")
    .eq("symbol", symbol)
    .limit(1)
    .maybeSingle();

  if (stockError) throw stockError;
  if (!stock?.id) return [];

  const { data, error } = await supabase
    .from("daily_prices")
    .select("stock_id,trade_date,open,high,low,close,volume")
    .eq("stock_id", stock.id)
    .order("trade_date", { ascending: true })
    .limit(260);

  if (error) throw error;

  return (data ?? []).map((row) => ({
    symbol,
    trade_date: String(row.trade_date),
    open: row.open == null ? null : Number(row.open),
    high: row.high == null ? null : Number(row.high),
    low: row.low == null ? null : Number(row.low),
    close: row.close == null ? null : Number(row.close),
    volume: row.volume == null ? null : Number(row.volume),
  }));
}

export async function loadBacktestRuns(): Promise<BacktestRun[]> {
  if (!supabase) return [];

  const { data, error } = await supabase
    .from("backtest_runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(30);

  if (error) throw error;

  return (data ?? []).map((row) => ({
    id: String(row.id),
    strategy_version: String(row.strategy_version ?? "UNKNOWN"),
    created_at: row.created_at == null ? null : String(row.created_at),
    total_return:
      row.total_return == null ? null : Number(row.total_return),
    annual_return:
      row.annual_return == null ? null : Number(row.annual_return),
    max_drawdown:
      row.max_drawdown == null ? null : Number(row.max_drawdown),
    sharpe_ratio:
      row.sharpe_ratio == null ? null : Number(row.sharpe_ratio),
    win_rate:
      row.win_rate == null ? null : Number(row.win_rate),
    trade_count:
      row.total_trades != null
        ? Number(row.total_trades)
        : row.trade_count != null
          ? Number(row.trade_count)
          : null,
  }));
}

export function formatPct(
  value?: number | null,
  digits = 1,
): string {
  if (value == null || Number.isNaN(Number(value))) return "—";

  const number = Number(value);
  const normalized = Math.abs(number) <= 2 ? number * 100 : number;

  return `${normalized.toFixed(digits)}%`;
}

export function formatNum(
  value?: number | null,
  digits = 1,
): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}
