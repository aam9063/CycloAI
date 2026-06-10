import Link from "next/link";

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-hairline">
        <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center px-6 md:px-8">
          {/* Logo only — no navigation, no sign-out (ADR-1: isolated onboarding chrome) */}
          <Link
            href="/"
            className="flex items-center gap-1 text-[16px] font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Cyclo
            <span className="text-primary">AI</span>
          </Link>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
