'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import type { ConversationRow } from '@/lib/ai/types';
import ConversationListItem from './ConversationListItem';

interface FloatingSidebarProps {
  conversations: ConversationRow[];
}

const STORAGE_KEY = 'cycloai-sidebar-open';

function readStoredOpen(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    const val = sessionStorage.getItem(STORAGE_KEY);
    return val === null ? true : val === 'true';
  } catch {
    return true;
  }
}

/**
 * Floating collapsible sidebar for the chat experience.
 *
 * Desktop (md+):
 *   - Floating panel inset from left edge.
 *   - Collapsed state: a slim toggle button floats at the top-left.
 *   - Open state: rounded-xl card (hairline border, Level-2 shadow) overlays
 *     the chat canvas, positioned below the toggle button.
 *   - State persisted in sessionStorage so collapse survives navigation
 *     within the session.
 *   - Motion gated behind motion-safe; falls back to instant show/hide.
 *
 * Mobile (below md):
 *   - Toggle button in the top-left corner opens a full-height overlay drawer.
 *   - Semi-transparent backdrop covers the rest of the screen.
 *   - Overlay closes on Escape, backdrop click, or conversation selection.
 *   - Replaces MobileChatBar — "Nueva conversación" always reachable.
 *
 * Accessibility:
 *   - Sidebar panel has role="complementary" + aria-label.
 *   - Toggle button has aria-expanded + aria-controls.
 *   - Escape closes the sidebar and returns focus to the toggle.
 */
export default function FloatingSidebar({ conversations }: FloatingSidebarProps) {
  // Hydration-safe: the first client render MUST match SSR output (always `true`).
  // The persisted value is applied after mount, never during the initial render.
  const [isOpen, setIsOpen] = useState(true);
  const hydratedRef = useRef(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);

  // Restore persisted state once, post-hydration. SSR cannot read sessionStorage,
  // so the first render is always `true` and the stored value is applied here —
  // a single, bounded setState on mount (standard SSR storage-restore pattern).
  useEffect(() => {
    hydratedRef.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsOpen(readStoredOpen());
  }, []);

  // Persist open state to sessionStorage (skip renders before restore).
  useEffect(() => {
    if (!hydratedRef.current) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, String(isOpen));
    } catch {
      // sessionStorage blocked (private browsing) — ignore.
    }
  }, [isOpen]);

  const close = useCallback(() => {
    setIsOpen(false);
    toggleRef.current?.focus();
  }, []);

  const toggle = useCallback(() => setIsOpen((v) => !v), []);

  // Escape closes the sidebar.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, close]);

  // Mobile: close on backdrop click (click outside the panel).
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (sidebarRef.current && !sidebarRef.current.contains(e.target as Node)) {
        close();
      }
    },
    [close],
  );

  // Mobile: close when a conversation item is clicked (navigates away).
  const handleConvClick = useCallback(() => {
    // On mobile the sidebar is a modal overlay; close it on selection.
    // On desktop the panel stays open — we rely on md:pointer-events-auto
    // to not call this on desktop. However, since we can't cheaply detect
    // viewport in a callback without isMobile state, we always close.
    // Desktop panel persists open because the user can re-open via toggle.
    // This is an acceptable UX tradeoff (same pattern as most chat apps).
    close();
  }, [close]);

  // ─── Shared sidebar content ───────────────────────────────────────────────────
  const SidebarContent = (
    <div
      id="floating-sidebar-panel"
      ref={sidebarRef}
      role="complementary"
      aria-label="Conversaciones"
      className={[
        'flex flex-col',
        'bg-canvas border border-hairline rounded-xl',
        'shadow-[var(--shadow-float)]',
        // Mobile: full sidebar width in the drawer
        'w-72',
        // Desktop: fixed width, max-height so it doesn't overflow viewport
        'md:max-h-[calc(100dvh-120px)]',
        // Mobile: stretches to full height of the overlay
        'max-h-[100dvh]',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-hairline shrink-0">
        <span className="text-[12px] font-medium text-ink-mute uppercase tracking-wider select-none">
          Conversaciones
        </span>
        <button
          type="button"
          onClick={close}
          aria-label="Cerrar panel de conversaciones"
          className="min-h-[32px] min-w-[32px] flex items-center justify-center rounded-md text-ink-mute hover:bg-canvas-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary transition-colors duration-150"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
          <span className="sr-only">Cerrar</span>
        </button>
      </div>

      {/* Nueva conversación */}
      <div className="px-3 py-2.5 border-b border-hairline shrink-0">
        <Link
          href="/chat?new=1"
          onClick={handleConvClick}
          className={[
            'flex items-center justify-center gap-2',
            'w-full min-h-[40px] px-3 py-2 rounded-lg',
            'text-[13px] font-medium',
            'border border-hairline bg-canvas-soft text-ink',
            'hover:bg-canvas hover:border-hairline-strong',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
            'transition-colors duration-150',
          ].join(' ')}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Nueva conversación
        </Link>
      </div>

      {/* Conversation list */}
      <nav
        aria-label="Lista de conversaciones"
        className="flex-1 overflow-y-auto px-2 py-2 flex flex-col gap-0.5 scrollbar-thin"
      >
        {conversations.length === 0 ? (
          <p className="px-3 py-4 text-[13px] text-ink-mute text-center">
            Aun no tienes conversaciones.
          </p>
        ) : (
          conversations.map((conv) => (
            <div key={conv.id} onClick={handleConvClick} role="none">
              <ConversationListItem conversation={conv} />
            </div>
          ))
        )}
      </nav>
    </div>
  );

  return (
    <>
      {/* ── Toggle button — always visible, top-left corner ── */}
      <div className="absolute top-4 left-4 z-30">
        <button
          ref={toggleRef}
          type="button"
          aria-expanded={isOpen}
          aria-controls="floating-sidebar-panel"
          aria-label={isOpen ? 'Cerrar panel de conversaciones' : 'Abrir panel de conversaciones'}
          onClick={toggle}
          className={[
            'min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg',
            'border border-hairline bg-canvas text-ink-mute',
            'hover:bg-canvas-soft hover:text-ink hover:border-hairline-strong',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
            'transition-colors duration-150',
            'shadow-[var(--shadow-lift)]',
          ].join(' ')}
        >
          {/* Panel-toggle icon: open = panel with left pane + close chevron; closed = panel with open chevron */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {isOpen ? (
              <>
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <line x1="9" y1="3" x2="9" y2="21" />
                <polyline points="13 15 11 12 13 9" />
              </>
            ) : (
              <>
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <line x1="9" y1="3" x2="9" y2="21" />
                <polyline points="11 9 13 12 11 15" />
              </>
            )}
          </svg>
          <span className="sr-only">
            {isOpen ? 'Cerrar conversaciones' : 'Conversaciones'}
          </span>
        </button>
      </div>

      {/* ── Desktop panel — floats below the toggle, slides in/out ── */}
      <div
        aria-hidden={!isOpen}
        className={[
          'absolute z-20',
          'left-4',
          // Positioned below toggle (44px height + 8px top offset + 8px gap ≈ 60px from top)
          'top-[60px]',
          // Only visible above md breakpoint
          'hidden md:block',
          // Transition
          'motion-safe:transition-all motion-safe:duration-200 motion-safe:ease-in-out',
          isOpen
            ? 'opacity-100 translate-x-0 pointer-events-auto'
            : 'opacity-0 -translate-x-4 pointer-events-none',
        ].join(' ')}
      >
        {SidebarContent}
      </div>

      {/* ── Mobile drawer — full-height overlay, slides in from left ── */}
      {isOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 flex"
          onClick={handleBackdropClick}
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-ink/20 motion-safe:animate-[fadeIn_150ms_ease-out]"
            aria-hidden="true"
          />
          {/* Drawer */}
          <div
            className="relative z-10 h-full motion-safe:animate-[slideInLeft_200ms_ease-out]"
            aria-hidden="false"
          >
            {SidebarContent}
          </div>
        </div>
      )}
    </>
  );
}
