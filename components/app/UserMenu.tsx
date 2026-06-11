'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import InitialsAvatar from '@/components/profile/InitialsAvatar';
import { signOutAction } from '@/app/(app)/actions';

interface UserMenuProps {
  displayName: string | null;
}

export default function UserMenu({ displayName }: UserMenuProps) {
  // Initial state must be deterministic (closed) for SSR/hydration safety.
  // Never read browser APIs during initializer — see FloatingSidebar hydration lesson.
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();

  const close = useCallback(() => {
    setIsOpen(false);
    triggerRef.current?.focus();
  }, []);

  const toggle = useCallback(() => setIsOpen((v) => !v), []);

  // Close on route change (e.g., "Mi perfil" link navigated away).
  // Bounded setState on external signal (route change) — intentional pattern.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsOpen(false);
  }, [pathname]);

  // Close on Escape; keyboard navigation (ArrowUp/Down, Tab) within menu
  useEffect(() => {
    if (!isOpen) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }

      // Arrow navigation between menu items
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const items = menuRef.current?.querySelectorAll<HTMLElement>(
          '[role="menuitem"]',
        );
        if (!items || items.length === 0) return;
        const focused = document.activeElement;
        const idx = Array.from(items).indexOf(focused as HTMLElement);
        if (e.key === 'ArrowDown') {
          const next = items[(idx + 1) % items.length];
          next?.focus();
        } else {
          const prev = items[(idx - 1 + items.length) % items.length];
          prev?.focus();
        }
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, close]);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;

    const handler = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [isOpen]);

  // Focus first menu item when opened via keyboard or click
  useEffect(() => {
    if (!isOpen) return;
    // Small defer so the panel renders before we attempt focus
    const id = setTimeout(() => {
      const first = menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]');
      first?.focus();
    }, 10);
    return () => clearTimeout(id);
  }, [isOpen]);

  return (
    <div className="relative">
      {/* Avatar trigger button */}
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Menú de usuario"
        className={[
          'min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
          'transition-opacity duration-150',
          isOpen ? 'opacity-80' : 'hover:opacity-80',
        ].join(' ')}
      >
        <InitialsAvatar name={displayName} size={36} />
      </button>

      {/* Dropdown panel */}
      {isOpen && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Menú de usuario"
          className={[
            'absolute right-0 top-full mt-2 z-50',
            'w-48',
            'bg-canvas border border-hairline rounded-lg',
            'shadow-[var(--shadow-float)]',
            'py-1',
            'motion-safe:animate-[menuIn_120ms_ease-out]',
          ].join(' ')}
        >
          {/* Mi perfil */}
          <Link
            href="/profile"
            role="menuitem"
            onClick={close}
            className={[
              'flex items-center gap-2.5 w-full px-3.5 py-2.5',
              'text-[13px] text-ink',
              'hover:bg-canvas-soft',
              'focus-visible:outline-none focus-visible:bg-canvas-soft',
              'transition-colors duration-100',
            ].join(' ')}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="8" r="4" />
              <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
            </svg>
            Mi perfil
          </Link>

          {/* Hairline separator */}
          <div role="separator" className="my-1 border-t border-hairline" />

          {/* Cerrar sesión */}
          <form action={signOutAction}>
            <button
              type="submit"
              role="menuitem"
              className={[
                'flex items-center gap-2.5 w-full px-3.5 py-2.5',
                'text-[13px] text-ink',
                'hover:bg-canvas-soft',
                'focus-visible:outline-none focus-visible:bg-canvas-soft',
                'transition-colors duration-100',
                'text-left',
              ].join(' ')}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              Cerrar sesión
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
