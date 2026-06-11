import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import type { UIMessage } from 'ai';
import { createClient } from '@/lib/supabase/server';
import { listConversations } from '@/lib/db/conversations';
import { getConversationHistory } from '@/lib/db/messages';
import type { MessageRow } from '@/lib/ai/types';
import ChatInterface from '@/components/chat/ChatInterface';

export const metadata: Metadata = {
  title: 'Chat — CycloAI',
};

interface ChatPageProps {
  // Next 16 (App Router): searchParams is a Promise — must be awaited
  searchParams: Promise<{ new?: string }>;
}

function mapToUIMessages(rows: MessageRow[]): UIMessage[] {
  return rows.map((row) => ({
    id: row.id,
    role: row.role as 'user' | 'assistant',
    parts: [{ type: 'text' as const, text: row.content }],
    metadata: row.metadata ?? undefined,
  }));
}

export default async function ChatPage({ searchParams }: ChatPageProps) {
  // BUG-2: await searchParams (Next 16 async API) and detect ?new=<unique>.
  // The value is a per-click timestamp (see FloatingSidebar) so it doubles as
  // a React key — consecutive "Nueva conversación" clicks remount ChatInterface.
  const { new: isNew } = await searchParams;
  const forceNew = Boolean(isNew);

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect('/login');
  }

  // When ?new=1 is present, always render the empty/welcome state regardless of
  // existing conversations. This makes "Nueva conversación" actually work (BUG-2).
  if (forceNew) {
    return <ChatInterface key={`new-${isNew}`} initialMessages={[]} />;
  }

  // Render-in-place: load the most-recent conversation if one exists, else welcome state.
  // No redirect to /chat/[id] — avoids double-navigation flash (ADR-5).
  const conversations = await listConversations(supabase, user.id);
  const latest = conversations[0];

  if (latest) {
    const historyRows = await getConversationHistory(supabase, latest.id, 20);
    const initialMessages = mapToUIMessages(historyRows);

    return (
      <ChatInterface
        key={latest.id}
        conversationId={latest.id}
        initialMessages={initialMessages}
      />
    );
  }

  // No conversations yet — render welcome / empty state
  return <ChatInterface key="new-empty" initialMessages={[]} />;
}
