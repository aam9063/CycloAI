import type { UIMessage } from 'ai';

/**
 * Extracts the plain text content from a UIMessage by joining all text parts.
 * Safe to call from both server and client contexts.
 */
export function uiMessageText(msg: UIMessage): string {
  return msg.parts
    .filter((p) => p.type === 'text')
    .map((p) => (p as { type: 'text'; text: string }).text)
    .join('');
}

/**
 * Truncates a string to `max` characters at a word boundary when possible,
 * or hard-cuts at `max` if no word boundary is found within range.
 */
export function truncateTitle(s: string, max: number): string {
  const trimmed = s.trim();
  if (trimmed.length <= max) return trimmed;
  const slice = trimmed.slice(0, max);
  const lastSpace = slice.lastIndexOf(' ');
  return lastSpace > max * 0.6 ? slice.slice(0, lastSpace) : slice;
}
