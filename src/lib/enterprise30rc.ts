import { supabase } from "./supabase";
import type {
  PortfolioRecommendation30,
  ReleaseStatus30,
  ResearchOutcome30,
} from "../types/enterprise30rc";

export async function loadEnterprise30RC(accountName = "paper-main") {
  if (!supabase) {
    return {
      recommendations: [] as PortfolioRecommendation30[],
      outcomes: [] as ResearchOutcome30[],
      release: null as ReleaseStatus30 | null,
    };
  }

  const [recommendationsResult, outcomesResult, releaseResult] =
    await Promise.all([
      supabase
        .from("quant_portfolio_recommendations")
        .select("*")
        .eq("account_name", accountName)
        .order("recommendation_date", { ascending: false })
        .order("target_weight", { ascending: false })
        .limit(100),
      supabase
        .from("quant_research_outcomes")
        .select("*")
        .eq("account_name", accountName)
        .order("evaluation_date", { ascending: false })
        .limit(100),
      supabase
        .from("quant_release_status")
        .select("*")
        .eq("account_name", accountName)
        .order("release_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
    ]);

  const error =
    recommendationsResult.error ??
    outcomesResult.error ??
    releaseResult.error;
  if (error) throw error;

  const recommendations = (recommendationsResult.data ?? []).map((row) => ({
    ...row,
    target_weight: Number(row.target_weight ?? 0),
    max_weight: Number(row.max_weight ?? 0),
    expected_return_score: Number(row.expected_return_score ?? 0),
    risk_score: Number(row.risk_score ?? 0),
    conviction: Number(row.conviction ?? 0),
    stop_loss_pct:
      row.stop_loss_pct == null ? null : Number(row.stop_loss_pct),
    take_profit_pct:
      row.take_profit_pct == null ? null : Number(row.take_profit_pct),
    suggested_holding_days:
      row.suggested_holding_days == null
        ? null
        : Number(row.suggested_holding_days),
  })) as PortfolioRecommendation30[];

  const outcomes = (outcomesResult.data ?? []).map((row) => ({
    ...row,
    original_score: Number(row.original_score ?? 0),
    return_pct: row.return_pct == null ? null : Number(row.return_pct),
    holding_days: Number(row.holding_days ?? 0),
  })) as ResearchOutcome30[];

  const release = releaseResult.data
    ? ({
        ...releaseResult.data,
        readiness_score: Number(releaseResult.data.readiness_score ?? 0),
        blockers: Array.isArray(releaseResult.data.blockers)
          ? releaseResult.data.blockers
          : [],
      } as ReleaseStatus30)
    : null;

  return { recommendations, outcomes, release };
}
