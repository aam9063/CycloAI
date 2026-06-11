interface InitialsAvatarProps {
  name: string | null;
  size?: number;
}

function getInitial(name: string | null): string {
  if (!name) return "?";
  // Get the first non-whitespace character and uppercase it
  const char = name.trim()[0];
  return char ? char.toUpperCase() : "?";
}

export default function InitialsAvatar({ name, size = 48 }: InitialsAvatarProps) {
  const initial = getInitial(name);

  return (
    // aria-hidden: the display_name is shown as visible text adjacent to this avatar,
    // so the decorative badge does not need to be read by screen readers.
    <div
      aria-hidden="true"
      className="rounded-full bg-canvas-night text-on-dark flex items-center justify-center font-medium flex-shrink-0"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {initial}
    </div>
  );
}
