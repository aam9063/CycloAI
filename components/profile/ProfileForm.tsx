"use client";

import { useActionState, useEffect } from "react";
import { useRouter } from "next/navigation";
import TextInput from "@/components/ui/TextInput";
import Button from "@/components/ui/Button";
import { updateDisplayName, type ActionResult } from "@/app/(app)/profile/actions";

interface ProfileFormProps {
  initialName: string | null;
  email: string;
}

const initialState: ActionResult = { error: null };

export default function ProfileForm({ initialName, email }: ProfileFormProps) {
  const [state, formAction, isPending] = useActionState(
    updateDisplayName,
    initialState
  );
  const router = useRouter();

  // Refresh server-rendered data (avatar initial, header name) after a save.
  useEffect(() => {
    if (state.ok) router.refresh();
  }, [state, router]);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <TextInput
        id="display_name"
        name="display_name"
        label="Nombre"
        type="text"
        autoComplete="name"
        defaultValue={initialName ?? ""}
        error={state.error}
      />

      {/* Email — read-only display, NOT an input (per spec §4 and ADR in design) */}
      <div className="flex flex-col gap-1">
        <span className="text-[14px] font-medium text-ink leading-none">
          Correo electrónico
        </span>
        <span className="text-[16px] text-ink-mute leading-[1.5]">{email}</span>
      </div>

      <div className="flex items-center gap-4">
        <Button
          type="submit"
          variant="primary"
          disabled={isPending}
        >
          {isPending ? "Guardando..." : "Guardar cambios"}
        </Button>

        {/* Success feedback — announced to screen readers via aria-live */}
        {state.ok && (
          <p
            role="status"
            aria-live="polite"
            className="text-[13px] text-ink-mute"
          >
            Cambios guardados
          </p>
        )}
      </div>
    </form>
  );
}
