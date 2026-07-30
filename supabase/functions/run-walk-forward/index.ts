import { corsHeaders } from "../_shared/cors.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const config = await req.json();

    // TODO:
    // 1. 建立 rolling / anchored folds
    // 2. Training 期間搜尋參數
    // 3. Testing 期間固定參數做 OOS
    // 4. 寫入 walk_forward_runs
    // 5. 計算 Stability Score

    return Response.json(
      {
        ok: true,
        job: "run-walk-forward",
        mode: "skeleton",
        config,
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
