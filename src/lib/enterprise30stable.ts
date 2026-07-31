import { supabase } from "./supabase";
import type {
  DataQuality30,
  StableRun30,
} from "../types/enterprise30stable";

export async function loadEnterprise30Stable(accountName = "paper-main") {
  if (!supabase) {
    return {
      run: null as StableRun30 | null,
      quality: [] as DataQuality30[],
    };
  }

  const [runResult, qualityResult] = await Promise.all([
    supabase
      .from("quant_release_runs")
      .select("*")
      .eq("account_name", accountName)
      .order("started_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("quant_data_quality_checks")
      .select("*")
      .eq("account_name", accountName)
      .order("check_date", { ascending: false })
      .order("check_key", { ascending: true })
      .limit(200),
  ]);

  const error = runResult.error ?? qualityResult.error;
  if (error) throw error;

  const run = runResult.data
    ? ({
        ...runResult.data,
        stage_results: Array.isArray(runResult.data.stage_results)
          ? runResult.data.stage_results
          : [],
        blockers: Array.isArray(runResult.data.blockers)
          ? runResult.data.blockers
          : [],
      } as StableRun30)
    : null;

  return {
    run,
    quality: (qualityResult.data ?? []) as DataQuality30[],
  };
}
