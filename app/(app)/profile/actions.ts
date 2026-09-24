"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ApiError, serverDelete, serverPatch } from "@/lib/api/server";
import type { Profile } from "@/lib/api/types";
import { SESSION_COOKIE_NAME } from "@/lib/api/middleware";

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

/**
 * Deletes the authenticated user's account against the backend
 * (DELETE /account) and ends the session.
 *
 * Security posture:
 * - Session transport: the session cookie is first-party to this app's
 *   host, so the browser never sends it to the backend. The authenticated
 *   call MUST go through the server client (`serverDelete`), which
 *   forwards the incoming request's cookies. There is no browser-side
 *   path to this endpoint.
 * - Local cookie clearing is GATED on success: it runs only after the
 *   backend confirms the account was deleted (200), or in the 404 case
 *   below. A failed deletion returns the error WITHOUT clearing anything,
 *   because signing a user out because their deletion errored would look
 *   like success. The backend clears its own cookie in the response, but
 *   that header is discarded by the server client, so without the local
 *   clear the browser would keep a cookie pointing at a deleted account.
 * - 404 (account already deleted, e.g. a retry after success): treated as
 *   SUCCESS. The user's goal is already achieved — the account does not
 *   exist — and the backend clears its cookie on 404 too, since a token
 *   for a deleted account still verifies. Reporting failure here would be
 *   a lie, so the cookie is cleared and the user is sent on their way.
 */
export async function deleteAccountAction(): Promise<ActionResult> {
  try {
    await serverDelete("/account");
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      // Already deleted: same outcome as success, per the docstring above.
      const cookieStore = await cookies();
      cookieStore.delete(SESSION_COOKIE_NAME);
      redirect("/");
    }
    return {
      error: "No se pudo eliminar la cuenta. Por favor, intenta de nuevo.",
    };
  }

  // The account WAS deleted. Clear the local session cookie (name only;
  // the path default is what was used to set it) and leave.
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE_NAME);

  redirect("/");
}
