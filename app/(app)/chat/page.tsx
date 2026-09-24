import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import type { UIMessage } from 'ai';
import { ApiError } from '@/lib/api/server';
import { listConversations } from '@/lib/db/conversations';
import { getConversationHistory } from '@/lib/db/messages';
import type { Message } from '@/lib/api/types';
import ChatInterface from '@/components/chat/ChatInterface';

export const metadata: Metadata = {
  title: 'Chat — CycloAI',
};

interface ChatPageProps {
  // Next 16 (App Router): searchParams is a Promise — must be awaited
  searchParams: Promise<{ new?: string }>;
}

// The backend returns every message; the UI seeds with the last 20, as before.
const HISTORY_WINDOW = 20;

function mapToUIMessages(rows: Message[]): UIMessage[] {
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

  // When ?new=1 is present, always render the empty/welcome state regardless of
  // existing conversations. This makes "Nueva conversación" actually work (BUG-2).
  if (forceNew) {
    return <ChatInterface key={`new-${isNew}`} initialMessages={[]} />;
  }

  // Render-in-place: load the most-recent conversation if one exists, else welcome state.
  // No redirect to /chat/[id] — avoids double-navigation flash (ADR-5).
  // A backend 401 (expired/absent API session) is a signed-out visitor — login redirect.
  // The middleware gates on cookie presence; the backend validates the session here.
  let conversations;
  try {
    conversations = await listConversations();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect('/login');
    }
    throw err;
  }
  const latest = conversations[0];

  if (latest) {
    const historyRows = await getConversationHistory(latest.id);
    const initialMessages = mapToUIMessages(historyRows.slice(-HISTORY_WINDOW));

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
