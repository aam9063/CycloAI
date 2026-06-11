'use client';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
}

/**
 * Chat message bubble.
 * Reuses the same design tokens as the onboarding bubbles (ADR-7 — own component, shared tokens).
 * Entry animation gated behind motion-safe: for prefers-reduced-motion support.
 */
export default function MessageBubble({ role, content, isStreaming }: MessageBubbleProps) {
  if (role === 'assistant') {
    return (
      <div
        className={[
          'self-start max-w-[85%]',
          'bg-canvas-soft border border-hairline rounded-lg',
          'px-4 py-3 text-[15px] leading-[1.5] text-ink whitespace-pre-wrap',
          'motion-safe:animate-[onboardingIn_200ms_ease-out]',
        ].join(' ')}
      >
        {content}
        {isStreaming && (
          <span className="inline-block w-0.5 h-4 bg-ink-mute ml-0.5 motion-safe:animate-pulse align-middle" aria-hidden="true" />
        )}
      </div>
    );
  }

  return (
    <div
      className={[
        'self-end max-w-[85%]',
        'bg-canvas-night text-on-dark rounded-lg',
        'px-4 py-3 text-[15px] leading-[1.5] whitespace-pre-wrap',
        'motion-safe:animate-[onboardingIn_200ms_ease-out]',
      ].join(' ')}
    >
      {content}
    </div>
  );
}
