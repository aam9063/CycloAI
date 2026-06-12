"use client";

import { useState } from "react";
import { LuCheck } from "react-icons/lu";
import Container from "@/components/ui/Container";
import SectionHeading from "@/components/ui/SectionHeading";
import Button from "@/components/ui/Button";

type BillingCycle = "monthly" | "annual";

interface PricingTier {
  name: string;
  monthlyPrice: string;
  annualPrice: string | null;
  annualCaption: string | null;
  period: string;
  features: string[];
  cta: string;
  featured?: boolean;
  badge?: string;
}

const tiers: PricingTier[] = [
  {
    name: "FREE",
    monthlyPrice: "0 €",
    annualPrice: "0 €",
    annualCaption: null,
    period: "/mes",
    features: ["20 mensajes/mes", "Onboarding", "1 plan guardado"],
    cta: "Empezar gratis",
  },
  {
    name: "PRO",
    monthlyPrice: "5 €",
    annualPrice: "3,75 €",
    annualCaption: "Facturado anualmente (45 €)",
    period: "/mes",
    features: [
      "Mensajes ilimitados",
      "Sync Strava",
      "Planes ilimitados",
      "Nutrición",
      "Dashboard CTL",
    ],
    cta: "Empezar con Pro",
    featured: true,
    badge: "Recomendado",
  },
  {
    name: "PREMIUM",
    monthlyPrice: "9,99 €",
    annualPrice: "5,83 €",
    annualCaption: "Facturado anualmente (70 €)",
    period: "/mes",
    features: [
      "Todo de Pro +",
      "Exportar PDF",
      "Análisis avanzado",
      "Soporte prioritario",
    ],
    cta: "Empezar Premium",
  },
];

export default function PricingSection() {
  const [billing, setBilling] = useState<BillingCycle>("monthly");

  return (
    <section id="precios" className="scroll-mt-20 py-24 bg-canvas">
      <Container>
        <SectionHeading title="Empieza gratis. Escala cuando lo necesites." />

        {/* Billing cycle toggle */}
        <div
          role="tablist"
          aria-label="Ciclo de facturación"
          className="flex items-center justify-center gap-1 mt-8 p-1 bg-canvas-soft border border-hairline rounded-sm w-fit mx-auto"
        >
          <button
            role="tab"
            aria-selected={billing === "monthly"}
            aria-controls="pricing-cards"
            onClick={() => setBilling("monthly")}
            className={`
              cursor-pointer text-[13px] font-medium px-4 py-1.5 rounded-[4px]
              motion-safe:transition-colors motion-safe:duration-150
              focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink
              ${
                billing === "monthly"
                  ? "bg-primary text-on-primary shadow-lift"
                  : "text-ink-mute hover:text-ink"
              }
            `}
          >
            Mensual
          </button>
          <button
            role="tab"
            aria-selected={billing === "annual"}
            aria-controls="pricing-cards"
            onClick={() => setBilling("annual")}
            className={`
              flex cursor-pointer items-center gap-2 text-[13px] font-medium px-4 py-1.5 rounded-[4px]
              motion-safe:transition-colors motion-safe:duration-150
              focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink
              ${
                billing === "annual"
                  ? "bg-primary text-on-primary shadow-lift"
                  : "text-ink-mute hover:text-ink"
              }
            `}
          >
            Anual
            {/* Savings pill — adapts to active (on green) vs inactive state */}
            <span
              className={`text-[11px] font-medium rounded-full px-1.5 py-0.5 leading-none border ${
                billing === "annual"
                  ? "bg-on-primary/15 border-on-primary/25 text-on-primary"
                  : "bg-canvas-soft border-hairline text-ink-mute"
              }`}
            >
              Ahorra hasta un 40%
            </span>
          </button>
        </div>

        <div
          id="pricing-cards"
          className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-6 mt-10 items-start"
        >
          {tiers.map((tier) => {
            const featured = tier.featured === true;
            const displayPrice =
              billing === "annual" && tier.annualPrice
                ? tier.annualPrice
                : tier.monthlyPrice;
            const caption =
              billing === "annual" ? tier.annualCaption : null;

            return (
              <div
                key={tier.name}
                data-reveal-item
                className={`rounded-lg p-8 flex flex-col gap-6 motion-safe:transition-[transform,box-shadow,border-color] motion-safe:duration-200 motion-safe:ease-out ${
                  featured
                    ? "bg-canvas-night text-on-dark shadow-float md:-mt-2 hover:shadow-deep"
                    : "bg-canvas border border-hairline hover:border-hairline-strong hover:shadow-float motion-safe:hover:-translate-y-1"
                }`}
              >
                {/* Tier label + badge */}
                <div className="flex items-center justify-between">
                  <h3
                    className={`text-[13px] font-medium tracking-widest uppercase ${
                      featured ? "text-on-dark/70" : "text-ink-mute"
                    }`}
                  >
                    {tier.name}
                  </h3>
                  {tier.badge && (
                    <span className="bg-primary text-on-primary text-[12px] font-medium rounded-full px-2 py-0.5">
                      {tier.badge}
                    </span>
                  )}
                </div>

                {/* Price */}
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-baseline gap-1">
                    <span
                      className={`display-lg motion-safe:transition-all motion-safe:duration-200 ${featured ? "text-on-dark" : "text-ink"}`}
                    >
                      {displayPrice}
                    </span>
                    <span
                      className={`text-[14px] ${featured ? "text-on-dark/60" : "text-ink-mute"}`}
                    >
                      {tier.period}
                    </span>
                  </div>
                  {caption && (
                    <p
                      className={`text-[12px] motion-safe:transition-opacity motion-safe:duration-200 ${
                        featured ? "text-on-dark/50" : "text-ink-faint"
                      }`}
                    >
                      {caption}
                    </p>
                  )}
                  {/* Reserve space when no caption to keep cards aligned */}
                  {!caption && (
                    <p className="text-[12px] text-transparent select-none" aria-hidden="true">
                      &nbsp;
                    </p>
                  )}
                </div>

                {/* Features list */}
                <ul className="flex flex-col gap-3 flex-1">
                  {tier.features.map((feat) => (
                    <li key={feat} className="flex items-start gap-2.5">
                      <LuCheck
                        size={15}
                        className={`mt-0.5 shrink-0 ${featured ? "text-primary" : "text-primary-deep"}`}
                        aria-hidden="true"
                      />
                      <span
                        className={`text-[14px] leading-[1.5] ${
                          featured ? "text-on-dark/80" : "text-ink-mute"
                        }`}
                      >
                        {feat}
                      </span>
                    </li>
                  ))}
                </ul>

                {/* CTA */}
                <Button
                  variant={featured ? "primary" : "outline"}
                  href="/#waitlist"
                  className="w-full justify-center"
                >
                  Unirme a la lista
                </Button>
              </div>
            );
          })}
        </div>

        <p className="text-center text-[13px] text-ink-mute mt-8">
          Sin permanencia. Cancela cuando quieras.
        </p>
      </Container>
    </section>
  );
}
