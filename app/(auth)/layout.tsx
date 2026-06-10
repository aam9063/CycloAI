import type { ReactNode } from "react";
import Link from "next/link";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-[400px]">
        {/* Logo wordmark */}
        <div className="mb-8 flex justify-center">
          <Link
            href="/"
            className="font-semibold text-[18px] text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Cyclo<span className="text-primary">AI</span>
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
