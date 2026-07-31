import { supabase } from "./supabase";
import type {
  EnterpriseDecision,
  EnterpriseHealth,
  EnterprisePortfolio,
  EnterpriseRun,
} from "../types/enterprise2";

export async function loadEnterprise2(accountName = "paper-main") {
  if (!supabase) {
    return {
      health: null as EnterpriseHealth | null,
      decisions: [] as EnterpriseDecision[],
      latestRun: null as EnterpriseRun | null,
      portfolio: null as EnterprisePortfolio | null,
    };
  }

  const [healthResult, decisionsResult, runResult, portfolioResult] =
    await Promise.all([
      supabase
        .from("quant_system_health")
        .select("*")
        .eq("account_name", accountName)
        .order("health_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("quant_decisions")
        .select("*")
        .eq("account_name", accountName)
        .order("decision_date", { ascending: false })
        .order("score", { ascending: false })
        .limit(100),
      supabase
        .from("quant_runs")
        .select("*")
        .eq("account_name", accountName)
        .order("started_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
      supabase
        .from("quant_portfolio_snapshots")
        .select("*")
        .eq("account_name", accountName)
        .order("snapshot_date", { ascending: false })
        .limit(1)
        .maybeSingle(),
    ]);

  const error =
    healthResult.error ??
    decisionsResult.error ??
    runResult.error ??
    portfolioResult.error;
  if (error) throw error;

  const health = healthResult.data
    ? ({
        ...healthResult.data,
        overall_score: Number(healthResult.data.overall_score ?? 0),
        data_score: Number(healthResult.data.data_score ?? 0),
        signal_score: Number(healthResult.data.signal_score ?? 0),
        execution_score: Number(healthResult.data.execution_score ?? 0),
        portfolio_score: Number(healthResult.data.portfolio_score ?? 0),
        risk_score: Number(healthResult.data.risk_score ?? 0),
        automation_score: Number(healthResult.data.automation_score ?? 0),
        issues: Array.isArray(healthResult.data.issues)
          ? healthResult.data.issues
          : [],
      } as EnterpriseHealth)
    : null;

  const decisions = (decisionsResult.data ?? []).map((row) => ({
    ...row,
    score: row.score == null ? null : Number(row.score),
    confidence: row.confidence == null ? null : Number(row.confidence),
    risk_score: row.risk_score == null ? null : Number(row.risk_score),
    target_weight:
      row.target_weight == null ? null : Number(row.target_weight),
    target_cash_pct:
      row.target_cash_pct == null ? null : Number(row.target_cash_pct),
  })) as EnterpriseDecision[];

  const latestRun = runResult.data
    ? ({
        ...runResult.data,
        module_count: Number(runResult.data.module_count ?? 0),
        success_count: Number(runResult.data.success_count ?? 0),
        failure_count: Number(runResult.data.failure_count ?? 0),
      } as EnterpriseRun)
    : null;

  const portfolio = portfolioResult.data
    ? ({
        ...portfolioResult.data,
        equity: Number(portfolioResult.data.equity ?? 0),
        cash: Number(portfolioResult.data.cash ?? 0),
        market_value: Number(portfolioResult.data.market_value ?? 0),
        gross_exposure_pct: Number(
          portfolioResult.data.gross_exposure_pct ?? 0,
        ),
        net_exposure_pct: Number(
          portfolioResult.data.net_exposure_pct ?? 0,
        ),
        unrealized_pnl: Number(
          portfolioResult.data.unrealized_pnl ?? 0,
        ),
        total_return: Number(portfolioResult.data.total_return ?? 0),
        max_drawdown: Number(portfolioResult.data.max_drawdown ?? 0),
        var_95: Number(portfolioResult.data.var_95 ?? 0),
        sharpe: Number(portfolioResult.data.sharpe ?? 0),
        positions_count: Number(
          portfolioResult.data.positions_count ?? 0,
        ),
      } as EnterprisePortfolio)
    : null;

  return { health, decisions, latestRun, portfolio };
}
