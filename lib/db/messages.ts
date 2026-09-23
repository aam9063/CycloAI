import 'server-only';

import { serverGet, serverPost } from '@/lib/api/server';
import type { Message, MessageCreate } from '@/lib/api/types';

/**
 * Returns the signed-in athlete's messages for one conversation, oldest
 * first (backend ordering). Unlike the old Supabase helper there is no
 * `limit` parameter — the backend returns every message; callers cap the
 * window themselves (e.g. `.slice(-20)`) if they need the old behaviour.
 * Errors (including 401 and the 404 for an invisible conversation) propagate.
 */
export function getConversationHistory(
  conversationId: string,
): Promise<Message[]> {
  return serverGet<Message[]>(`/conversations/${conversationId}/messages`);
}

/**
 * Appends one message to the signed-in athlete's conversation and returns
 * the stored row. Unlike the old Supabase helpers, failures THROW — nothing
 * is swallowed. Callers decide whether that aborts the turn (route handler)
 * or is logged (stream callbacks).
 */
export function appendMessage(
  conversationId: string,
  message: MessageCreate,
): Promise<Message> {
  return serverPost<Message>(`/conversations/${conversationId}/messages`, message);
}

/** Appends the user's turn. */
export function appendUserMessage(
  conversationId: string,
  content: string,
): Promise<Message> {
  return appendMessage(conversationId, { role: 'user', content });
}

/**
 * Appends the assistant's turn. Guards against empty content — the backend
 * rejects empty messages (422), so a blank stream result is stored as an
 * explicit interrupted-answer marker, exactly like the old helper did.
 */
export function appendAssistantMessage(
  conversationId: string,
  content: string,
  metadata?: Record<string, unknown> | null,
): Promise<Message> {
  const safeContent = content.trim() || '[respuesta interrumpida]';
  return appendMessage(conversationId, {
    role: 'assistant',
    content: safeContent,
    metadata: metadata ?? null,
  });
}
