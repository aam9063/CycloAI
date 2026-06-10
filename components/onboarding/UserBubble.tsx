import type { ReactNode } from "react";

interface UserBubbleProps {
  children: ReactNode;
}

/**
 * User answer echo bubble — right-aligned, night surface (inverted).
 */
export default function UserBubble({ children }: UserBubbleProps) {
  return (
    <div
      className={[
        "self-end max-w-[85%]",
        "bg-canvas-night text-on-dark rounded-lg",
        "px-4 py-3 text-[15px] leading-[1.5]",
        "motion-safe:animate-[onboardingIn_200ms_ease-out]",
      ].join(" ")}
    >
      {children}
    </div>
  );
}
