'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport, type UIMessage } from 'ai';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';
import SuggestionChips from './SuggestionChips';
import ChatInput from './ChatInput';

interface ChatInterfaceProps {
  conversationId?: string;
  initialMessages?: UIMessage[];
}

/**
 * Main chat island component.
 *
 * Layout modes:
 *   - Empty state (no messages): welcome text + chips rendered above a vertically
 *     centered floating input card. The entire content area is used for centering.
 *   - Conversation state (has messages): messages fill the scroll area; the
 *     floating input is anchored at the bottom of the viewport. The messages
 *     container gets bottom padding so the last message is never obscured.
 *
 * Scroll containment:
 *   The outer wrapper is h-full + overflow-hidden. Only the inner messages div
 *   (scrollbar-thin) scrolls. No page-level scrollbar appears.
 *
 * Floating sidebar co-existence:
 *   The sidebar is absolutely positioned by the layout. ChatInterface does not
 *   need to reserve space — it fills the full column width. The sidebar overlays
 *   the messages area, which is intentional (same pattern as Claude's sidebar).
 */
export default function ChatInterface({
  conversationId,
  initialMessages = [],
}: ChatInterfaceProps) {
  const router = useRouter();
  const activeIdRef = useRef<string | undefined>(conversationId);
  const idReplacedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');

  // aria-live: announced once on stream completion (not per-token).
  // The region is always mounted; its content is updated in-place so NVDA/JAWS
  // detect a content change within an existing node (never a node re-insert).
  const [announcedText, setAnnouncedText] = useState('');

  // pendingRefreshRef: when a new conversation is created, we update the URL shallowly
  // (no RSC re-render) and schedule a router.refresh() for AFTER the stream finishes.
  const pendingRefreshRef = useRef(false);

  // Transport is created once. body/fetch callbacks are only called at request time
  // (outside render), so accessing activeIdRef.current there is safe per React semantics.
  /* eslint-disable react-hooks/refs */
  const [transport] = useState(() => {
    return new DefaultChatTransport({
      api: '/api/chat',
      body: () => ({ conversationId: activeIdRef.current }),
      fetch: async (input, init) => {
        const response = await fetch(input, init);
        const newId = response.headers.get('X-Conversation-Id');
        if (newId && newId !== activeIdRef.current && !idReplacedRef.current) {
          activeIdRef.current = newId;
          idReplacedRef.current = true;
          // Shallow history update: updates the browser URL and Next.js
          // usePathname/useParams without triggering an RSC re-render or
          // unmounting this component. The stream and useChat state survive intact.
          window.history.replaceState(null, '', `/chat/${newId}`);
          // Schedule router.refresh() for after the stream finishes so the RSC
          // sidebar picks up the new conversation.
          pendingRefreshRef.current = true;
        }
        return response;
      },
    });
  });
  /* eslint-enable react-hooks/refs */

  const { messages, sendMessage, status, stop, regenerate, error } = useChat({
    messages: initialMessages,
    transport,
    onFinish: ({ message }) => {
      // Announce completed assistant message to screen readers (once, not per token)
      const text = message.parts
        .filter((p) => p.type === 'text')
        .map((p) => (p as { type: 'text'; text: string }).text)
        .join('');
      setAnnouncedText(text);
    },
  });

  const isLoading = status === 'submitted' || status === 'streaming';
  const hasMessages = messages.length > 0;

  // Continue-on-cut affordance:
  // Show when the last assistant message ended abnormally (finishReason !== 'stop')
  // AND the user did NOT explicitly stop it.
  // - User stop (via stop()): onAbort writes { aborted: true } — no finishReason field.
  // - Abnormal cut (Gemini 'other', 'length', etc.): onFinish writes { aborted: true, finishReason } OR { finishReason }.
  // Rule: affordance = finishReason is present AND finishReason !== 'stop'.
  const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null;
  const wasCut = (() => {
    if (status !== 'ready') return false;
    if (!lastMsg || lastMsg.role !== 'assistant') return false;
    const meta = lastMsg.metadata as Record<string, unknown> | undefined;
    if (!meta) return false;
    const fr = meta.finishReason as string | undefined;
    // finishReason must be present and not 'stop' to show the affordance
    return typeof fr === 'string' && fr !== 'stop';
  })();

  // Detect if the assistant has started sending text (for typing indicator logic)
  const lastAssistantMessage = messages.findLast((m) => m.role === 'assistant');
  const assistantHasText =
    lastAssistantMessage !== undefined &&
    lastAssistantMessage.parts.some(
      (p) => p.type === 'text' && (p as { type: 'text'; text: string }).text.length > 0,
    );
  const showTypingIndicator = isLoading && !assistantHasText;

  // Auto-scroll: scroll to bottom unless the user has scrolled up
  const scrollToBottom = useCallback((instant?: boolean) => {
    const container = scrollContainerRef.current;
    if (!container) return;

    // Check if user has scrolled up (with 80px tolerance)
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < 80;

    if (isAtBottom || !userScrolledRef.current) {
      const prefersReducedMotion =
        typeof window !== 'undefined' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      messagesEndRef.current?.scrollIntoView({
        behavior: instant || prefersReducedMotion ? 'auto' : 'smooth',
        block: 'end',
      });
    }
  }, []);

  // Track user scroll
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const isAtBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight < 80;
      userScrolledRef.current = !isAtBottom;
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Scroll on new messages / streaming tokens
  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Initial scroll to bottom (instant)
  useEffect(() => {
    scrollToBottom(true);
    // Focus input on mount
    const ta = document.getElementById('chat-input') as HTMLTextAreaElement | null;
    ta?.focus();
  }, [scrollToBottom]);

  // Deferred router.refresh(): fires once when a new conversation's stream finishes.
  // Waits for status to return to 'ready' so the RSC sidebar update never interrupts
  // an active stream. ChatInterface itself is a Client Component and its useChat state
  // survives the refresh because the component instance stays mounted.
  useEffect(() => {
    if (status === 'ready' && pendingRefreshRef.current) {
      pendingRefreshRef.current = false;
      router.refresh();
    }
  }, [status, router]);

  const handleSend = useCallback(
    (text: string) => {
      if (isLoading) return;
      setInputValue('');
      userScrolledRef.current = false; // Reset scroll lock on new send
      sendMessage({ text });
    },
    [isLoading, sendMessage],
  );

  const handleChipSelect = useCallback(
    (text: string) => {
      if (isLoading) return;
      userScrolledRef.current = false;
      sendMessage({ text });
    },
    [isLoading, sendMessage],
  );

  // Classify error for Spanish copy
  const errorMessage = (() => {
    if (!error) return null;
    const msg = error.message ?? '';
    if (msg.includes('429') || msg.toLowerCase().includes('rate')) {
      return 'El asistente está saturado. Inténtalo de nuevo en un momento.';
    }
    return 'Hubo un error al conectar con el asistente. Inténtalo de nuevo.';
  })();

  // ─── Floating input component ─────────────────────────────────────────────────
  const floatingInput = (
    <div
      className={[
        // Floating card: white bg, rounded-xl, hairline border, Level-2 shadow
        'bg-canvas border border-hairline rounded-xl',
        'shadow-[var(--shadow-float)]',
        // Width: constrained and centered
        'w-full max-w-2xl mx-auto',
        // When anchored at bottom: absolute positioning + horizontal padding from edges
        hasMessages ? 'px-0' : 'px-0',
      ].join(' ')}
    >
      <ChatInput
        onSend={handleSend}
        onStop={stop}
        isLoading={isLoading}
        value={inputValue}
        onChange={setInputValue}
        floating
      />
    </div>
  );

  // ─── Empty / welcome state ────────────────────────────────────────────────────
  if (!hasMessages) {
    return (
      <div className="flex flex-col h-full overflow-hidden chat-no-hscroll">
        {/* Skip link */}
        <a
          href="#chat-main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-on-primary focus:rounded"
        >
          Saltar al chat
        </a>

        {/* Visually-hidden h1 */}
        <h1 className="sr-only">Chat</h1>

        {/* aria-live region — always mounted, never remounted */}
        <div aria-live="polite" aria-atomic="true" className="sr-only">
          {announcedText}
        </div>

        {/* Vertically centered welcome + input */}
        <div className="flex-1 flex flex-col items-center justify-center gap-8 px-4">
          {/* Welcome text */}
          <div className="text-center max-w-md">
            <h2 className="text-[22px] font-semibold text-ink mb-2 tracking-[-0.42px]">
              Hola, soy CycloAI
            </h2>
            <p className="text-[15px] leading-[1.6] text-ink-mute">
              Tu entrenador personal de ciclismo. Pregunta lo que necesites
              sobre entrenamiento, nutrición o preparación física.
            </p>
          </div>

          {/* Floating input card — vertically centered */}
          <div className="w-full max-w-2xl px-4 md:px-8">
            {floatingInput}
          </div>

          {/* Suggestion chips below the input */}
          <SuggestionChips
            onSelect={handleChipSelect}
            disabled={isLoading}
          />
        </div>
      </div>
    );
  }

  // ─── Conversation state (has messages) ───────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden chat-no-hscroll relative">
      {/* Skip link */}
      <a
        href="#chat-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-on-primary focus:rounded"
      >
        Saltar al chat
      </a>

      {/* Visually-hidden h1 */}
      <h1 className="sr-only">Chat</h1>

      {/* aria-live region — always mounted, content updated in-place */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcedText}
      </div>

      {/* Messages scroll area — fills available height, scrolls internally.
          Bottom padding reserves space for the floating input (approx 96px). */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin pb-[108px] px-4 pt-6"
      >
        <div className="flex flex-col gap-3 max-w-2xl mx-auto">
          {messages.map((msg) => {
            const textContent = msg.parts
              .filter((p) => p.type === 'text')
              .map((p) => (p as { type: 'text'; text: string }).text)
              .join('');

            const isLastAssistant =
              msg === messages[messages.length - 1] &&
              msg.role === 'assistant' &&
              status === 'streaming';

            return (
              <MessageBubble
                key={msg.id}
                role={msg.role as 'user' | 'assistant'}
                content={textContent}
                isStreaming={isLastAssistant}
              />
            );
          })}

          {/* Typing indicator (pre-first-token) */}
          <TypingIndicator visible={showTypingIndicator} />

          {/* Continue-on-cut affordance — shown when Gemini ends stream abnormally */}
          {wasCut && !errorMessage && (
            <div className="self-start max-w-[85%]">
              <p className="text-[13px] text-ink-mute mb-1.5">
                La respuesta se interrumpió.
              </p>
              <button
                type="button"
                onClick={() => handleSend('continúa')}
                className={[
                  'min-h-[44px] px-3 py-2 rounded-lg border border-hairline',
                  'text-[13px] font-medium text-ink',
                  'bg-canvas hover:bg-surface-hover',
                  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
                  'transition-colors',
                ].join(' ')}
              >
                Continuar
              </button>
            </div>
          )}

          {/* Inline error block */}
          {errorMessage && (
            <div
              role="alert"
              className="self-start max-w-[85%] bg-canvas border border-hairline rounded-lg px-4 py-3"
            >
              <p className="text-[14px] text-ink-mute mb-2">{errorMessage}</p>
              <button
                type="button"
                onClick={() => regenerate()}
                className={[
                  'text-[13px] font-medium text-primary underline underline-offset-2',
                  'hover:text-primary-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
                ].join(' ')}
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Floating input — anchored at the bottom, overlapping scroll area.
          absolute + bottom-inset so it sits above the scroll region visually.
          The scroll area's pb-[108px] ensures the last message clears it. */}
      <div className="absolute bottom-0 left-0 right-0 px-4 pb-4 z-10">
        <div className="max-w-2xl mx-auto">
          {floatingInput}
        </div>
      </div>
    </div>
  );
}
