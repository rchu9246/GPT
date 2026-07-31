import { supabase } from "./supabase";
import type { CIOReportV18, CommitteeDecisionV18 } from "../types/v18";

export async function loadCommitteeV18(
  accountName = "paper-main",
): Promise<CommitteeDecisionV18[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from("ai_committee_decisions_v18")
    .select("*")
    .eq("account_name", accountName)
    .order("committee_score", { ascending: false })
    .limit(100);

  if (error) throw error;

  return (data ?? []).map((row) => ({
    ...row,
    trend_vote: Number(row.trend_vote ?? 0),
    momentum_vote: Number(row.momentum_vote ?? 0),
    quality_vote: Number(row.quality_vote ?? 0),
    risk_vote: Number(row.risk_vote ?? 0),
    liquidity_vote: Number(row.liquidity_vote ?? 0),
    committee_score: Number(row.committee_score ?? 0),
    target_weight: Number(row.target_weight ?? 0),
  })) as CommitteeDecisionV18[];
}

export async function loadCIOReportV18(
  accountName = "paper-main",
): Promise<CIOReportV18 | null> {
  if (!supabase) return null;
  const { data, error } = await supabase
    .from("cio_reports_v18")
    .select("*")
    .eq("account_name", accountName)
    .order("report_date", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) throw error;
  if (!data) return null;

  return {
    ...data,
    target_cash_pct: Number(data.target_cash_pct ?? 0),
    portfolio_equity: Number(data.portfolio_equity ?? 0),
    portfolio_exposure: Number(data.portfolio_exposure ?? 0),
    proposed_orders: Number(data.proposed_orders ?? 0),
    approved_orders: Number(data.approved_orders ?? 0),
    positions_count: Number(data.positions_count ?? 0),
  } as CIOReportV18;
}
