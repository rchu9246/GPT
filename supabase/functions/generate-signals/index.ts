import { corsHeaders } from "../_shared/cors.ts";
import { createAdminClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const supabase = createAdminClient();
    const body = await req.json().catch(() => ({}));
    const strategyVersion = body.strategy_version ?? "V2.0";

    // TODO:
    // 1. 讀取指定日期 features
    // 2. 依 strategy_configs 權重計算 0~100 分
    // 3. 分級 S/A/B/C/D
    // 4. upsert signals

    const { data, error } = await supabase
      .from("strategy_configs")
      .select("*")
      .eq("version", strategyVersion)
      .maybeSingle();

    if (error) throw error;

    return Response.json(
      {
        ok: true,
        job: "generate-signals",
        mode: "skeleton",
        strategy: data ?? null,
      },
      { headers: corsHeaders },
    );
  } catch (error) {
    return Response.json(
      { ok: false, error: String(error) },
      { status: 500, headers: corsHeaders },
    );
  }
});
