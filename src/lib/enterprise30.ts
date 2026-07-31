import { supabase } from "./supabase";
import type {
  CeoSnapshot30,
  ResearchReport30,
  StrategyMarket30,
} from "../types/enterprise30";

export async function loadEnterprise30(accountName = "paper-main") {
  if (!supabase) {
    return {
      snapshot: null as CeoSnapshot30 | null,
      research: [] as ResearchReport30[],
      strategies: [] as StrategyMarket30[],
    };
  }

  const [snapshotResult, researchResult, strategiesResult] =
    await Promise.all([
      supabase
        .from("quant_ceo_snapshots")
        .select("*")
        .eq("account_name", accountName)
        .order("snapshot_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("quant_research_reports")
        .select("*")
        .eq("account_name", accountName)
        .order("report_date", { ascending: false })
        .order("research_score", { ascending: false })
        .limit(100),
      supabase
        .from("quant_strategy_marketplace")
        .select("*")
        .order("enabled", { ascending: false })
        .order("quality_score", { ascending: false })
        .limit(100),
    ]);

  const error =
    snapshotResult.error ??
    researchResult.error ??
    strategiesResult.error;
  if (error) throw error;

  const snapshot = snapshotResult.data
    ? ({
        ...snapshotResult.data,
        research_confidence: Number(
          snapshotResult.data.research_confidence ?? 0,
        ),
        system_health: Number(snapshotResult.data.system_health ?? 0),
        operational_score: Number(
          snapshotResult.data.operational_score ?? 0,
        ),
        equity: Number(snapshotResult.data.equity ?? 0),
        cash: Number(snapshotResult.data.cash ?? 0),
        total_return: Number(snapshotResult.data.total_return ?? 0),
        max_drawdown: Number(snapshotResult.data.max_drawdown ?? 0),
        risk_events: Number(snapshotResult.data.risk_events ?? 0),
        proposed_orders: Number(snapshotResult.data.proposed_orders ?? 0),
        approved_orders: Number(snapshotResult.data.approved_orders ?? 0),
        filled_orders: Number(snapshotResult.data.filled_orders ?? 0),
        top_ideas: Array.isArray(snapshotResult.data.top_ideas)
          ? snapshotResult.data.top_ideas
          : [],
        latest_actions: Array.isArray(snapshotResult.data.latest_actions)
          ? snapshotResult.data.latest_actions
          : [],
      } as CeoSnapshot30)
    : null;

  const research = (researchResult.data ?? []).map((row) => ({
    ...row,
    research_score: Number(row.research_score ?? 0),
    confidence: Number(row.confidence ?? 0),
  })) as ResearchReport30[];

  const strategies = (strategiesResult.data ?? []).map((row) => ({
    ...row,
    enabled: Boolean(row.enabled),
    signal_count: Number(row.signal_count ?? 0),
    quality_score: Number(row.quality_score ?? 0),
    cagr: row.cagr == null ? null : Number(row.cagr),
    sharpe: row.sharpe == null ? null : Number(row.sharpe),
    max_drawdown:
      row.max_drawdown == null ? null : Number(row.max_drawdown),
    win_rate: row.win_rate == null ? null : Number(row.win_rate),
  })) as StrategyMarket30[];

  return { snapshot, research, strategies };
}
