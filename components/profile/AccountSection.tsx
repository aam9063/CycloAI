"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { createClient } from "@/lib/supabase/client";
import { signOutAction } from "@/app/(app)/actions";

export default function AccountSection() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleDelete() {
    // Double-submit guard
    if (pending) return;

    setPending(true);
    setErrorMsg(null);

    const { error } = await supabase.functions.invoke("delete-account", {
      method: "POST",
    });

    if (error) {
      setPending(false);
      setErrorMsg(
        "No se pudo eliminar la cuenta. Por favor, intenta de nuevo."
      );
      return;
    }

    // On success: sign out then navigate to home
    // Do NOT setPending(false) — the page is navigating away
    await supabase.auth.signOut();
    router.replace("/");
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
