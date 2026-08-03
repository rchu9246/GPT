import { supabase } from "./supabase";
import type {
  AgentOpinionV21,
  CouncilDecisionV21,
  CouncilReportV21,
} from "../types/v21";

export async function loadCouncilV21(accountName = "paper-main") {
  if (!supabase) {
    return {
      decisions: [] as CouncilDecisionV21[],
      opinions: [] as AgentOpinionV21[],
      report: null as CouncilReportV21 | null,
    };
  }

  const [decisionsResult, opinionsResult, reportResult] = await Promise.all([
    supabase
      .from("investment_council_decisions_v21")
      .select("*")
      .eq("account_name", accountName)
      .order("consensus_score", { ascending: false })
      .limit(100),
    supabase
      .from("agent_opinions_v21")
      .select("*")
      .eq("account_name", accountName)
      .order("council_date", { ascending: false })
      .order("symbol", { ascending: true })
      .order("score", { ascending: false })
      .limit(500),
    supabase
      .from("council_reports_v21")
      .select("*")
      .eq("account_name", accountName)
      .order("report_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const error =
    decisionsResult.error ?? opinionsResult.error ?? reportResult.error;
  if (error) throw error;

  const decisions = (decisionsResult.data ?? []).map((row) => ({
    ...row,
    consensus_score: Number(row.consensus_score ?? 0),
    agreement_pct: Number(row.agreement_pct ?? 0),
    dispersion: Number(row.dispersion ?? 0),
    bullish_votes: Number(row.bullish_votes ?? 0),
    neutral_votes: Number(row.neutral_votes ?? 0),
    bearish_votes: Number(row.bearish_votes ?? 0),
    veto_count: Number(row.veto_count ?? 0),
    target_weight: Number(row.target_weight ?? 0),
  })) as CouncilDecisionV21[];

  const opinions = (opinionsResult.data ?? []).map((row) => ({
    ...row,
    score: Number(row.score ?? 0),
    confidence: Number(row.confidence ?? 0),
    veto: Boolean(row.veto),
  })) as AgentOpinionV21[];

  const report = reportResult.data
    ? ({
        ...reportResult.data,
        symbols_reviewed: Number(reportResult.data.symbols_reviewed ?? 0),
        buy_decisions: Number(reportResult.data.buy_decisions ?? 0),
        hold_decisions: Number(reportResult.data.hold_decisions ?? 0),
        avoid_decisions: Number(reportResult.data.avoid_decisions ?? 0),
        vetoed_decisions: Number(reportResult.data.vetoed_decisions ?? 0),
        average_consensus: Number(reportResult.data.average_consensus ?? 0),
      } as CouncilReportV21)
    : null;

  return { decisions, opinions, report };
}
