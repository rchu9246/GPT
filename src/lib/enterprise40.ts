import { supabase } from "./supabase";
import type {
  Portfolio40,
  Regime40,
  Release40,
  Run40,
  Strategy40,
} from "../types/enterprise40";

export async function loadEnterprise40() {
  if (!supabase) {
    return {
      portfolios: [] as Portfolio40[],
      strategies: [] as Strategy40[],
      regime: null as Regime40 | null,
      run: null as Run40 | null,
      release: null as Release40 | null,
    };
  }

  const [portfolioResult, strategyResult, regimeResult, runResult, releaseResult] =
    await Promise.all([
      supabase
        .from("enterprise_portfolios_v40")
        .select("*")
        .order("portfolio_key", { ascending: true }),
      supabase
        .from("enterprise_strategies_v40")
        .select("*")
        .order("strategy_key", { ascending: true }),
      supabase
        .from("market_regimes_v40")
        .select("*")
        .order("regime_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("enterprise_runs_v40")
        .select("*")
        .order("started_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("release_status_v40")
        .select("*")
        .order("release_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
    ]);

  const error =
    portfolioResult.error ??
    strategyResult.error ??
    regimeResult.error ??
    runResult.error ??
    releaseResult.error;
  if (error) throw error;

  const portfolios = (portfolioResult.data ?? []).map((row) => ({
    ...row,
    starting_cash: Number(row.starting_cash ?? 0),
    reserve_cash_pct: Number(row.reserve_cash_pct ?? 0),
    max_positions: Number(row.max_positions ?? 0),
    max_position_pct: Number(row.max_position_pct ?? 0),
  })) as Portfolio40[];

  const strategies = (strategyResult.data ?? []).map((row) => ({
    ...row,
    enabled: Boolean(row.enabled),
    paper_approved: Boolean(row.paper_approved),
    live_approved: Boolean(row.live_approved),
  })) as Strategy40[];

  const regime = regimeResult.data
    ? ({
        ...regimeResult.data,
        confidence: Number(regimeResult.data.confidence ?? 0),
      } as Regime40)
    : null;

  const run = runResult.data
    ? ({
        ...runResult.data,
        blockers: Array.isArray(runResult.data.blockers)
          ? runResult.data.blockers
          : [],
      } as Run40)
    : null;

  const release = releaseResult.data
    ? ({
        ...releaseResult.data,
        readiness_score: Number(releaseResult.data.readiness_score ?? 0),
        blockers: Array.isArray(releaseResult.data.blockers)
          ? releaseResult.data.blockers
          : [],
      } as Release40)
    : null;

  return { portfolios, strategies, regime, run, release };
}
