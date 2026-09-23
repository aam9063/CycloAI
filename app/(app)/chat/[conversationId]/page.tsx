import { notFound, redirect } from 'next/navigation';
import type { UIMessage } from 'ai';
import { createClient } from '@/lib/supabase/server';
import { ApiError } from '@/lib/api/server';
import { getConversation } from '@/lib/db/conversations';
import { getConversationHistory } from '@/lib/db/messages';
import type { Message } from '@/lib/api/types';
import ChatInterface from '@/components/chat/ChatInterface';

interface ConversationPageProps {
  params: Promise<{ conversationId: string }>;
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

export default async function ConversationPage({ params }: ConversationPageProps) {
  const { conversationId } = await params;

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect('/login');
  }

  // The backend already enforces ownership: a missing id and a foreign id are
  // the same generic 404 (getConversation collapses both — plus a malformed
  // id's 422 — into null). Render "not found"; no second ownership check here.
  // A backend 401 (expired/absent API session) is a signed-out visitor — login
  // redirect, same as every other screen behind auth.
  let conversation;
  try {
    conversation = await getConversation(conversationId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect('/login');
    }
    throw err;
  }
  if (!conversation) {
    notFound();
  }

  const historyRows = await getConversationHistory(conversationId);
  const initialMessages = mapToUIMessages(historyRows.slice(-HISTORY_WINDOW));

  return (
    <ChatInterface
      key={conversationId}
      conversationId={conversationId}
      initialMessages={initialMessages}
    />
  );
}
