import { supabase } from "./supabase";
import type {
  BacktestRun,
  PriceRow,
  Rating,
  SignalRow,
  TechnicalSnapshot,
} from "../types/v8";

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

function num(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function key(value: unknown): string {
  return value == null ? "" : String(value);
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value));
}

export function ratingFromSignal(signal: SignalRow): Rating {
  const score = num(signal.score);
  const risk = num(signal.risk_score, 50);
  const confidence = num(signal.confidence, 50);

  if (score >= 75 && risk < 45 && confidence >= 60) return "STRONG_BUY";
  if (score >= 60 && risk < 60) return "BUY";
  if (score >= 45) return "WATCH";
  if (score >= 30) return "REDUCE";
  return "AVOID";
}

function mapSignal(
  row: DatabaseSignalRow,
  stocksById: Map<string, DatabaseStockRow>,
): SignalRow {
  const stock = stocksById.get(key(row.stock_id));
  const totalScore = num(row.total_score ?? row.score);
  const trendScore = num(row.trend_score);
  const momentumScore = num(row.momentum_score);
  const volumeScore = num(row.volume_score);
  const riskScore = num(row.risk_score);
  const confidence = num(row.confidence);

  const mapped: SignalRow = {
    symbol: stock?.symbol?.trim() || key(row.stock_id),
    name: stock?.name?.trim() || null,
    trade_date: row.trade_date,
    strategy_version: row.strategy_version ?? "UNKNOWN",
    score: totalScore,
    trend_score: trendScore,
    momentum_score: momentumScore,
    volume_score: volumeScore,
    value_score: clamp(
      totalScore * 0.45 +
        trendScore * 0.2 +
        momentumScore * 0.2 +
        volumeScore * 0.15,
    ),
    risk_score: riskScore,
    confidence,
    signal: row.signal ?? null,
  };
  mapped.rating = ratingFromSignal(mapped);
  return mapped;
}

export function dedupeSignals(rows: SignalRow[]): SignalRow[] {
  const best = new Map<string, SignalRow>();
  for (const row of rows) {
    const current = best.get(row.symbol);
    if (!current || num(row.score) > num(current.score)) {
      best.set(row.symbol, row);
    }
  }
  return Array.from(best.values()).sort((a, b) => num(b.score) - num(a.score));
}

export async function loadLatestSignals(): Promise<SignalRow[]> {
  if (!supabase) return [];

  const [signalResult, stockResult] = await Promise.all([
    supabase
      .from("signals")
      .select(
        "id,stock_id,trade_date,strategy_version,total_score,trend_score,momentum_score,volume_score,risk_score,signal,confidence",
      )
      .order("trade_date", { ascending: false })
      .order("total_score", { ascending: false })
      .limit(300),
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
  for (const stock of stockRows) stocksById.set(key(stock.id), stock);

  const latestDate = signalRows[0]?.trade_date;
  const mapped = signalRows
    .filter((row) => !latestDate || row.trade_date === latestDate)
    .map((row) => mapSignal(row, stocksById));

  return dedupeSignals(mapped);
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
    .limit(300);

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
    total_return: row.total_return == null ? null : Number(row.total_return),
    annual_return: row.annual_return == null ? null : Number(row.annual_return),
    max_drawdown: row.max_drawdown == null ? null : Number(row.max_drawdown),
    sharpe_ratio: row.sharpe_ratio == null ? null : Number(row.sharpe_ratio),
    win_rate: row.win_rate == null ? null : Number(row.win_rate),
    trade_count:
      row.total_trades != null
        ? Number(row.total_trades)
        : row.trade_count != null
          ? Number(row.trade_count)
          : null,
  }));
}

function average(values: number[]): number | null {
  return values.length
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : null;
}

function standardDeviation(values: number[]): number | null {
  if (values.length < 2) return null;
  const mean = average(values);
  if (mean == null) return null;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
    (values.length - 1);
  return Math.sqrt(variance);
}

export function technicalSnapshot(prices: PriceRow[]): TechnicalSnapshot {
  const closes = prices
    .map((row) => Number(row.close))
    .filter((value) => Number.isFinite(value));

  const latest = closes.length ? closes[closes.length - 1] : null;
  const prev20 =
    closes.length > 20
      ? closes[closes.length - 21]
      : closes.length
        ? closes[0]
        : null;
  const change20 =
    latest != null && prev20 != null && prev20 !== 0
      ? latest / prev20 - 1
      : null;

  const ma20 = average(closes.slice(-20));
  const ma60 = average(closes.slice(-60));
  const recent60 = closes.slice(-60);

  const changes: number[] = [];
  for (let i = 1; i < closes.length; i += 1) {
    if (closes[i - 1] !== 0) changes.push(closes[i] / closes[i - 1] - 1);
  }
  const volatility20 = standardDeviation(changes.slice(-20));

  let gains = 0;
  let losses = 0;
  const recent15 = closes.slice(-15);
  for (let i = 1; i < recent15.length; i += 1) {
    const diff = recent15[i] - recent15[i - 1];
    if (diff >= 0) gains += diff;
    else losses += Math.abs(diff);
  }
  const avgGain = recent15.length > 1 ? gains / (recent15.length - 1) : 0;
  const avgLoss = recent15.length > 1 ? losses / (recent15.length - 1) : 0;
  const rsi14 =
    avgLoss === 0 ? (avgGain > 0 ? 100 : 50) : 100 - 100 / (1 + avgGain / avgLoss);

  return {
    latest,
    change20,
    ma20,
    ma60,
    rsi14,
    volatility20,
    high60: recent60.length ? Math.max(...recent60) : null,
    low60: recent60.length ? Math.min(...recent60) : null,
  };
}

export function formatPct(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  const normalized = Math.abs(n) <= 2 ? n * 100 : n;
  return `${normalized.toFixed(digits)}%`;
}

export function formatNum(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

export function ratingLabel(rating?: Rating): string {
  const labels: Record<Rating, string> = {
    STRONG_BUY: "強力關注",
    BUY: "偏多",
    WATCH: "觀察",
    REDUCE: "減碼",
    AVOID: "避開",
  };
  return rating ? labels[rating] : "—";
}
