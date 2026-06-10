"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";

interface FreeTextAnswerProps {
  id: string;
  label: string;
  placeholder?: string;
  maxLength?: number;
  onSubmit: (value: string) => void;
  disabled: boolean;
  showCounter?: boolean;
  /**
   * When true, renders a <textarea> (multi-line, e.g. Q4 injuries).
   * When false (default), renders <input type="text"> (single-line, e.g. Q6 target_event).
   */
  multiline?: boolean;
  /** When true, focuses the control on mount (question transition focus — W-1). */
  shouldFocus?: boolean;
}

/**
 * Free-text answer control. Renders a <textarea> (Q4) or <input type="text"> (Q6)
 * depending on the `multiline` prop. Label is visually hidden but present for screen readers.
 */
export default function FreeTextAnswer({
  id,
  label,
  placeholder,
  maxLength,
  onSubmit,
  disabled,
  showCounter = false,
  multiline = false,
  shouldFocus = false,
}: FreeTextAnswerProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement | null>(null);

  useEffect(() => {
    if (shouldFocus) {
      inputRef.current?.focus();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(value);
  }

  const sharedInputClass = [
    "w-full rounded-sm border border-hairline bg-canvas",
    "text-ink text-[16px] leading-[1.5] px-3 py-2",
    "placeholder:text-ink-faint",
    "focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
    "transition-colors",
    "disabled:opacity-60 disabled:cursor-not-allowed",
  ].join(" ");

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 motion-safe:animate-[onboardingIn_200ms_ease-out]"
    >
      {/* Visually hidden label — screen readers still announce it */}
      <label htmlFor={id} className="sr-only">
        {label}
      </label>

      {multiline ? (
        <textarea
          ref={inputRef as React.RefObject<HTMLTextAreaElement>}
          id={id}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          maxLength={maxLength}
          disabled={disabled}
          rows={3}
          className={`${sharedInputClass} min-h-[88px] resize-none`}
        />
      ) : (
        <input
          ref={inputRef as React.RefObject<HTMLInputElement>}
          type="text"
          id={id}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          maxLength={maxLength}
          disabled={disabled}
          className={`${sharedInputClass} min-h-[44px]`}
        />
      )}

      {showCounter && maxLength !== undefined && (
        <p className="text-[13px] text-ink-mute text-right leading-none">
          {value.length}/{maxLength}
        </p>
      )}

      <Button type="submit" variant="primary" disabled={disabled}>
        Continuar
      </Button>
    </form>
  );
}
