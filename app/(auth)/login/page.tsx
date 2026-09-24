import { redirect } from "next/navigation";
import Link from "next/link";
import Button from "@/components/ui/Button";
import TextInput from "@/components/ui/TextInput";
import GoogleAuthButton from "@/components/ui/GoogleAuthButton";
import { serverGet } from "@/lib/api/server";
import type { Profile } from "@/lib/api/types";

/**
 * Login page.
 *
 * The form posts NATIVELY to `POST /api/auth/login`, whose handler forwards
 * the credentials to the backend and relays the backend's `Set-Cookie`
 * header to the browser verbatim (a server action cannot forward response
 * headers — re-issuing the cookie would risk a weaker one reaching the
 * browser). The page works without client JavaScript.
 *
 * Failures come back as a `303` redirect to this page with an `?error=`
 * marker. The markers below map to EXACTLY the copy the old login server
 * action produced. A wrong email and a wrong password land on the same
 * `credentials` marker on purpose: the backend returns one generic 401 for
 * both, and this page must not undo that anti-enumeration contract.
 */
const AUTH_ERRORS: Record<string, { field?: "email" | "password"; message: string }> = {
  email_required: { field: "email", message: "El correo es obligatorio." },
  email_invalid: { field: "email", message: "Ingresa un correo válido." },
  password_required: {
    field: "password",
    message: "La contraseña es obligatoria.",
  },
  credentials: { message: "Correo o contraseña incorrectos." },
  generic: { message: "Algo salió mal. Inténtalo de nuevo." },
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  // Signed-in redirect, confirmed against the backend — never by cookie
  // presence. A present-but-expired cookie is exactly what the middleware
  // refuses to bounce on (see lib/api/middleware.ts); only a profile the
  // backend actually serves proves the session is genuinely valid.
  let signedIn = false;
  try {
    await serverGet<Profile>("/profile");
    signedIn = true;
  } catch {
    // Unconfirmed session (401, backend error or unreachable backend):
    // show the form. Only a backend-confirmed session redirects.
  }
  if (signedIn)
    // Re-entering with a valid session lands on the NEW-CONVERSATION state,
    // matching the post-login redirect in /api/auth/login. The UUID is
    // unique per redirect, so the chat page's React key (`new-${value}`)
    // forces a fresh ChatInterface mount.
    redirect(`/chat?new=${crypto.randomUUID()}`);

  const { error } = await searchParams;
  const marker = typeof error === "string" ? error : undefined;
  const authError = marker
    ? (AUTH_ERRORS[marker] ?? AUTH_ERRORS.generic)
    : undefined;

  return (
    <>
      <h1 className="display-md text-ink mb-6 text-center">Inicia sesión</h1>

      {/* Google OAuth — deliberately unavailable (decision D10): the
          backend implements email + password only. The option stays visible
          and disabled so users read a decision, not a malfunction. */}
      <GoogleAuthButton label="Continuar con Google" />

      {/* Divider */}
      <div className="flex items-center gap-3 my-6" aria-hidden="true">
        <hr className="flex-1 border-hairline" />
        <span className="text-[13px] text-ink-mute">o</span>
        <hr className="flex-1 border-hairline" />
      </div>

      {/* Email/password form — posts natively to the login pipe, which
          forwards the backend's Set-Cookie verbatim. */}
      <form
        action="/api/auth/login"
        method="post"
        noValidate
        className="flex flex-col gap-4"
      >
        <TextInput
          id="email"
          name="email"
          label="Correo electrónico"
          type="email"
          autoComplete="email"
          required
          error={authError?.field === "email" ? authError.message : null}
        />
        <TextInput
          id="password"
          name="password"
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          required
          error={authError?.field === "password" ? authError.message : null}
        />

        {/* Form-level error (bad credentials / backend or network failure) */}
        {authError && !authError.field && (
          <p role="alert" className="text-[13px] text-ink-mute">
            {authError.message}
          </p>
        )}

        <Button type="submit" variant="primary" className="w-full mt-2">
          Iniciar sesión
        </Button>
      </form>

      {/* Forgot password placeholder */}
      <div className="mt-4 text-center">
        <a
          href="#"
          className="text-[13px] text-ink-mute hover:text-ink underline-offset-4 hover:underline"
        >
          ¿Olvidaste tu contraseña?
        </a>
      </div>

      {/* Cross-link to waitlist */}
      <p className="mt-6 text-center text-[13px] text-ink-mute">
        ¿No tienes cuenta?{" "}
        <Link
          href="/#waitlist"
          className="text-ink font-medium hover:underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          Únete a la lista de espera
        </Link>
      </p>
    </>
  );
}
