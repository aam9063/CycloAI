'use client';

interface TypingIndicatorProps {
  visible: boolean;
}

/**
 * Three-dot pulse animation shown while the assistant is generating a response.
 * The aria-live region announces to screen readers when the indicator appears.
 * Motion gated behind motion-safe: to respect prefers-reduced-motion.
 */
export default function TypingIndicator({ visible }: TypingIndicatorProps) {
  if (!visible) return null;

  return (
    <div className="self-start max-w-[85%] bg-canvas-soft border border-hairline rounded-lg px-4 py-3">
      {/* Accessible announcement (visually hidden) */}
      <span className="sr-only" aria-live="polite">
        CycloAI está escribiendo...
      </span>

      {/* Visual dots */}
      <div className="flex items-center gap-1" aria-hidden="true">
        <span className="block h-2 w-2 rounded-full bg-ink-mute motion-safe:animate-bounce [animation-delay:0ms]" />
        <span className="block h-2 w-2 rounded-full bg-ink-mute motion-safe:animate-bounce [animation-delay:150ms]" />
        <span className="block h-2 w-2 rounded-full bg-ink-mute motion-safe:animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  );
}
