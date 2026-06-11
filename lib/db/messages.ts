import 'server-only';

import type { SupabaseClient } from '@supabase/supabase-js';
import type { MessageRow } from '@/lib/ai/types';

/** Persists the user's turn BEFORE the stream starts (durability on stream failure). */
export async function insertUserMessage(
  supabase: SupabaseClient,
  {
    conversationId,
    userId,
    content,
  }: { conversationId: string; userId: string; content: string },
): Promise<void> {
  await supabase.from('messages').insert({
    conversation_id: conversationId,
    user_id: userId,
    role: 'user',
    content,
  });
}

/**
 * Persists the assistant's turn in onFinish.
 * Guards against empty content: substitutes '[respuesta interrumpida]' if text is empty.
 */
export async function insertAssistantMessage(
  supabase: SupabaseClient,
  {
    conversationId,
    userId,
    content,
    metadata,
  }: {
    conversationId: string;
    userId: string;
    content: string;
    metadata?: Record<string, unknown> | null;
  },
): Promise<void> {
  const safeContent = content.trim() || '[respuesta interrumpida]';
  await supabase.from('messages').insert({
    conversation_id: conversationId,
    user_id: userId,
    role: 'assistant',
    content: safeContent,
    metadata: metadata ?? null,
  });
}

/**
 * Returns the last `limit` messages for a conversation in chronological order.
 * Used to seed the model's context window and the UI's initialMessages.
 */
export async function getConversationHistory(
  supabase: SupabaseClient,
  conversationId: string,
  limit: number,
): Promise<MessageRow[]> {
  // Fetch most-recent N, then reverse to chronological order for the model.
  const { data, error } = await supabase
    .from('messages')
    .select('*')
    .eq('conversation_id', conversationId)
    .order('created_at', { ascending: false })
    .limit(limit);

  if (error || !data) return [];
  return (data as MessageRow[]).reverse();
}
