'use client';

import Link from 'next/link';
import type { ConversationRow } from '@/lib/ai/types';
import ConversationListItem from './ConversationListItem';

interface ConversationListProps {
  conversations: ConversationRow[];
}

/**
 * Sidebar conversation list with "Nueva conversación" action.
 * Passed as a prop from the RSC layout (data fetched server-side).
 * BUG-2: "Nueva conversación" navigates to /chat?new=1 so the RSC can detect it
 * and render the empty/welcome state even when conversations exist.
 */
export default function ConversationList({ conversations }: ConversationListProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-3 border-b border-hairline shrink-0">
        <Link
          href="/chat?new=1"
          className={[
            'block w-full min-h-[44px] px-3 py-2 rounded-md text-[14px] font-medium text-center',
            'border border-hairline bg-canvas text-ink',
            'hover:bg-canvas-soft hover:border-hairline-strong',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
            'transition-colors duration-150',
          ].join(' ')}
        >
          Nueva conversación
        </Link>
      </div>

      {/* Conversation list */}
      <nav aria-label="Conversaciones" className="flex-1 overflow-y-auto px-2 py-2 flex flex-col gap-1">
        {conversations.length === 0 ? null : (
          conversations.map((conv) => (
            <ConversationListItem key={conv.id} conversation={conv} />
          ))
        )}
      </nav>
    </div>
  );
}
