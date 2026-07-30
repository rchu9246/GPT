import { corsHeaders } from "../_shared/cors.ts";
import { createAdminClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const supabase = createAdminClient();
    const config = await req.json();

    const required = ["start_date", "end_date", "strategy_version"];
    for (const field of required) {
      if (!config[field]) throw new Error(`Missing required field: ${field}`);
    }

    // TODO:
    // 1. T 日訊號
    // 2. T+1 開盤成交
    // 3. 模擬 TP / SL / time exit
    // 4. 納入 commission / tax / slippage
    // 5. 寫入 backtest_runs / backtest_trades

    const { data, error } = await supabase
      .from("signals")
      .select("id")
      .gte("trade_date", config.start_date)
      .lte("trade_date", config.end_date)
      .eq("strategy_version", config.strategy_version)
      .limit(1);

    if (error) throw error;

    return Response.json(
      {
        ok: true,
        job: "run-backtest",
        mode: "skeleton",
        config,
        hasSignals: Boolean(data?.length),
      },
      { headers: corsHeaders },
    );
  } catch (error) {
    return Response.json(
      { ok: false, error: String(error) },
      { status: 400, headers: corsHeaders },
    );
  }
});
