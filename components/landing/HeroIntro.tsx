"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

interface HeroIntroProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * HeroIntro — on-load staggered entrance for the hero section.
 *
 * Expects two direct structural zones inside `children`:
 *   - Elements with [data-hero-item]: eyebrow, h1, paragraph, CTA row
 *     → fade up from {autoAlpha:0, y:18}, stagger 0.1
 *   - An element with [data-hero-phone]: the outer wrapper of the iPhone column
 *     → fade up from {autoAlpha:0, y:30, scale:0.97}, starts after last hero item
 *
 * IMPORTANT — transform safety:
 *   [data-hero-phone] must wrap the perspective-container div, NOT the
 *   element that carries the CSS rotateY/rotateX classes. That way GSAP
 *   animates y + scale on the outer wrapper while the inner CSS 3D
 *   transform is untouched.
 *
 * All animation creation is inside gsap.matchMedia so reduced-motion
 * users see fully visible static content with no FOUC.
 */
export default function HeroIntro({ children, className }: HeroIntroProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const container = containerRef.current;
        if (!container) return;

        const heroItems = container.querySelectorAll("[data-hero-item]");
        const phoneEl = container.querySelector("[data-hero-phone]");

        const tl = gsap.timeline({ defaults: { ease: "power2.out" } });

        if (heroItems.length > 0) {
          tl.from(heroItems, {
            autoAlpha: 0,
            y: 18,
            duration: 0.65,
            stagger: 0.1,
          });
        }

        if (phoneEl) {
          // Offset by 0.15s from where the last hero item starts (overlapping feel)
          tl.from(
            phoneEl,
            {
              autoAlpha: 0,
              y: 30,
              scale: 0.97,
              duration: 0.75,
            },
            heroItems.length > 0 ? "-=0.35" : 0
          );
        }
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
