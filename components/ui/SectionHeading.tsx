interface SectionHeadingProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  align?: "left" | "center";
}

export default function SectionHeading({
  eyebrow,
  title,
  subtitle,
  align = "center",
}: SectionHeadingProps) {
  const alignClass = align === "center" ? "text-center mx-auto" : "text-left";

  return (
    <div className={`max-w-2xl ${alignClass}`}>
      {eyebrow && (
        <p className="text-[13px] text-ink-mute mb-3 font-medium uppercase tracking-wider">
          {eyebrow}
        </p>
      )}
      <h2 className={`display-lg text-ink`}>{title}</h2>
      {subtitle && (
        <p className="mt-4 text-[18px] leading-[1.55] text-ink-mute">{subtitle}</p>
      )}
    </div>
  );
}
