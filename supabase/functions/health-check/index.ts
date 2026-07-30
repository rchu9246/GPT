import { corsHeaders } from "../_shared/cors.ts";

Deno.serve((req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  return Response.json(
    {
      ok: true,
      service: "rchu9246-quant-v2",
      timestamp: new Date().toISOString(),
    },
    { headers: corsHeaders },
  );
});
