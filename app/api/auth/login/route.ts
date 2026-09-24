import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/api/client";

/**
 * POST /api/auth/login — the login pipe between the browser and the backend.
 *
 * SECURITY — READ BEFORE TOUCHING
 * -------------------------------
 * This handler forwards to a FIXED backend path (`/auth/login`). It must
 * NEVER take a destination from the request — not from a query parameter, a
 * header, a body field, anywhere. A handler that relays a request-chosen
 * destination is an open proxy, and this one exists specifically to move a
 * credential (the session cookie), which makes an open proxy here far more
 * dangerous than a generic one. The request body is used only as the payload
 * of that one fixed call; nothing about the request chooses where anything
 * goes.
 *
 * WHY A ROUTE HANDLER AND NOT A SERVER ACTION
 * -------------------------------------------
 * The backend answers a successful login with `Set-Cookie`, and that cookie
 * must reach the browser VERBATIM — forwarded, never re-issued. A server
 * action would have to re-declare `HttpOnly`, `SameSite`, `Secure` and
 * `Max-Age` from scratch, and if the backend hardened any of those
 * attributes and this layer did not follow, the cookie the browser actually
 * stored would be WEAKER than the one the backend emitted, with nothing
 * failing loudly. Security attributes of a credential are forwarded, never
 * duplicated. The backend's cookies are read with `Headers.getSetCookie()`
 * — the multi-value accessor — so several cookies can never be folded into
 * one string and silently dropped.
 *
 * This is a pipe, not a place for policy: it adds only the blank/format
 * field checks (the login page is a server component with no client
 * JavaScript to pre-validate, and `redirect()` from a server action cannot
 * hand a POST off to this handler) and the onboarding landing decision the
 * page previously made. Everything else is relayed untouched.
 */

/** The ONLY backend path this handler ever contacts. */
const BACKEND_LOGIN_PATH = "/auth/login";
/** Profile path used once, after login, to decide the landing page. */
const BACKEND_PROFILE_PATH = "/profile";
/** Where a failed login lands, with an `?error=` marker the page maps to copy. */
const LOGIN_PAGE = "/login";

/** Same rule as the old login server action; also the backend's minimum. */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** `303 See Other`: the browser repeats a failed login as a clean GET. */
const SEE_OTHER = 303;

function errorRedirect(request: Request, marker: string): NextResponse {
  const url = new URL(LOGIN_PAGE, request.url);
  url.searchParams.set("error", marker);
  return NextResponse.redirect(url, SEE_OTHER);
}

export async function POST(request: Request): Promise<NextResponse> {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return errorRedirect(request, "generic");
  }

  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  // Boundary validation only — identical rules and outcomes to the old
  // server action, moved here because the form now posts natively.
  if (!email) return errorRedirect(request, "email_required");
  if (!EMAIL_PATTERN.test(email)) return errorRedirect(request, "email_invalid");
  if (!password) return errorRedirect(request, "password_required");

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${getApiBaseUrl()}${BACKEND_LOGIN_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    // Backend unreachable: the same generic failure the page already shows
    // for anything that is not bad credentials.
    return errorRedirect(request, "generic");
  }

  // Multi-value accessor on purpose — see the module docstring.
  const setCookies = backendResponse.headers.getSetCookie();

  if (!backendResponse.ok) {
    // The backend answers EVERY bad credential with one generic 401, so this
    // marker cannot reveal whether the email or the password was wrong —
    // that indistinguishability is the backend's anti-enumeration contract
    // and is preserved here deliberately. Any other status stays generic.
    return errorRedirect(
      request,
      backendResponse.status === 401 ? "credentials" : "generic",
    );
  }

  // Success: the session cookie (any cookies) is forwarded verbatim below.
  // The landing decision reads the profile THROUGH the freshly issued
  // session — the browser does not have the cookie yet, so the raw cookie
  // pair from the backend's own response is used directly.
  let destination = "/onboarding";
  try {
    const cookieHeader = setCookies
      .map((cookie) => cookie.split(";")[0])
      .join("; ");
    const profileResponse = await fetch(
      `${getApiBaseUrl()}${BACKEND_PROFILE_PATH}`,
      { headers: { Cookie: cookieHeader } },
    );
    if (profileResponse.ok) {
      const profile = (await profileResponse.json()) as {
        onboarding_completed?: boolean;
      };
      const unique = String(Date.now());
      if (profile.onboarding_completed)
        // Landing on the NEW-CONVERSATION state, not the latest thread:
        // `?new=` is what the chat page checks for its empty view, and the
        // value doubles as the page's React key, so it must be unique per
        // sign-in to force a fresh mount instead of reusing a stale one.
        destination = `/chat?new=${unique}`;
    }
  } catch {
    // Profile unresolvable: /onboarding, the same default the old flow used
    // whenever it could not read an onboarding status.
  }

  const response = NextResponse.redirect(
    new URL(destination, request.url),
    SEE_OTHER,
  );
  for (const cookie of setCookies) {
    // append, not set: one header per cookie, verbatim, attributes intact.
    response.headers.append("set-cookie", cookie);
  }
  return response;
}
