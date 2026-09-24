"use client";

import { useActionState } from "react";
import { joinWaitlist, type WaitlistResult } from "@/app/(marketing)/actions";

interface WaitlistFormProps {
  source: string;
}

const initial: WaitlistResult = { error: null };

export default function WaitlistForm({ source }: WaitlistFormProps) {
  const [state, formAction, pending] = useActionState(joinWaitlist, initial);

  const succeeded = state.ok === true;

  return (
    <div className="w-full">
      {succeeded ? (
        // Success state — hide the form, show confirmation
        <div
          role="status"
          aria-live="polite"
          className="flex flex-col items-center gap-2 py-2"
        >
          <p className="text-[15px] font-medium text-on-dark text-center">
            {/* The backend does not distinguish a fresh signup from a duplicate
                (both return the same 202), so there is a single confirmation. */}
            ¡Estás dentro! Te avisaremos en cuanto abramos el acceso.
          </p>
        </div>
      ) : (
        <form
          action={formAction}
          noValidate
          className="flex flex-col sm:flex-row gap-3 w-full"
        >
          {/* Hidden source field */}
          <input type="hidden" name="source" value={source} />

          {/* Email input — full width on mobile, flex-1 on sm+ */}
          <div className="flex-1 flex flex-col gap-1">
            <label htmlFor={`waitlist-email-${source}`} className="sr-only">
              Correo electrónico
            </label>
            <input
              id={`waitlist-email-${source}`}
              name="email"
              type="email"
              required
              autoComplete="email"
              placeholder="tu@email.com"
              aria-label="Correo electrónico"
              aria-invalid={state.error ? "true" : undefined}
              aria-describedby={state.error ? `waitlist-error-${source}` : undefined}
              className={[
                "w-full min-h-[44px] rounded-sm px-4 py-2",
                "text-ink text-[15px] leading-[1.5] bg-canvas",
                "border placeholder:text-ink-faint",
                state.error ? "border-hairline-strong" : "border-hairline",
                "focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
                "transition-colors cursor-text",
              ]
                .join(" ")
                .trim()}
            />
            {/* Inline error */}
            {state.error && (
              <p
                id={`waitlist-error-${source}`}
                role="alert"
                aria-live="polite"
                className="text-[13px] text-on-dark/70"
              >
                {state.error}
              </p>
            )}
          </div>

          {/* Submit button — full width on mobile, auto on sm+ */}
          <button
            type="submit"
            disabled={pending}
            className="
              inline-flex items-center justify-center
              min-h-[44px] px-5 py-2
              bg-primary text-on-primary
              font-medium text-[14px] leading-none
              rounded-sm cursor-pointer
              hover:bg-primary-deep
              focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
              transition-colors
              disabled:opacity-60 disabled:cursor-not-allowed disabled:pointer-events-none
              shrink-0
            "
          >
            {pending ? "Apuntando…" : "Unirme a la lista"}
          </button>
        </form>
      )}
    </div>
  );
}
