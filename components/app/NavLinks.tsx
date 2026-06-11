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
      <div className="flex items-center gap-2 text-[14px]">
        {links.map(({ href, label }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className={
                isActive
                  ? "rounded-full bg-canvas-soft px-3 py-1.5 text-ink font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                  : "rounded-full px-3 py-1.5 text-ink-mute hover:text-ink hover:bg-canvas-soft/60 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
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
