"use client";

import { useEffect, useRef } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  destructive?: boolean;
  pending?: boolean;
}

const FOCUSABLE =
  'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

const buttonBase =
  "inline-flex items-center justify-center font-medium text-[14px] leading-none rounded-sm px-4 py-2 min-h-[44px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed disabled:pointer-events-none";

const cancelClasses = `${buttonBase} bg-canvas text-ink border border-hairline-strong hover:bg-canvas-soft focus-visible:outline-ink`;
const confirmClasses = `${buttonBase} bg-primary text-on-primary hover:bg-primary-deep focus-visible:outline-primary`;

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onClose,
  pending = false,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<Element | null>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  const titleId = "confirm-dialog-title";
  const descId = "confirm-dialog-desc";

  // Body scroll lock + focus management on open
  useEffect(() => {
    if (!open) return;

    // Store current focus to restore on close
    triggerRef.current = document.activeElement;

    // Lock body scroll
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Set initial focus on Cancelar (safe default for destructive dialog)
    const raf = requestAnimationFrame(() => {
      cancelBtnRef.current?.focus();
    });

    return () => {
      document.body.style.overflow = prevOverflow;
      cancelAnimationFrame(raf);
      // Restore focus to the element that opened the dialog
      if (
        triggerRef.current &&
        typeof (triggerRef.current as HTMLElement).focus === "function"
      ) {
        (triggerRef.current as HTMLElement).focus();
      }
    };
  }, [open]);

  // Keyboard handler: Escape + Tab focus trap
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (pending) return; // Locked while in-flight
        onClose();
        return;
      }

      if (e.key === "Tab") {
        const panel = panelRef.current;
        if (!panel) return;

        const focusable = Array.from(
          panel.querySelectorAll<HTMLElement>(FOCUSABLE)
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, pending, onClose]);

  if (!open) return null;

  function handleBackdropClick() {
    if (pending) return; // Locked while in-flight
    onClose();
  }

  function handlePanelClick(e: React.MouseEvent) {
    e.stopPropagation();
  }

  return (
    <div
      role="presentation"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40 motion-safe:transition-opacity"
      onClick={handleBackdropClick}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-[420px] bg-canvas border border-hairline rounded-xl shadow-deep p-6 flex flex-col gap-4 motion-safe:transition-transform"
        onClick={handlePanelClick}
      >
        <h2
          id={titleId}
          className="text-[18px] font-medium text-ink leading-[1.25]"
        >
          {title}
        </h2>

        <p id={descId} className="text-[14px] text-ink-mute leading-[1.5]">
          {description}
        </p>

        <div className="flex justify-end gap-3 pt-2">
          {/* Cancel button — receives initial focus (safe default for destructive dialog) */}
          <button
            ref={cancelBtnRef}
            type="button"
            className={cancelClasses}
            disabled={pending}
            onClick={() => {
              if (!pending) onClose();
            }}
          >
            {cancelLabel}
          </button>

          {/* Confirm button — destructive intent conveyed by copy + dialog gate, not red color */}
          <button
            type="button"
            className={confirmClasses}
            disabled={pending}
            onClick={() => {
              if (!pending) onConfirm();
            }}
          >
            {pending ? "Eliminando..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
