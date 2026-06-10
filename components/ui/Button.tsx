import Link from "next/link";
import type { ReactNode } from "react";

type ButtonVariant = "primary" | "outline" | "ghost";

interface ButtonProps {
  variant?: ButtonVariant;
  href?: string;
  /** Applies only to the <button> branch (when no href is provided). Default: "button". */
  type?: "button" | "submit" | "reset";
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  disabled?: boolean;
  /** Accessible name — use when the button has no visible text label. */
  "aria-label"?: string;
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
  "inline-flex items-center justify-center font-medium text-[14px] leading-none rounded-sm px-4 py-2 min-h-[44px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed disabled:pointer-events-none";

export default function Button({
  variant = "primary",
  href,
  type = "button",
  onClick,
  disabled,
  "aria-label": ariaLabel,
  children,
  className = "",
}: ButtonProps) {
  const classes = `${base} ${variantClasses[variant]} ${className}`.trim();

  if (href) {
    return (
      <Link href={href} className={classes} aria-label={ariaLabel}>
        {children}
      </Link>
    );
  }

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={classes}
    >
      {children}
    </button>
  );
}
