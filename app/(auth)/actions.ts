"use server";

// Login lives in `app/api/auth/login/route.ts` now: the backend answers
// with `Set-Cookie`, and the session cookie must be forwarded to the browser
// VERBATIM through a route handler — a server action can only re-issue it,
// which would risk a weaker cookie (mis-declared HttpOnly/SameSite/Secure/
// Max-Age) silently replacing the one the backend emitted.

export type FieldErrors = {
  name?: string;
  email?: string;
  password?: string;
};

export type AuthResult = {
  error: string | null;
  fieldErrors?: FieldErrors;
};

export async function registerAction(
  _prev: AuthResult,
  formData: FormData
): Promise<AuthResult> {
  // WAITLIST MODE: registration locked — remove this guard to re-open signups.
  // Re-opening also means wiring a register endpoint on the backend: the old
  // Supabase signUp path that used to follow this return has been removed,
  // and nothing else performs signup today.
  return {
    error:
      "El registro está cerrado temporalmente. Únete a la lista de espera en cycloai para recibir acceso anticipado.",
  };
}
