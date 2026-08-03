import { supabase } from "./supabase";
import type {
  CommitteeOpinion43,
  CommitteeSession43,
  CommitteeStatus43,
  ExplainableDecision43,
  InvestmentThesis43,
} from "../types/enterprise43";

export async function loadEnterprise43() {
  if (!supabase) {
    return {
      status: null as CommitteeStatus43 | null,
      sessions: [] as CommitteeSession43[],
      opinions: [] as CommitteeOpinion43[],
      theses: [] as InvestmentThesis43[],
      decisions: [] as ExplainableDecision43[],
    };
  }

  const [statusResult, sessionResult, opinionResult, thesisResult, decisionResult] =
    await Promise.all([
      supabase
        .from("committee_status_v43")
        .select("*")
        .order("status_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("investment_committee_sessions_v43")
        .select("*")
        .order("session_date", { ascending: false })
        .limit(20),
      supabase
        .from("committee_opinions_v43")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(100),
      supabase
        .from("investment_theses_v43")
        .select("*")
        .order("thesis_date", { ascending: false })
        .limit(20),
      supabase
        .from("explainable_decisions_v43")
        .select("*")
        .order("decision_date", { ascending: false })
        .limit(20),
    ]);

  const error =
    statusResult.error ??
    sessionResult.error ??
    opinionResult.error ??
    thesisResult.error ??
    decisionResult.error;
  if (error) throw error;

  const status = statusResult.data
    ? ({
        ...statusResult.data,
        sessions_completed: Number(statusResult.data.sessions_completed ?? 0),
        opinions_generated: Number(statusResult.data.opinions_generated ?? 0),
        votes_cast: Number(statusResult.data.votes_cast ?? 0),
        theses_generated: Number(statusResult.data.theses_generated ?? 0),
        decisions_generated: Number(statusResult.data.decisions_generated ?? 0),
        risk_vetoes: Number(statusResult.data.risk_vetoes ?? 0),
        blockers: Array.isArray(statusResult.data.blockers)
          ? statusResult.data.blockers
          : [],
      } as CommitteeStatus43)
    : null;

  const sessions = (sessionResult.data ?? []).map((row) => ({
    ...row,
    quorum_reached: Number(row.quorum_reached ?? 0),
    chairman_confidence:
      row.chairman_confidence == null ? null : Number(row.chairman_confidence),
  })) as CommitteeSession43[];

  const opinions = (opinionResult.data ?? []).map((row) => ({
    ...row,
    confidence: Number(row.confidence ?? 0),
    expected_return_pct:
      row.expected_return_pct == null ? null : Number(row.expected_return_pct),
    downside_risk_pct:
      row.downside_risk_pct == null ? null : Number(row.downside_risk_pct),
    proposed_weight_pct:
      row.proposed_weight_pct == null ? null : Number(row.proposed_weight_pct),
  })) as CommitteeOpinion43[];

  const theses = (thesisResult.data ?? []).map((row) => ({
    ...row,
    confidence: Number(row.confidence ?? 0),
    recommended_weight_pct:
      row.recommended_weight_pct == null
        ? null
        : Number(row.recommended_weight_pct),
    expected_return_pct:
      row.expected_return_pct == null ? null : Number(row.expected_return_pct),
    downside_risk_pct:
      row.downside_risk_pct == null ? null : Number(row.downside_risk_pct),
  })) as InvestmentThesis43[];

  const decisions = (decisionResult.data ?? []).map((row) => ({
    ...row,
    confidence: Number(row.confidence ?? 0),
    supporting_reasons: Array.isArray(row.supporting_reasons)
      ? row.supporting_reasons
      : [],
    opposing_reasons: Array.isArray(row.opposing_reasons)
      ? row.opposing_reasons
      : [],
    risk_overrides: Array.isArray(row.risk_overrides)
      ? row.risk_overrides
      : [],
  })) as ExplainableDecision43[];

  return { status, sessions, opinions, theses, decisions };
}
