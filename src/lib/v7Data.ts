import { supabase } from "./supabase";
import type { BacktestRun, PriceRow, SignalRow } from "../types/v7";

export async function loadLatestSignals(): Promise<SignalRow[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from("signals")
    .select("*")
    .order("trade_date", { ascending: false })
    .order("score", { ascending: false })
    .limit(50);
  if (error) throw error;
  const rows = (data ?? []) as SignalRow[];
  const latest = rows[0]?.trade_date;
  return latest ? rows.filter((row) => row.trade_date === latest) : rows;
}

export async function loadPriceHistory(symbol: string): Promise<PriceRow[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from("daily_prices")
    .select("symbol,trade_date,open,high,low,close,volume")
    .eq("symbol", symbol)
    .order("trade_date", { ascending: true })
    .limit(260);
  if (error) throw error;
  return (data ?? []) as PriceRow[];
}

export async function loadBacktestRuns(): Promise<BacktestRun[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from("backtest_runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(30);
  if (error) throw error;
  return (data ?? []) as BacktestRun[];
}

export function formatPct(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const normalized = Math.abs(value) <= 2 ? value * 100 : value;
  return `${normalized.toFixed(digits)}%`;
}

export function formatNum(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toFixed(digits);
}
