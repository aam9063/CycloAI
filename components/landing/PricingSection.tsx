import { LuCheck } from "react-icons/lu";
import Container from "@/components/ui/Container";
import SectionHeading from "@/components/ui/SectionHeading";
import Button from "@/components/ui/Button";

interface PricingTier {
  name: string;
  price: string;
  period: string;
  features: string[];
  cta: string;
  featured?: boolean;
  badge?: string;
}

const tiers: PricingTier[] = [
  {
    name: "FREE",
    price: "0 €",
    period: "/mes",
    features: ["20 mensajes/mes", "Onboarding", "1 plan guardado"],
    cta: "Empezar gratis",
  },
  {
    name: "PRO",
    price: "9,99 €",
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
    price: "19,99 €",
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
  return (
    <section id="precios" className="scroll-mt-20 py-24 bg-canvas">
      <Container>
        <SectionHeading title="Empieza gratis. Escala cuando lo necesites." />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12 items-start">
          {tiers.map((tier) => {
            const featured = tier.featured === true;

            return (
              <div
                key={tier.name}
                className={`rounded-lg p-8 flex flex-col gap-6 ${
                  featured
                    ? "bg-canvas-night text-on-dark shadow-float md:-translate-y-2"
                    : "bg-canvas border border-hairline"
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
                <div className="flex items-baseline gap-1">
                  <span className="display-lg">{tier.price}</span>
                  <span
                    className={`text-[14px] ${featured ? "text-on-dark/60" : "text-ink-mute"}`}
                  >
                    {tier.period}
                  </span>
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
                  href="/login"
                  className="w-full justify-center"
                >
                  {tier.cta}
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
