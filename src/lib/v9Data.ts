import { supabase } from "./supabase";
import type {
  BacktestRun,
  MarketIntelligence,
  PortfolioAllocation,
  PriceRow,
  Rating,
  SignalRow,
  TechnicalSnapshot,
  DecisionAlert,
} from "../types/v9";

type DbSignal = {
  stock_id?: number | string | null;
  trade_date: string;
  strategy_version?: string | null;
  total_score?: number | string | null;
  score?: number | string | null;
  trend_score?: number | string | null;
  momentum_score?: number | string | null;
  volume_score?: number | string | null;
  risk_score?: number | string | null;
  confidence?: number | string | null;
  signal?: string | null;
};

type DbStock = {
  id: number | string;
  symbol?: string | null;
  name?: string | null;
  industry?: string | null;
};

function num(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function key(value: unknown): string {
  return value == null ? "" : String(value);
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

export function ratingFromSignal(row: Pick<SignalRow, "score" | "risk_score" | "confidence">): Rating {
  if (row.score >= 70 && row.risk_score < 45 && row.confidence >= 58) return "STRONG_BUY";
  if (row.score >= 55 && row.risk_score < 60) return "BUY";
  if (row.score >= 40) return "WATCH";
  if (row.score >= 28) return "REDUCE";
  return "AVOID";
}

function mapSignal(row: DbSignal, stockMap: Map<string, DbStock>): SignalRow {
  const stock = stockMap.get(key(row.stock_id));
  const score = num(row.total_score ?? row.score);
  const trend = num(row.trend_score);
  const momentum = num(row.momentum_score);
  const volume = num(row.volume_score);
  const risk = num(row.risk_score, 50);
  const confidence = num(row.confidence, 50);
  const quality = clamp(score * 0.35 + trend * 0.25 + momentum * 0.2 + volume * 0.2 - risk * 0.1);
  const base = {
    symbol: stock?.symbol?.trim() || key(row.stock_id),
    name: stock?.name?.trim() || null,
    industry: stock?.industry?.trim() || null,
    trade_date: row.trade_date,
    strategy_version: row.strategy_version ?? "UNKNOWN",
    score,
    confidence,
    signal: row.signal ?? null,
    risk_score: risk,
    momentum_score: momentum,
    trend_score: trend,
    volume_score: volume,
    quality_score: quality,
  };
  return { ...base, rating: ratingFromSignal(base) };
}

export function dedupeSignals(rows: SignalRow[]): SignalRow[] {
  const best = new Map<string, SignalRow>();
  for (const row of rows) {
    const current = best.get(row.symbol);
    if (!current || row.score > current.score) best.set(row.symbol, row);
  }
  return Array.from(best.values()).sort((a, b) => b.score - a.score);
}

export async function loadLatestSignals(): Promise<SignalRow[]> {
  if (!supabase) return [];
  const [signalsResult, stocksResult] = await Promise.all([
    supabase.from("signals")
      .select("stock_id,trade_date,strategy_version,total_score,trend_score,momentum_score,volume_score,risk_score,confidence,signal")
      .order("trade_date", { ascending: false })
      .order("total_score", { ascending: false })
      .limit(400),
    supabase.from("stocks").select("id,symbol,name,industry").limit(5000),
  ]);
  if (signalsResult.error) throw signalsResult.error;
  if (stocksResult.error) throw stocksResult.error;
  const signals = (signalsResult.data ?? []) as unknown as DbSignal[];
  const stocks = (stocksResult.data ?? []) as unknown as DbStock[];
  const stockMap = new Map<string, DbStock>();
  for (const stock of stocks) stockMap.set(key(stock.id), stock);
  const latestDate = signals.length ? signals[0].trade_date : "";
  return dedupeSignals(signals.filter((row) => !latestDate || row.trade_date === latestDate).map((row) => mapSignal(row, stockMap)));
}

export async function loadPriceHistory(symbol: string): Promise<PriceRow[]> {
  if (!supabase) return [];
  const { data: stock, error: stockError } = await supabase.from("stocks").select("id,symbol").eq("symbol", symbol).limit(1).maybeSingle();
  if (stockError) throw stockError;
  if (!stock?.id) return [];
  const { data, error } = await supabase.from("daily_prices")
    .select("stock_id,trade_date,open,high,low,close,volume")
    .eq("stock_id", stock.id).order("trade_date", { ascending: true }).limit(320);
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
  const { data, error } = await supabase.from("backtest_runs").select("*").order("created_at", { ascending: false }).limit(50);
  if (error) throw error;
  return (data ?? []).map((row) => ({
    id: String(row.id),
    strategy_version: String(row.strategy_version ?? "UNKNOWN"),
    created_at: row.created_at == null ? null : String(row.created_at),
    total_return: row.total_return == null ? null : Number(row.total_return),
    annual_return: row.annual_return == null ? null : Number(row.annual_return),
    max_drawdown: row.max_drawdown == null ? null : Number(row.max_drawdown),
    sharpe_ratio: row.sharpe_ratio == null ? null : Number(row.sharpe_ratio),
    sortino_ratio: row.sortino_ratio == null ? null : Number(row.sortino_ratio),
    win_rate: row.win_rate == null ? null : Number(row.win_rate),
    trade_count: row.total_trades != null ? Number(row.total_trades) : row.trade_count != null ? Number(row.trade_count) : null,
  }));
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function stdev(values: number[]): number | null {
  if (values.length < 2) return null;
  const mean = average(values);
  if (mean == null) return null;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

export function technicalSnapshot(prices: PriceRow[]): TechnicalSnapshot {
  const closes = prices.map((row) => Number(row.close)).filter(Number.isFinite);
  const latest = closes.length ? closes[closes.length - 1] : null;
  const base5 = closes.length > 5 ? closes[closes.length - 6] : closes.length ? closes[0] : null;
  const base20 = closes.length > 20 ? closes[closes.length - 21] : closes.length ? closes[0] : null;
  const change5 = latest != null && base5 != null && base5 !== 0 ? latest / base5 - 1 : null;
  const change20 = latest != null && base20 != null && base20 !== 0 ? latest / base20 - 1 : null;
  const ma5 = average(closes.slice(-5));
  const ma20 = average(closes.slice(-20));
  const ma60 = average(closes.slice(-60));
  const recent60 = closes.slice(-60);
  const high60 = recent60.length ? Math.max(...recent60) : null;
  const low60 = recent60.length ? Math.min(...recent60) : null;
  const drawdown60 = latest != null && high60 != null && high60 !== 0 ? latest / high60 - 1 : null;
  const returns: number[] = [];
  for (let i = 1; i < closes.length; i += 1) if (closes[i - 1] !== 0) returns.push(closes[i] / closes[i - 1] - 1);
  const volatility20 = stdev(returns.slice(-20));
  let gains = 0;
  let losses = 0;
  const recent15 = closes.slice(-15);
  for (let i = 1; i < recent15.length; i += 1) {
    const diff = recent15[i] - recent15[i - 1];
    if (diff >= 0) gains += diff; else losses += Math.abs(diff);
  }
  const periods = Math.max(1, recent15.length - 1);
  const avgGain = gains / periods;
  const avgLoss = losses / periods;
  const rsi14 = avgLoss === 0 ? (avgGain > 0 ? 100 : 50) : 100 - 100 / (1 + avgGain / avgLoss);
  return { latest, change5, change20, ma5, ma20, ma60, rsi14, volatility20, high60, low60, drawdown60 };
}

export function marketIntelligence(signals: SignalRow[]): MarketIntelligence {
  if (!signals.length) return { regime: "RISK_OFF", averageScore: 0, averageRisk: 0, breadth: 0, health: 0, bullishCount: 0, warningCount: 0 };
  const averageScore = signals.reduce((sum, row) => sum + row.score, 0) / signals.length;
  const averageRisk = signals.reduce((sum, row) => sum + row.risk_score, 0) / signals.length;
  const bullishCount = signals.filter((row) => row.rating === "STRONG_BUY" || row.rating === "BUY").length;
  const warningCount = signals.filter((row) => row.risk_score >= 60 || row.rating === "AVOID").length;
  const breadth = bullishCount / signals.length;
  const health = clamp(averageScore * 0.7 + breadth * 30 - averageRisk * 0.18);
  const regime = health >= 55 ? "RISK_ON" : health >= 35 ? "NEUTRAL" : "RISK_OFF";
  return { regime, averageScore, averageRisk, breadth, health, bullishCount, warningCount };
}

export function optimizePortfolio(signals: SignalRow[], maxHoldings = 8): PortfolioAllocation[] {
  const candidates = signals.filter((row) => row.score >= 30).slice(0, maxHoldings);
  const raw = candidates.map((row) => Math.max(0.1, row.score * Math.max(0.2, 1 - row.risk_score / 110) * Math.max(0.3, row.confidence / 100)));
  const total = raw.reduce((sum, value) => sum + value, 0) || 1;
  return candidates.map((row, index) => {
    const weight = raw[index] / total;
    return { ...row, weight, riskContribution: weight * row.risk_score };
  });
}

export function scenarioLoss(allocations: PortfolioAllocation[], shockPercent: number): number {
  return allocations.reduce((sum, row) => sum + row.weight * shockPercent * (0.65 + row.risk_score / 100), 0);
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

export function ratingLabel(rating: Rating): string {
  const labels: Record<Rating, string> = { STRONG_BUY: "強力關注", BUY: "偏多", WATCH: "觀察", REDUCE: "減碼", AVOID: "避開" };
  return labels[rating];
}

export function regimeLabel(regime: MarketIntelligence["regime"]): string {
  return regime === "RISK_ON" ? "風險偏好" : regime === "NEUTRAL" ? "中性盤整" : "風險趨避";
}


export function buildDecisionAlerts(signals: SignalRow[]): DecisionAlert[] {
  const alerts: DecisionAlert[] = [];
  for (const row of signals) {
    if (row.risk_score >= 65) {
      alerts.push({ id: `risk-${row.symbol}`, symbol: row.symbol, title: `${row.symbol} 高風險`, message: `風險分數 ${row.risk_score.toFixed(1)}，建議降低單股權重。`, severity: "CRITICAL" });
    } else if (row.score >= 60 && row.confidence >= 60) {
      alerts.push({ id: `opportunity-${row.symbol}`, symbol: row.symbol, title: `${row.symbol} 訊號轉強`, message: `Score ${row.score.toFixed(1)}、信心 ${row.confidence.toFixed(1)}，可列入優先觀察。`, severity: "INFO" });
    } else if (row.score < 35) {
      alerts.push({ id: `weak-${row.symbol}`, symbol: row.symbol, title: `${row.symbol} 結構偏弱`, message: `Score ${row.score.toFixed(1)}，避免追價並檢查停損。`, severity: "WARNING" });
    }
  }
  return alerts.slice(0, 12);
}

export function compareScore(a: SignalRow, b: SignalRow): number {
  return (a.score - a.risk_score * 0.35 + a.confidence * 0.2) - (b.score - b.risk_score * 0.35 + b.confidence * 0.2);
}


export function sectorRotation(signals: SignalRow[]): import("../types/v9").SectorSnapshot[] {
  const groups = new Map<string, SignalRow[]>();
  for (const row of signals) {
    const industry = row.industry?.trim() || "未分類";
    const current = groups.get(industry) ?? [];
    current.push(row);
    groups.set(industry, current);
  }
  return Array.from(groups.entries()).map(([industry, rows]) => ({
    industry,
    count: rows.length,
    averageScore: rows.reduce((sum, row) => sum + row.score, 0) / rows.length,
    averageRisk: rows.reduce((sum, row) => sum + row.risk_score, 0) / rows.length,
    bullishRatio: rows.filter((row) => row.rating === "STRONG_BUY" || row.rating === "BUY").length / rows.length,
  })).sort((a, b) => (b.averageScore - b.averageRisk * 0.25) - (a.averageScore - a.averageRisk * 0.25));
}

export function strategyScorecards(runs: BacktestRun[]): import("../types/v9").StrategyScorecard[] {
  return runs.map((run) => {
    const totalReturn = Number(run.total_return ?? 0);
    const drawdown = Math.abs(Number(run.max_drawdown ?? 0));
    const sharpe = Number(run.sharpe_ratio ?? 0);
    const winRate = Number(run.win_rate ?? 0);
    const compositeScore = clamp(50 + totalReturn * 35 + sharpe * 12 + winRate * 15 - drawdown * 30);
    const stabilityLabel = compositeScore >= 70 ? "穩健" : compositeScore >= 50 ? "中性" : "待改善";
    return { ...run, compositeScore, stabilityLabel };
  }).sort((a, b) => b.compositeScore - a.compositeScore);
}

export function buildAssistantInsights(signals: SignalRow[]): import("../types/v9").AssistantInsight[] {
  const market = marketIntelligence(signals);
  const sectors = sectorRotation(signals);
  const top = signals[0];
  const insights: import("../types/v9").AssistantInsight[] = [
    {
      title: "市場判讀",
      message: market.regime === "RISK_ON" ? "風險偏好回升，可提高高分低風險標的的研究優先級。" : market.regime === "NEUTRAL" ? "市場處於中性盤整，應採選股不選市並控制總曝險。" : "市場風險偏高，建議提高現金與停損紀律。",
      tone: market.regime === "RISK_ON" ? "POSITIVE" : market.regime === "NEUTRAL" ? "NEUTRAL" : "CAUTION",
    },
  ];
  if (top) insights.push({ title: "首選標的", message: `${top.symbol} ${top.name ?? ""} 目前 Score ${top.score.toFixed(1)}、風險 ${top.risk_score.toFixed(1)}，為去重後優先觀察標的。`, tone: top.risk_score < 50 ? "POSITIVE" : "NEUTRAL" });
  if (sectors[0]) insights.push({ title: "產業輪動", message: `${sectors[0].industry} 目前產業綜合排名領先，平均 Score ${sectors[0].averageScore.toFixed(1)}。`, tone: "NEUTRAL" });
  return insights;
}
