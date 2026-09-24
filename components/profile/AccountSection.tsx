"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { signOutAction } from "@/app/(app)/actions";
import { deleteAccountAction } from "@/app/(app)/profile/actions";

export default function AccountSection() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleDelete() {
    // Double-submit guard
    if (pending) return;

    setPending(true);
    setErrorMsg(null);

    // The session cookie is first-party to this app's host, so a browser
    // fetch to the backend would carry no session — the deletion goes
    // through the server action, which forwards the cookie.
    const result = await deleteAccountAction();

    if (result.error) {
      setPending(false);
      setErrorMsg(result.error);
      return;
    }

    // On success the action redirects away.
    // Do NOT setPending(false) — the page is navigating away
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Sign out — reuses the existing server action; no confirmation needed (reversible) */}
      <form action={signOutAction}>
        <Button variant="outline" type="submit">
          Cerrar sesión
        </Button>
      </form>

      {/* Delete account — opens ConfirmDialog before any action */}
      <div className="flex flex-col gap-2">
        <Button
          variant="outline"
          type="button"
          onClick={() => {
            setDialogOpen(true);
            setErrorMsg(null);
          }}
        >
          Eliminar cuenta
        </Button>

        {/* Inline error shown on delete failure */}
        {errorMsg && (
          <p
            role="alert"
            aria-live="assertive"
            className="text-[13px] font-medium text-ink"
          >
            {errorMsg}
          </p>
        )}
      </div>

      <ConfirmDialog
        open={dialogOpen}
        title="¿Eliminar tu cuenta?"
        description="Esta acción es permanente e irreversible. Se eliminarán todos tus datos, historial de conversaciones y planes guardados. No es posible deshacer esta operación."
        confirmLabel="Eliminar cuenta"
        cancelLabel="Cancelar"
        pending={pending}
        onClose={() => {
          if (!pending) {
            setDialogOpen(false);
            setErrorMsg(null);
          }
        }}
        onConfirm={handleDelete}
      />
    </div>
  );
}
