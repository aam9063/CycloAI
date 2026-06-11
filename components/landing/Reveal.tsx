"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP, ScrollTrigger);

interface RevealProps {
  children: React.ReactNode;
  className?: string;
  /** When true, animate [data-reveal-item] children with stagger instead of the wrapper. */
  stagger?: boolean;
}

/**
 * Reveal — scroll-triggered fade-up wrapper for below-the-fold sections.
 *
 * - RSC-safe: sections passed as `children` remain server-rendered.
 * - All animation creation is inside gsap.matchMedia so reduced-motion
 *   users see fully visible static content (no CSS opacity-0 hiding).
 * - Uses `gsap.from` so the initial hidden state only exists while the
 *   animation is active — no FOUC risk without JS.
 * - `once: true` means each section reveals permanently on first enter.
 */
export default function Reveal({ children, className, stagger = false }: RevealProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const container = containerRef.current;
        if (!container) return;

        if (stagger) {
          // Animate individual [data-reveal-item] children with stagger
          const items = container.querySelectorAll("[data-reveal-item]");
          if (items.length > 0) {
            gsap.from(items, {
              autoAlpha: 0,
              y: 28,
              duration: 0.7,
              ease: "power2.out",
              stagger: 0.1,
              scrollTrigger: {
                trigger: container,
                start: "top 82%",
                once: true,
              },
            });
          } else {
            // Fallback: animate the wrapper if no items found
            gsap.from(container, {
              autoAlpha: 0,
              y: 28,
              duration: 0.7,
              ease: "power2.out",
              scrollTrigger: {
                trigger: container,
                start: "top 82%",
                once: true,
              },
            });
          }
        } else {
          gsap.from(container, {
            autoAlpha: 0,
            y: 28,
            duration: 0.7,
            ease: "power2.out",
            scrollTrigger: {
              trigger: container,
              start: "top 82%",
              once: true,
            },
          });
        }

        // mm cleanup is automatic via matchMedia
      });
    },
    { scope: containerRef }
  );

  return (
    <div ref={containerRef} className={className}>
      {children}
    </div>
  );
}
