import { supabase } from "./supabase";
import type { PortfolioDecisionV17 } from "../types/v17";

export async function loadPortfolioDecisionsV17(
  accountName = "paper-main",
): Promise<PortfolioDecisionV17[]> {
  if (!supabase) return [];

  const { data, error } = await supabase
    .from("portfolio_decisions_v17")
    .select("*")
    .eq("account_name", accountName)
    .order("created_at", { ascending: false })
    .limit(100);

  if (error) throw error;

  return (data ?? []).map((row) => ({
    ...row,
    quantity: Number(row.quantity ?? 0),
    average_price: Number(row.average_price ?? 0),
    current_price: Number(row.current_price ?? 0),
    market_value: Number(row.market_value ?? 0),
    unrealized_pnl: Number(row.unrealized_pnl ?? 0),
    score: Number(row.score ?? 0),
    risk_score: Number(row.risk_score ?? 0),
  })) as PortfolioDecisionV17[];
}
