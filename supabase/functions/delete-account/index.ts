// @ts-nocheck — Deno runtime; excluded from Next.js tsconfig.
// This file runs on the Supabase Edge Function runtime (Deno).
// It must NOT be bundled or type-checked by the Next.js TypeScript project.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*", // Tighten to app origin in production hardening
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  // 1. CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { status: 204, headers: corsHeaders });
  }

  // 2. Only POST is accepted
  if (req.method !== "POST") {
    return json({ error: "Method not allowed" }, 405);
  }

  // 3. Extract Bearer JWT from Authorization header
  const authHeader = req.headers.get("Authorization");
  if (!authHeader) {
    return json({ error: "Unauthorized" }, 401);
  }
  const jwt = authHeader.replace("Bearer ", "");

  // 4. Build a service-role client — reads secrets from edge function env ONLY
  //    SUPABASE_SERVICE_ROLE_KEY is never present in the Next.js app code or .env
  const admin = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
  );

  // 5. Verify the JWT and obtain the user's id
  //    getUser validates against the Auth server — belt-and-suspenders with platform verify_jwt
  const {
    data: { user },
    error: authErr,
  } = await admin.auth.getUser(jwt);

  if (authErr || !user) {
    return json({ error: "Unauthorized" }, 401);
  }

  // 6. Delete the caller's own account
  //    The profiles row cascades automatically via migration 003 (ON DELETE CASCADE)
  const { error: delErr } = await admin.auth.admin.deleteUser(user.id);

  if (delErr) {
    return json({ error: "Failed to delete account" }, 500);
  }

  return json({ ok: true }, 200);
});
