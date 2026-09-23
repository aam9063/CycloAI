"use server";

import { redirect } from "next/navigation";
import { ApiError, serverPatch } from "@/lib/api/server";
import type { Profile } from "@/lib/api/types";

export type ActionResult = {
  error: string | null;
  ok?: boolean;
};

/**
 * Updates the authenticated user's display_name.
 *
 * Security posture:
 * - Auth gate: the backend enforces the session on PATCH /profile; a 401
 *   (session ended between load and submit) redirects to /login instead of
 *   surfacing as a generic failure.
 * - Whitelist: ONLY display_name is sent in the payload. No other field is
 *   included, and no `id` — the backend derives the target profile from the
 *   authenticated caller, so an id in the body could never select a row.
 * - Email is NEVER written by this action.
 */
export async function updateDisplayName(
  _prev: ActionResult,
  formData: FormData
): Promise<ActionResult> {
  const raw = formData.get("display_name");
  const display_name = String(raw ?? "").trim();

  if (display_name.length === 0) {
    return { error: "El nombre no puede estar vacío." };
  }

  if (display_name.length > 100) {
    return { error: "El nombre no puede superar 100 caracteres." };
  }

  try {
    await serverPatch<Profile>("/profile", { display_name });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect("/login");
    }
    return { error: "Error al guardar. Intenta de nuevo." };
  }

  return { error: null, ok: true };
}
