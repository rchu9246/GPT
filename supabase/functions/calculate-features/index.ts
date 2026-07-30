import { corsHeaders } from "../_shared/cors.ts";
import { createAdminClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const supabase = createAdminClient();
    const { trade_date } = await req.json().catch(() => ({}));

    // TODO:
    // 1. 讀取足夠長度的 daily_prices
    // 2. 計算 MA / RSI / MACD / ATR / volatility / breakout
    // 3. 合併法人與相對強弱
    // 4. upsert features

    const { count, error } = await supabase
      .from("daily_prices")
      .select("*", { count: "exact", head: true });

    if (error) throw error;

    return Response.json(
      {
        ok: true,
        job: "calculate-features",
        mode: "skeleton",
        tradeDate: trade_date ?? null,
        availablePriceRows: count ?? 0,
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
