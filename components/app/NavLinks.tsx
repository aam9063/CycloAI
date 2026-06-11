"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/chat", label: "Chat" },
] as const;

export default function NavLinks() {
  const pathname = usePathname();

  return (
    <nav aria-label="Principal">
      <div className="flex items-center gap-6 text-[14px]">
        {links.map(({ href, label }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className={
                isActive
                  ? "text-ink font-medium underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                  : "text-ink-mute hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              }
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
