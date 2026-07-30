import { corsHeaders } from "../_shared/cors.ts";
import { createAdminClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const supabase = createAdminClient();
    const payload = await req.json().catch(() => ({}));

    // TODO:
    // 1. 呼叫已授權的台股資料來源
    // 2. 正規化股票代號、交易日期與 OHLCV
    // 3. upsert stocks / daily_prices / institutional_flows
    // 4. 回傳寫入筆數與錯誤摘要

    const { count, error } = await supabase
      .from("stocks")
      .select("*", { count: "exact", head: true });

    if (error) throw error;

    return Response.json(
      {
        ok: true,
        job: "ingest-market-data",
        mode: "skeleton",
        payload,
        currentStockCount: count ?? 0,
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
