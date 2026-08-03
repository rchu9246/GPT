import { supabase } from "./supabase";
import type {
  DirectorReasoningV22,
  MarketStateV22,
  TradingDirectiveV22,
} from "../types/v22";

export async function loadDirectorV22(accountName = "paper-main") {
  if (!supabase) {
    return {
      directive: null as TradingDirectiveV22 | null,
      market: null as MarketStateV22 | null,
      reasoning: [] as DirectorReasoningV22[],
    };
  }

  const [directiveResult, marketResult, reasoningResult] = await Promise.all([
    supabase
      .from("trading_directives_v22")
      .select("*")
      .eq("account_name", accountName)
      .order("directive_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("market_state_v22")
      .select("*")
      .eq("account_name", accountName)
      .order("state_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("director_reasoning_v22")
      .select("*")
      .eq("account_name", accountName)
      .order("directive_date", { ascending: false })
      .order("contribution", { ascending: false })
      .limit(50),
  ]);

  const error =
    directiveResult.error ?? marketResult.error ?? reasoningResult.error;
  if (error) throw error;

  const directive = directiveResult.data
    ? ({
        ...directiveResult.data,
        confidence: Number(directiveResult.data.confidence ?? 0),
        target_cash_pct: Number(directiveResult.data.target_cash_pct ?? 0),
        deploy_capital_pct: Number(
          directiveResult.data.deploy_capital_pct ?? 0,
        ),
        reduce_exposure_pct: Number(
          directiveResult.data.reduce_exposure_pct ?? 0,
        ),
      } as TradingDirectiveV22)
    : null;

  const market = marketResult.data
    ? ({
        ...marketResult.data,
        opportunity_score: Number(marketResult.data.opportunity_score ?? 0),
        risk_score: Number(marketResult.data.risk_score ?? 0),
        liquidity_score: Number(marketResult.data.liquidity_score ?? 0),
        breadth_score: Number(marketResult.data.breadth_score ?? 0),
        confidence: Number(marketResult.data.confidence ?? 0),
      } as MarketStateV22)
    : null;

  const reasoning = (reasoningResult.data ?? []).map((row) => ({
    ...row,
    score: Number(row.score ?? 0),
    weight: Number(row.weight ?? 0),
    contribution: Number(row.contribution ?? 0),
  })) as DirectorReasoningV22[];

  return { directive, market, reasoning };
}
