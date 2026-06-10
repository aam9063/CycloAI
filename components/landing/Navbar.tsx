"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { LuMenu, LuX } from "react-icons/lu";
import Button from "@/components/ui/Button";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const hamburgerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let prev = false;

    function onScroll() {
      const next = window.scrollY > 8;
      if (next !== prev) {
        prev = next;
        setScrolled(next);
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        hamburgerRef.current?.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const navLinks = [
    { href: "#funcionalidades", label: "Funcionalidades" },
    { href: "#precios", label: "Precios" },
  ];

  const scrollClass = scrolled
    ? "bg-white/80 backdrop-blur-md border-b border-hairline"
    : "bg-transparent border-b border-transparent";

  return (
    <nav
      aria-label="Principal"
      className={`sticky top-0 z-50 motion-safe:transition-all motion-safe:duration-200 ${scrollClass}`}
    >
      <div className="mx-auto w-full max-w-[1280px] px-6 md:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link
            href="/"
            className="flex items-center gap-1 font-semibold text-[16px] text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Cyclo
            <span className="text-primary">AI</span>
          </Link>

          {/* Center nav links — desktop only */}
          <div className="hidden md:flex items-center gap-6">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-[14px] text-ink-mute hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                {link.label}
              </a>
            ))}
          </div>

          {/* Right actions — desktop only */}
          <div className="hidden md:flex items-center gap-3">
            <Button variant="ghost" href="/login">
              Iniciar sesión
            </Button>
            <Button variant="primary" href="/login">
              Empezar gratis
            </Button>
          </div>

          {/* Hamburger — mobile only */}
          <button
            ref={hamburgerRef}
            type="button"
            className="md:hidden flex items-center justify-center w-11 h-11 rounded-sm text-ink hover:bg-canvas-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            aria-label={open ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={open}
            aria-controls="mobile-nav-panel"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? (
              <LuX size={20} aria-hidden="true" />
            ) : (
              <LuMenu size={20} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile panel */}
      {open && (
        <div
          id="mobile-nav-panel"
          className="md:hidden border-b border-hairline bg-canvas px-6 py-4 flex flex-col gap-4"
        >
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-[15px] text-ink py-2 hover:text-ink-mute transition-colors"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <div className="flex flex-col gap-3 pt-2 border-t border-hairline">
            <Button variant="outline" href="/login">
              Iniciar sesión
            </Button>
            <Button variant="primary" href="/login">
              Empezar gratis
            </Button>
          </div>
        </div>
      )}
    </nav>
  );
}
