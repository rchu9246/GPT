import { supabase } from "./supabase";
import type { BacktestRun, PriceRow, SignalRow } from "../types/v7";

type StockRelation =
  | { symbol?: string | null; name?: string | null; industry?: string | null }
  | Array<{ symbol?: string | null; name?: string | null; industry?: string | null }>
  | null;

type DatabaseSignalRow = {
  id?: number;
  stock_id?: number;
  trade_date: string;
  strategy_version: string;
  total_score?: number | null;
  trend_score?: number | null;
  momentum_score?: number | null;
  volume_score?: number | null;
  risk_score?: number | null;
  signal?: string | null;
  confidence?: number | null;
  stocks?: StockRelation;
};

function firstStock(relation: StockRelation) {
  return Array.isArray(relation) ? relation[0] ?? null : relation ?? null;
}

function numeric(value: unknown, fallback = 0): number {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value));
}

function mapSignal(row: DatabaseSignalRow): SignalRow {
  const stock = firstStock(row.stocks);
  const totalScore = numeric(row.total_score);
  const trendScore = numeric(row.trend_score);
  const momentumScore = numeric(row.momentum_score);
  const volumeScore = numeric(row.volume_score);
  const riskScore = numeric(row.risk_score);
  const confidence = numeric(row.confidence);
  const derivedValueScore = clamp(
    totalScore * 0.45 + trendScore * 0.2 + momentumScore * 0.2 + volumeScore * 0.15,
  );

  return {
    symbol: stock?.symbol ?? String(row.stock_id ?? ""),
    name: stock?.name ?? null,
    trade_date: row.trade_date,
    strategy_version: row.strategy_version,
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

  const { data, error } = await supabase
    .from("signals")
    .select(
      "id,stock_id,trade_date,strategy_version,total_score,trend_score,momentum_score,volume_score,risk_score,signal,confidence,stocks(symbol,name,industry)",
    )
    .order("trade_date", { ascending: false })
    .order("total_score", { ascending: false })
    .limit(100);

  if (error) throw error;

  const rows = (data ?? []) as unknown as DatabaseSignalRow[];
  const latestDate = rows[0]?.trade_date;

  return rows
    .filter((row) => !latestDate || row.trade_date === latestDate)
    .map(mapSignal)
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

export function formatPct(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const number = Number(value);
  const normalized = Math.abs(number) <= 2 ? number * 100 : number;
  return `${normalized.toFixed(digits)}%`;
}

export function formatNum(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}
