'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ConversationRow } from '@/lib/ai/types';

interface ConversationListItemProps {
  conversation: ConversationRow;
}

function relativeDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Hoy';
  if (diffDays === 1) return 'Ayer';
  return `Hace ${diffDays} días`;
}

/**
 * Single conversation item in the sidebar list.
 * Active state computed from the current pathname via usePathname().
 */
export default function ConversationListItem({
  conversation,
}: ConversationListItemProps) {
  const pathname = usePathname();
  const isActive =
    pathname === `/chat/${conversation.id}` ||
    // Also matches the /chat index when this is the rendered conversation
    (pathname === '/chat' && false); // index renders-in-place, so only /chat/[id] is truly "active"

  const title = conversation.title ?? 'Sin título';
  const dateLabel = relativeDate(conversation.updated_at);

  return (
    <Link
      href={`/chat/${conversation.id}`}
      aria-current={isActive ? 'page' : undefined}
      className={[
        'flex flex-col gap-0.5 px-3 py-2.5 min-h-[44px] rounded-md text-left',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
        'transition-colors duration-150',
        isActive
          ? 'bg-canvas-soft border border-hairline-strong text-ink'
          : 'text-ink hover:bg-canvas-soft border border-transparent hover:border-hairline',
      ].join(' ')}
    >
      <span className="text-[14px] leading-[1.3] font-medium truncate">
        {title}
      </span>
      <span className="text-[12px] text-ink-mute">{dateLabel}</span>
    </Link>
  );
}
