import { supabase } from "./supabase";
import type {
  AttributionV20,
  InstitutionalReportV20,
} from "../types/v20";

export async function loadInstitutionalV20(
  accountName = "paper-main",
): Promise<{
  attribution: AttributionV20[];
  report: InstitutionalReportV20 | null;
}> {
  if (!supabase) return { attribution: [], report: null };

  const [attributionResult, reportResult] = await Promise.all([
    supabase
      .from("performance_attribution_v20")
      .select("*")
      .eq("account_name", accountName)
      .order("attribution_date", { ascending: false })
      .order("contribution", { ascending: false })
      .limit(50),
    supabase
      .from("institutional_reports_v20")
      .select("*")
      .eq("account_name", accountName)
      .order("report_date", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const error = attributionResult.error ?? reportResult.error;
  if (error) throw error;

  const attribution = (attributionResult.data ?? []).map((row) => ({
    ...row,
    contribution: Number(row.contribution ?? 0),
    exposure: Number(row.exposure ?? 0),
  })) as AttributionV20[];

  const report = reportResult.data
    ? ({
        ...reportResult.data,
        system_health: Number(reportResult.data.system_health ?? 0),
      } as InstitutionalReportV20)
    : null;

  return { attribution, report };
}
