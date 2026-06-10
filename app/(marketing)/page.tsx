import type { Metadata } from "next";
import HeroSection from "@/components/landing/HeroSection";
import FeaturesSection from "@/components/landing/FeaturesSection";
import PricingSection from "@/components/landing/PricingSection";
import CtaSection from "@/components/landing/CtaSection";

export const metadata: Metadata = {
  alternates: {
    canonical: "/",
  },
};

export default function HomePage() {
  return (
    <>
      <HeroSection />
      <FeaturesSection />
      <PricingSection />
      <CtaSection />
    </>
  );
}
