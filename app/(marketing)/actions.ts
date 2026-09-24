"use server";

import { ApiError, serverPost } from "@/lib/api/server";
import type { DetailAck } from "@/lib/api/types";
import { getClientIp, checkRateLimit } from "@/lib/utils/ratelimit";

export type WaitlistResult = {
  ok?: boolean;
  // No `already` field: the backend (POST /waitlist) returns the same 202 for
  // a fresh signup and a duplicate, by design (idempotent, no enumeration
  // signal). It never carries a true signal, so we don't model it.
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
  //
  // LOAD-BEARING: the backend endpoint (POST /waitlist) has NO rate limiting
  // of its own — see the "Known gap" note in
  // backend/src/cycloai/api/routes_waitlist.py. This Upstash limit is the
  // only throttling on this path, not a decorative second layer.
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

  // Anonymous endpoint: no session check, none needed. Status mapping
  // (backend/src/cycloai/api/routes_waitlist.py):
  //   202 — fresh signup OR duplicate (idempotent by design: the unique
  //         index on lower(email) yields the same acknowledgement, so the
  //         backend does not distinguish them and neither do we)
  //   422 — the database's shape CHECK rejected the email or the source
  //   5xx / network failure — unexpected storage or connectivity failure
  try {
    await serverPost<DetailAck>("/waitlist", { email, source });
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) {
      // Shape rejection: same situation the local validation above covers.
      return { error: "El correo no es válido." };
    }
    return { error: "Algo salió mal. Inténtalo de nuevo en un momento." };
  }

  return { ok: true, error: null };
}
