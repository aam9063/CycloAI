import Link from "next/link";
import type { ReactNode } from "react";

type ButtonVariant = "primary" | "outline" | "ghost";

interface ButtonProps {
  variant?: ButtonVariant;
  href?: string;
  children: ReactNode;
  className?: string;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-on-primary hover:bg-primary-deep focus-visible:outline-primary",
  outline:
    "bg-canvas text-ink border border-hairline-strong hover:bg-canvas-soft focus-visible:outline-ink",
  ghost:
    "bg-transparent text-ink hover:underline underline-offset-4 focus-visible:outline-ink px-0 py-0 min-h-0",
};

const base =
  "inline-flex items-center justify-center font-medium text-[14px] leading-none rounded-sm px-4 py-2 min-h-[44px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 cursor-pointer";

export default function Button({
  variant = "primary",
  href,
  children,
  className = "",
}: ButtonProps) {
  const classes = `${base} ${variantClasses[variant]} ${className}`.trim();

  if (href) {
    return (
      <Link href={href} className={classes}>
        {children}
      </Link>
    );
  }

  return (
    <button type="button" className={classes}>
      {children}
    </button>
  );
}
