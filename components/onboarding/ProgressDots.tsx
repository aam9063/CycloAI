interface ProgressDotsProps {
  /** Total number of main steps (always 6 for this flow). */
  total: number;
  /** Number of steps fully answered. */
  answeredCount: number;
  /** Zero-based index of the current active step. */
  currentIndex: number;
}

/**
 * 6-dot progress indicator. Purely decorative — aria-hidden on the container.
 * Screen reader progress is conveyed by the question bubble content.
 */
export default function ProgressDots({
  total,
  answeredCount,
  currentIndex,
}: ProgressDotsProps) {
  return (
    <div
      role="progressbar"
      aria-valuenow={answeredCount}
      aria-valuemax={total}
      aria-hidden="true"
      className="flex gap-2 mb-6"
    >
      {Array.from({ length: total }, (_, i) => {
        let dotClass = "w-2 h-2 rounded-full motion-safe:transition-colors";

        if (i < answeredCount) {
          // Answered: filled primary (emerald).
          dotClass += " bg-primary";
        } else if (i === currentIndex) {
          // Current: ink.
          dotClass += " bg-ink";
        } else {
          // Upcoming: hairline (empty-looking).
          dotClass += " bg-hairline";
        }

        return <div key={i} className={dotClass} />;
      })}
    </div>
  );
}
