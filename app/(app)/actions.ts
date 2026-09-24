"use server";

import { redirect } from "next/navigation";
import { cookies } from "next/headers";

import { SESSION_COOKIE_NAME } from "@/lib/api/middleware";
import { serverDelete } from "@/lib/api/server";

export async function signOutAction() {
  // Tell the backend first. Its logout is idempotent ("no session" is also
  // a success), and a failure there must never leave the user
  // half-signed-out in the browser — so the outcome of this call is
  // deliberately ignored and the cookie is cleared below either way.
  try {
    await serverDelete("/auth/logout");
  } catch {
    // Swallowed on purpose: see above.
  }

  // The backend's own Set-Cookie deletion cannot reach the browser from this
  // server-side fetch, so THIS is what actually signs the browser out.
  // Clearing needs only the name (and the path it was set with, "/") — no
  // attributes to re-declare, unlike login, which must forward the cookie
  // verbatim (see app/api/auth/login/route.ts).
  (await cookies()).delete(SESSION_COOKIE_NAME);

  redirect("/");
}
