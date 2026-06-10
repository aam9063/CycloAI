import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Onboarding — CycloAI",
};

export default function OnboardingPage() {
  return (
    <section className="flex min-h-[60vh] items-center justify-center px-6">
      <div className="w-full max-w-[400px] rounded-lg border border-hairline bg-canvas p-8 text-center">
        <h1 className="display-md text-ink mb-3">Onboarding</h1>
        <p className="text-[15px] leading-[1.5] text-ink-mute">
          El onboarding conversacional estará disponible muy pronto.
        </p>
      </div>
    </section>
  );
}
