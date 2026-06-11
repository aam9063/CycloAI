import type { ReactNode } from "react";
import Link from "next/link";
import Image from "next/image";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-[400px]">
        {/* Logo */}
        <div className="mb-8 flex justify-center">
          <Link
            href="/"
            className="flex items-center rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            aria-label="CycloAI"
          >
            <Image
              src="/img/logo.png"
              alt="CycloAI"
              width={64}
              height={64}
              priority
              className="h-16 w-16"
            />
          </Link>
        </div>

        {/* Card */}
        <div className="w-full rounded-lg border border-hairline bg-canvas p-8 shadow-lift">
          {children}
        </div>
      </div>
    </div>
  );
}
