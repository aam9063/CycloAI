"use server";

import { createClient } from "@/lib/supabase/server";

export type WaitlistResult = {
  ok?: boolean;
  already?: boolean;
  error: string | null;
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function joinWaitlist(
  _prev: WaitlistResult,
  formData: FormData
): Promise<WaitlistResult> {
  const raw = (formData.get("email") as string | null) ?? "";
  const source = (formData.get("source") as string | null) ?? "unknown";

  const email = raw.trim().toLowerCase();

  if (!email) return { error: "El correo es obligatorio." };
  if (!EMAIL_RE.test(email)) return { error: "Introduce un correo válido." };

  const supabase = await createClient();

  const { error } = await supabase
    .from("waitlist")
    .insert({ email, source });

  if (error) {
    // Unique violation — already on the list (treat as soft success)
    if (error.code === "23505") {
      return { ok: true, already: true, error: null };
    }
    return { error: "Algo salió mal. Intenta de nuevo en un momento." };
  }

  return { ok: true, error: null };
}
