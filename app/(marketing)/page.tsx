import type { Metadata } from "next";
import HeroSection from "@/components/landing/HeroSection";
import DemoSection from "@/components/landing/DemoSection";
import HowItWorksSection from "@/components/landing/HowItWorksSection";
import FeaturesSection from "@/components/landing/FeaturesSection";
import PricingSection from "@/components/landing/PricingSection";
import FaqSection from "@/components/landing/FaqSection";
import CtaSection from "@/components/landing/CtaSection";
import Reveal from "@/components/landing/Reveal";

export const metadata: Metadata = {
  alternates: {
    canonical: "/",
  },
};

export default function HomePage() {
  return (
    <>
      {/* Hero: entrance handled by HeroIntro (on-load, not scroll) */}
      <HeroSection />

      {/* Below-the-fold sections: scroll-triggered fade-up via Reveal */}
      <Reveal>
        <DemoSection />
      </Reveal>

      <Reveal stagger>
        <HowItWorksSection />
      </Reveal>

      <Reveal stagger>
        <FeaturesSection />
      </Reveal>

      <Reveal stagger>
        <PricingSection />
      </Reveal>

      <Reveal stagger>
        <FaqSection />
      </Reveal>

      <Reveal>
        <CtaSection />
      </Reveal>
    </>
  );
}
