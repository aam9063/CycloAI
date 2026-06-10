"use client";

import { useActionState, useEffect, useRef } from "react";
import Link from "next/link";
import Button from "@/components/ui/Button";
import TextInput from "@/components/ui/TextInput";
import GoogleAuthButton from "@/components/ui/GoogleAuthButton";
import { registerAction, type AuthResult } from "@/app/(auth)/actions";

const initialState: AuthResult = { error: null };

export default function RegisterPage() {
  const [state, formAction, pending] = useActionState(registerAction, initialState);

  // Focus the first field with an error after action state updates.
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (state.fieldErrors?.name && nameRef.current) {
      nameRef.current.focus();
    } else if (state.fieldErrors?.email && emailRef.current) {
      emailRef.current.focus();
    } else if (state.fieldErrors?.password && passwordRef.current) {
      passwordRef.current.focus();
    }
  }, [state]);

  return (
    <>
      <h1 className="display-md text-ink mb-6 text-center">Crea tu cuenta</h1>

      {/* Google OAuth */}
      <GoogleAuthButton label="Registrarse con Google" />

      {/* Divider */}
      <div className="flex items-center gap-3 my-6" aria-hidden="true">
        <hr className="flex-1 border-hairline" />
        <span className="text-[13px] text-ink-mute">o</span>
        <hr className="flex-1 border-hairline" />
      </div>

      {/* Registration form */}
      <form action={formAction} noValidate className="flex flex-col gap-4">
        <TextInput
          id="name"
          name="name"
          label="Nombre"
          type="text"
          autoComplete="name"
          required
          error={state.fieldErrors?.name}
          ref={nameRef}
        />
        <TextInput
          id="email"
          name="email"
          label="Correo electrónico"
          type="email"
          autoComplete="email"
          required
          error={state.fieldErrors?.email}
          ref={emailRef}
        />
        <TextInput
          id="password"
          name="password"
          label="Contraseña"
          type="password"
          autoComplete="new-password"
          required
          error={state.fieldErrors?.password}
          ref={passwordRef}
        />

        {/* Form-level error (Supabase / network errors) */}
        {state.error && (
          <p role="alert" className="text-[13px] text-ink-mute">
            {state.error}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          disabled={pending}
          className="w-full mt-2"
        >
          {pending ? "Creando cuenta…" : "Crear cuenta"}
        </Button>
      </form>

      {/* Cross-link to login */}
      <p className="mt-6 text-center text-[13px] text-ink-mute">
        ¿Ya tienes cuenta?{" "}
        <Link
          href="/login"
          className="text-ink font-medium hover:underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          Inicia sesión
        </Link>
      </p>
    </>
  );
}
