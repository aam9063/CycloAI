"use server";

import { createClient } from "@/lib/supabase/server";
import { getClientIp, checkRateLimit } from "@/lib/utils/ratelimit";

export type WaitlistResult = {
  ok?: boolean;
  already?: boolean;
  error: string | null;
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Known source values the client is allowed to send.
const VALID_SOURCES = new Set([
  "landing-hero",
  "landing-cta",
  "landing-pricing",
  "landing-nav",
]);

export async function joinWaitlist(
  _prev: WaitlistResult,
  formData: FormData
): Promise<WaitlistResult> {
  // Rate-limit before any validation to stop floods cheaply.
  const ip = await getClientIp();
  const rl = await checkRateLimit({ key: `waitlist:${ip}`, limit: 5, windowSeconds: 60 });
  if (!rl.success) {
    return { error: "Demasiados intentos. Inténtalo de nuevo en un minuto." };
  }

  // Email: trim, RFC 5321 length cap, regex, normalise.
  const raw = (formData.get("email") as string | null) ?? "";
  const email = raw.trim().toLowerCase();

  if (!email) return { error: "El correo es obligatorio." };
  if (email.length > 320) return { error: "El correo no es válido." };
  if (!EMAIL_RE.test(email)) return { error: "El correo no es válido." };

  // Source: cap length, then whitelist — never store arbitrary client strings.
  const rawSource = formData.get("source") as string | null;
  const sourceCandidate = String(rawSource ?? "").slice(0, 50);
  const source = VALID_SOURCES.has(sourceCandidate) ? sourceCandidate : "unknown";

  const supabase = await createClient();

  const { error } = await supabase
    .from("waitlist")
    .insert({ email, source });

  if (error) {
    // Unique violation — already on the list (treat as soft success)
    if (error.code === "23505") {
      return { ok: true, already: true, error: null };
    }
    return { error: "Algo salió mal. Inténtalo de nuevo en un momento." };
  }

  return { ok: true, error: null };
}
