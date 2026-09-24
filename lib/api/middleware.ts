/**
 * Route-gate middleware for the CycloAI frontend.
 *
 * THE DESIGN DECISION — read this before touching this file
 * ---------------------------------------------------------
 * This middleware is a ROUTING CONVENIENCE, NOT a security boundary.
 *
 * It checks only whether the session cookie is PRESENT:
 *   - it never calls the backend;
 *   - it cannot know whether the cookie is valid, and it does not try.
 *
 * THE SECURITY BOUNDARY IS THE BACKEND, which validates the session token on
 * every request (see `backend/src/cycloai/api/deps.py`,
 * `get_current_athlete`). A visitor who forges the cookie passes this
 * middleware and then receives a 401 from the page or route they reached,
 * which is the correct and sufficient outcome. The opposite assumption is
 * the standard way this pattern is misunderstood: nobody should later
 * "harden" this middleware by making it authenticate — verifying the opaque
 * cookie here would mean calling the backend on EVERY request, one extra
 * round trip per navigation across the whole app, to learn nothing the
 * backend does not already enforce.
 *
 * The auth-page redirect deliberately does NOT live here either. Redirecting
 * a signed-in user away from /login or /register on cookie PRESENCE alone
 * creates an infinite bounce for an expired cookie:
 *
 *   cookie present -> /login redirects to /chat -> /chat gets 401 from the
 *   backend -> redirects to /login -> and around again.
 *
 * That is a user who cannot get in at all. The redirect belongs to the auth
 * pages themselves, which CAN ask the backend whether the session is
 * genuinely valid (one call on two infrequent screens). Do not restore that
 * redirect here.
 */

import { NextResponse, type NextRequest } from "next/server";

/**
 * The (single) frontend name of the backend session cookie. Mirrors
 * `AUTH_COOKIE_NAME` in `backend/src/cycloai/api/deps.py`; the contents of
 * the cookie are opaque to the frontend.
 */
export const SESSION_COOKIE_NAME = "cycloai_session";

/** Route prefixes that require a session cookie to be present. */
const PROTECTED_PREFIXES = [
  "/chat",
  "/dashboard",
  "/profile",
  "/plans",
  "/onboarding",
] as const;

/**
 * Auth page paths, exported so the auth pages themselves (the owners of the
 * signed-in redirect) can use the same source of truth instead of
 * restating it.
 */
export const AUTH_PAGES = ["/login", "/register"] as const;

/**
 * Gate requests by cookie presence only. See the module docstring for the
 * boundary decision and the redirect trade-off.
 */
export function sessionGate(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  // Protected route + no session cookie at all -> /login. This is pure
  // routing convenience: a FORGED cookie also passes and is rejected with a
  // 401 by the backend, which is the actual boundary.
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
  if (isProtected && !request.cookies.has(SESSION_COOKIE_NAME)) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    return NextResponse.redirect(loginUrl);
  }

  // Deliberately NOT done here: redirecting a cookie-bearing visitor away
  // from the auth pages. Presence says nothing about validity, and acting on
  // presence alone traps an expired cookie in a redirect loop. The auth
  // pages own that redirect, after confirming the session with the backend.

  return NextResponse.next();
}
