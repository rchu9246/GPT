import { corsHeaders } from "../_shared/cors.ts";
import { createAdminClient } from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const supabase = createAdminClient();
    const body = await req.json().catch(() => ({}));

    // TODO:
    // 對已有足夠未來交易日資料的 signal，
    // 計算 T+1/T+3/T+5/T+10/T+20 報酬與 MFE/MAE。

    const { count, error } = await supabase
      .from("signals")
      .select("*", { count: "exact", head: true });

    if (error) throw error;

    return Response.json(
      {
        ok: true,
        job: "calculate-outcomes",
        mode: "skeleton",
        payload: body,
        signalCount: count ?? 0,
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
