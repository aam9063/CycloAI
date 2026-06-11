'use client';

import { useRef, useEffect, useCallback } from 'react';

interface ChatInputProps {
  onSend: (text: string) => void;
  onStop: () => void;
  isLoading: boolean;
  value: string;
  onChange: (value: string) => void;
  /**
   * When true, the component is rendered inside a floating card container.
   * The outer border/background is removed; the inner textarea and buttons
   * sit directly inside the card's padding.
   * When false (default), the component renders its own border-top + bg.
   */
  floating?: boolean;
}

/**
 * Chat input area with auto-growing textarea.
 * Enter submits; Shift+Enter inserts a newline.
 * Send and Stop buttons meet 44×44px minimum touch target.
 *
 * In floating mode (floating=true), the parent card provides the visual chrome
 * (border, bg, rounded corners, shadow). This component only renders the
 * textarea + action buttons, with appropriate internal padding.
 */
export default function ChatInput({
  onSend,
  onStop,
  isLoading,
  value,
  onChange,
  floating = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow: reset height then set to scrollHeight
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [value]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
  }, [value, isLoading, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const wrapperClass = floating
    ? 'px-3 py-3' // floating: inner padding only; parent card owns border/bg/shadow
    : 'border-t border-hairline bg-canvas px-4 py-3'; // classic: own border-top

  return (
    <div className={wrapperClass}>
      <div className="flex items-end gap-2">
        {/* Message input */}
        <label className="sr-only" htmlFor="chat-input">
          Escribe tu pregunta
        </label>
        <textarea
          ref={textareaRef}
          id="chat-input"
          aria-label="Escribe tu pregunta"
          placeholder="Escribe tu pregunta..."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          maxLength={4000}
          rows={1}
          className={[
            'flex-1 resize-none',
            // In floating mode, textarea is borderless (card owns the border)
            floating
              ? 'rounded-lg bg-transparent border-0 outline-none'
              : 'rounded-lg border border-hairline bg-canvas-soft',
            'px-3 py-2.5 text-[15px] leading-[1.5] text-ink',
            'placeholder:text-ink-faint',
            'focus-visible:outline-none',
            'disabled:opacity-60 disabled:cursor-not-allowed',
            'transition-colors duration-150 overflow-hidden',
          ].join(' ')}
        />

        {/* Stop button (visible only while loading) */}
        {isLoading && (
          <button
            type="button"
            onClick={onStop}
            aria-label="Detener"
            className={[
              'min-h-[44px] min-w-[44px] flex items-center justify-center',
              'rounded-lg border border-hairline bg-canvas text-ink-mute',
              'hover:bg-canvas-soft hover:text-ink',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
              'transition-colors duration-150 shrink-0',
            ].join(' ')}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
            <span className="sr-only">Detener</span>
          </button>
        )}

        {/* Send button — the single emerald CTA in the viewport */}
        {!isLoading && (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isLoading || !value.trim()}
            aria-label="Enviar mensaje"
            className={[
              'min-h-[44px] min-w-[44px] flex items-center justify-center',
              'rounded-lg bg-primary text-on-primary',
              'hover:bg-primary-deep',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
              'disabled:opacity-40 disabled:cursor-not-allowed',
              'transition-colors duration-150 shrink-0',
            ].join(' ')}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
            <span className="sr-only">Enviar mensaje</span>
          </button>
        )}
      </div>
    </div>
  );
}
