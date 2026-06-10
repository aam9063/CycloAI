"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";

interface FtpInputProps {
  onSubmit: (watts: number) => void;
  disabled: boolean;
  error?: string | null;
  /** When true, focuses the numeric input on mount (question transition focus — W-1). */
  shouldFocus?: boolean;
}

const FTP_ID = "ftp-input";
const FTP_ERROR_ID = "ftp-input-error";

/**
 * Numeric FTP input with client-side range validation (80–500 W).
 * Server-side validation is the authoritative check — this is UX-layer guard only.
 */
export default function FtpInput({
  onSubmit,
  disabled,
  error,
  shouldFocus = false,
}: FtpInputProps) {
  const [value, setValue] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (shouldFocus) {
      inputRef.current?.focus();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const displayError = error ?? localError;
  const hasError = Boolean(displayError);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Guard: input type=number returns "" when blank or non-numeric.
    const raw = value === "" ? NaN : Number(value);
    if (!Number.isFinite(raw) || !Number.isInteger(raw) || raw < 80 || raw > 500) {
      setLocalError("Introduce un valor entre 80 y 500 vatios.");
      return;
    }
    setLocalError(null);
    onSubmit(raw);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 motion-safe:animate-[onboardingIn_200ms_ease-out]"
    >
      <div className="flex flex-col gap-1">
        <label
          htmlFor={FTP_ID}
          className="text-[14px] font-medium text-ink leading-none"
        >
          FTP actual (vatios)
        </label>

        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            id={FTP_ID}
            type="number"
            inputMode="numeric"
            min={80}
            max={500}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (localError) setLocalError(null);
            }}
            disabled={disabled}
            aria-invalid={hasError ? "true" : undefined}
            aria-describedby={hasError ? FTP_ERROR_ID : undefined}
            className={[
              "w-full min-h-[44px] rounded-sm border px-3 py-2",
              "bg-canvas text-ink text-[16px] leading-[1.5]",
              "focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
              "transition-colors",
              "disabled:opacity-60 disabled:cursor-not-allowed",
              hasError ? "border-hairline-strong" : "border-hairline",
            ].join(" ")}
          />
          <span className="text-[15px] text-ink-mute shrink-0">W</span>
        </div>

        {hasError && (
          <p
            id={FTP_ERROR_ID}
            role="alert"
            aria-live="assertive"
            className="text-[13px] text-ink-mute leading-[1.45]"
          >
            {displayError}
          </p>
        )}
      </div>

      <Button type="submit" variant="primary" disabled={disabled}>
        Continuar
      </Button>
    </form>
  );
}
