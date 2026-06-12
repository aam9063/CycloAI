"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

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

export async function loginAction(
  _prev: AuthResult,
  formData: FormData
): Promise<AuthResult> {
  const email = (formData.get("email") as string | null) ?? "";
  const password = (formData.get("password") as string | null) ?? "";

  // Collect per-field validation errors before hitting Supabase.
  const fieldErrors: FieldErrors = {};
  const emailError = validateEmail(email);
  if (emailError) fieldErrors.email = emailError;
  const passwordError = validatePassword(password);
  if (passwordError) fieldErrors.password = passwordError;
  if (Object.keys(fieldErrors).length > 0) {
    return { error: null, fieldErrors };
  }

  const supabase = await createClient();

  let redirectTo = "/chat";

  try {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) return { error: mapAuthError(error) };

    // Read onboarding status to decide redirect destination.
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (user) {
      const { data: profile } = await supabase
        .from("profiles")
        .select("onboarding_completed")
        .eq("id", user.id)
        .single();

      if (!profile?.onboarding_completed) {
        redirectTo = "/onboarding";
      }
    }
  } catch (err) {
    return { error: mapAuthError(err) };
  }

  // redirect() MUST be called outside try/catch — Next throws NEXT_REDIRECT
  // internally and a catch block would swallow it.
  redirect(redirectTo);
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
