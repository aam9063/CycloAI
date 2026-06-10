import type { ReactNode } from "react";

interface QuestionBubbleProps {
  children: ReactNode;
}

/**
 * AI/assistant chat bubble — left-aligned, soft canvas background.
 * Wrapped in an aria-live region by the OnboardingChat container.
 */
export default function QuestionBubble({ children }: QuestionBubbleProps) {
  return (
    <div
      className={[
        "self-start max-w-[85%]",
        "bg-canvas-soft border border-hairline rounded-lg",
        "px-4 py-3 text-[15px] leading-[1.5] text-ink",
        "motion-safe:animate-[onboardingIn_200ms_ease-out]",
      ].join(" ")}
    >
      {children}
    </div>
  );
}
