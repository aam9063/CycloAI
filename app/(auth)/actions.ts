"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

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

// Maps Supabase error codes / messages to Spanish copy.
function mapAuthError(error: unknown): string {
  const msg =
    error instanceof Error
      ? error.message
      : typeof error === "string"
      ? error
      : "";

  const lower = msg.toLowerCase();

  if (
    lower.includes("invalid login credentials") ||
    lower.includes("invalid_credentials")
  ) {
    return "Correo o contraseña incorrectos.";
  }
  if (
    lower.includes("user already registered") ||
    lower.includes("user_already_exists") ||
    lower.includes("already registered")
  ) {
    return "Ya existe una cuenta con ese correo.";
  }
  if (
    lower.includes("password should be at least") ||
    lower.includes("weak_password")
  ) {
    return "La contraseña debe tener al menos 6 caracteres.";
  }
  if (
    lower.includes("unable to validate email address") ||
    lower.includes("email_address_invalid")
  ) {
    return "Ingresa un correo válido.";
  }

  return "Algo salió mal. Inténtalo de nuevo.";
}

function validateEmail(email: string): string | null {
  if (!email) return "El correo es obligatorio.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
    return "Ingresa un correo válido.";
  return null;
}

function validatePassword(password: string, isRegister = false): string | null {
  if (!password) return "La contraseña es obligatoria.";
  if (isRegister && password.length < 6)
    return "La contraseña debe tener al menos 6 caracteres.";
  return null;
}

export async function registerAction(
  _prev: AuthResult,
  formData: FormData
): Promise<AuthResult> {
  // WAITLIST MODE: registration locked — remove this guard to re-open signups.
  return {
    error:
      "El registro está cerrado temporalmente. Únete a la lista de espera en cycloai para recibir acceso anticipado.",
  };

  const name = (formData.get("name") as string | null) ?? "";
  const email = (formData.get("email") as string | null) ?? "";
  const password = (formData.get("password") as string | null) ?? "";

  // Collect per-field validation errors before hitting Supabase.
  const fieldErrors: FieldErrors = {};
  if (!name.trim()) fieldErrors.name = "El nombre es obligatorio.";
  const emailError = validateEmail(email);
  if (emailError) fieldErrors.email = emailError ?? undefined;
  const passwordError = validatePassword(password, true);
  if (passwordError) fieldErrors.password = passwordError ?? undefined;
  if (Object.keys(fieldErrors).length > 0) {
    return { error: null, fieldErrors };
  }

  const supabase = await createClient();

  try {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { display_name: name.trim(), full_name: name.trim() },
      },
    });

    if (error) return { error: mapAuthError(error) };
  } catch (err) {
    return { error: mapAuthError(err) };
  }

  // New users always land on onboarding.
  redirect("/onboarding");
}
