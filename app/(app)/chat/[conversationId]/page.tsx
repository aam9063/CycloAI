import { notFound } from 'next/navigation';
import type { UIMessage } from 'ai';
import { createClient } from '@/lib/supabase/server';
import { getConversationOwned } from '@/lib/db/conversations';
import { getConversationHistory } from '@/lib/db/messages';
import type { MessageRow } from '@/lib/ai/types';
import ChatInterface from '@/components/chat/ChatInterface';

interface ConversationPageProps {
  params: Promise<{ conversationId: string }>;
}

function mapToUIMessages(rows: MessageRow[]): UIMessage[] {
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
    notFound();
  }

  // Ownership check — 404 on miss or unauthorized (no data leak)
  const conversation = await getConversationOwned(supabase, conversationId, user.id);
  if (!conversation) {
    notFound();
  }

  const historyRows = await getConversationHistory(supabase, conversationId, 20);
  const initialMessages = mapToUIMessages(historyRows);

  return (
    <ChatInterface
      conversationId={conversationId}
      initialMessages={initialMessages}
    />
  );
}
