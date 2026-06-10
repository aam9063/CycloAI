"use client";

import { useEffect, useRef } from "react";
import type { OptionDef } from "@/lib/onboarding/flow";

interface OptionGroupProps {
  options: OptionDef[];
  onSelect: (value: string) => void;
  disabled: boolean;
  name: string;
  /** When true, focuses the first button on mount (question transition focus — W-1). */
  shouldFocus?: boolean;
}

/**
 * Group of instant-fire choice buttons with roving arrow-key keyboard navigation.
 * Plain <button> elements — no radio semantics because there is no persistent
 * selection state; clicking fires the action immediately and the group unmounts.
 */
export default function OptionGroup({
  options,
  onSelect,
  disabled,
  name,
  shouldFocus,
}: OptionGroupProps) {
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Focus the first button when a new question mounts (W-1).
  // shouldFocus is false on the initial page load replay to avoid stealing focus.
  useEffect(() => {
    if (shouldFocus) {
      buttonRefs.current[0]?.focus();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleKeyDown(
    e: React.KeyboardEvent<HTMLButtonElement>,
    index: number
  ) {
    if (e.key === "ArrowDown" || e.key === "ArrowRight") {
      e.preventDefault();
      const next = (index + 1) % options.length;
      buttonRefs.current[next]?.focus();
    } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = (index - 1 + options.length) % options.length;
      buttonRefs.current[prev]?.focus();
    }
  }

  return (
    <div
      aria-label={name}
      className="flex flex-col gap-2 motion-safe:animate-[onboardingIn_200ms_ease-out]"
    >
      {options.map((opt, i) => (
        <button
          key={opt.value}
          ref={(el) => {
            buttonRefs.current[i] = el;
          }}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(opt.value)}
          onKeyDown={(e) => handleKeyDown(e, i)}
          className={[
            "w-full min-h-[44px] text-left rounded-md border px-4 py-2.5 text-[15px] transition-colors",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
            "disabled:opacity-60 disabled:pointer-events-none",
            "border-hairline bg-canvas text-ink hover:border-hairline-strong hover:bg-canvas-soft",
          ].join(" ")}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
