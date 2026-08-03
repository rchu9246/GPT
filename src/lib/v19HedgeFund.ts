import { supabase } from "./supabase";
import type {
  HedgeAllocationV19,
  HedgeFundReportV19,
  RiskSnapshotV19,
} from "../types/v19";

export async function loadHedgeFundV19(accountName = "paper-main") {
  if (!supabase) {
    return {
      allocations: [] as HedgeAllocationV19[],
      risk: null as RiskSnapshotV19 | null,
      report: null as HedgeFundReportV19 | null,
    };
  }

  const [allocationsResult, riskResult, reportResult] = await Promise.all([
    supabase
      .from("hedge_fund_allocations_v19")
      .select("*")
      .eq("account_name", accountName)
      .order("strategy_weight", { ascending: false }),
    supabase
      .from("risk_snapshots_v19")
      .select("*")
      .eq("account_name", accountName)
      .order("snapshot_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("hedge_fund_reports_v19")
      .select("*")
      .eq("account_name", accountName)
      .order("report_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const error =
    allocationsResult.error ?? riskResult.error ?? reportResult.error;
  if (error) throw error;

  const allocations = (allocationsResult.data ?? []).map((row) => ({
    ...row,
    strategy_weight: Number(row.strategy_weight ?? 0),
    expected_return: Number(row.expected_return ?? 0),
    expected_volatility: Number(row.expected_volatility ?? 0),
    risk_contribution: Number(row.risk_contribution ?? 0),
  })) as HedgeAllocationV19[];

  const risk = riskResult.data
    ? ({
        ...riskResult.data,
        equity: Number(riskResult.data.equity ?? 0),
        cash: Number(riskResult.data.cash ?? 0),
        gross_exposure: Number(riskResult.data.gross_exposure ?? 0),
        net_exposure: Number(riskResult.data.net_exposure ?? 0),
        daily_var_95: Number(riskResult.data.daily_var_95 ?? 0),
        daily_var_99: Number(riskResult.data.daily_var_99 ?? 0),
        expected_shortfall_95: Number(
          riskResult.data.expected_shortfall_95 ?? 0,
        ),
        max_drawdown: Number(riskResult.data.max_drawdown ?? 0),
        volatility_20d: Number(riskResult.data.volatility_20d ?? 0),
        sharpe_20d: Number(riskResult.data.sharpe_20d ?? 0),
      } as RiskSnapshotV19)
    : null;

  const report = reportResult.data
    ? ({
        ...reportResult.data,
        target_cash_pct: Number(reportResult.data.target_cash_pct ?? 0),
        recommended_gross_exposure: Number(
          reportResult.data.recommended_gross_exposure ?? 0,
        ),
        recommended_net_exposure: Number(
          reportResult.data.recommended_net_exposure ?? 0,
        ),
      } as HedgeFundReportV19)
    : null;

  return { allocations, risk, report };
}
