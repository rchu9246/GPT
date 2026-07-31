import { supabase } from "./supabase";
import type {
  DailyBrief21,
  OperationalStatus21,
  RiskEvent21,
} from "../types/enterprise21";

export async function loadEnterprise21(accountName = "paper-main") {
  if (!supabase) {
    return {
      operational: null as OperationalStatus21 | null,
      events: [] as RiskEvent21[],
      brief: null as DailyBrief21 | null,
    };
  }

  const [operationalResult, eventsResult, briefResult] = await Promise.all([
    supabase
      .from("quant_operational_status")
      .select("*")
      .eq("account_name", accountName)
      .order("status_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("quant_risk_events")
      .select("*")
      .eq("account_name", accountName)
      .order("event_date", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(50),
    supabase
      .from("quant_daily_briefs")
      .select("*")
      .eq("account_name", accountName)
      .order("brief_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const error =
    operationalResult.error ?? eventsResult.error ?? briefResult.error;
  if (error) throw error;

  const operational = operationalResult.data
    ? ({
        ...operationalResult.data,
        overall_score: Number(operationalResult.data.overall_score ?? 0),
        proposed_orders: Number(operationalResult.data.proposed_orders ?? 0),
        approved_orders: Number(operationalResult.data.approved_orders ?? 0),
        filled_orders: Number(operationalResult.data.filled_orders ?? 0),
        open_positions: Number(operationalResult.data.open_positions ?? 0),
        issues: Array.isArray(operationalResult.data.issues)
          ? operationalResult.data.issues
          : [],
      } as OperationalStatus21)
    : null;

  const events = (eventsResult.data ?? []).map((row) => ({
    ...row,
    metric_value:
      row.metric_value == null ? null : Number(row.metric_value),
    limit_value:
      row.limit_value == null ? null : Number(row.limit_value),
  })) as RiskEvent21[];

  return {
    operational,
    events,
    brief: (briefResult.data as DailyBrief21 | null) ?? null,
  };
}
