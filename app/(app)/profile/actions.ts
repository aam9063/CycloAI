"use server";

import { createClient } from "@/lib/supabase/server";

export type ActionResult = {
  error: string | null;
  ok?: boolean;
};

/**
 * Updates the authenticated user's display_name.
 *
 * Security posture:
 * - Auth gate first: getUser() must return a valid user before any DB write.
 * - Whitelist: ONLY display_name is written. No other field from the payload is touched.
 * - Scoped write: WHERE id = user.id — no cross-user writes possible.
 * - Email is NEVER written by this action.
 */
export async function updateDisplayName(
  _prev: ActionResult,
  formData: FormData
): Promise<ActionResult> {
  // Auth gate — must be first
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return { error: "No autenticado" };
  }

  const raw = formData.get("display_name");
  const display_name = String(raw ?? "").trim();

  if (display_name.length === 0) {
    return { error: "El nombre no puede estar vacío." };
  }

  if (display_name.length > 100) {
    return { error: "El nombre no puede superar 100 caracteres." };
  }

  const { error: dbError } = await supabase
    .from("profiles")
    .update({ display_name })
    .eq("id", user.id);

  if (dbError) {
    return { error: "Error al guardar. Intenta de nuevo." };
  }

  return { error: null, ok: true };
}
