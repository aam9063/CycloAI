import 'server-only';

import type { SupabaseClient } from '@supabase/supabase-js';
import { ApiError, serverGet, serverPost } from '@/lib/api/server';
import type { ChatProfile } from '@/lib/ai/types';
import type { Conversation } from '@/lib/api/types';

/**
 * Loads the authenticated user's profile row (all fields needed for system prompt).
 * Returns null if no profile row exists yet.
 *
 * NOTE: still backed by Supabase on purpose — the profile fetch feeds the chat
 * route's system-prompt assembly, which is a later migration slice. Everything
 * else in this module now goes through the backend API.
 */
export async function getUserProfile(
  supabase: SupabaseClient,
  userId: string,
): Promise<ChatProfile | null> {
  const { data, error } = await supabase
    .from('profiles')
    .select(
      'id, display_name, objective, weekly_hours, gym_days_per_week, injuries, has_power_meter, target_event, target_event_date, ftp_estimated, strava_connected, ctl, atl, tsb, weekly_volume_km, weekly_volume_hours, avg_days_per_week, last_sync_at',
    )
    .eq('id', userId)
    .single();

  if (error || !data) return null;
  return data as ChatProfile;
}

/**
 * Lists the signed-in athlete's own conversations, most recently active first.
 * Ownership is decided by the backend from the session — the caller never
 * passes a user id. Errors (including 401) propagate to the caller.
 */
export function listConversations(): Promise<Conversation[]> {
  return serverGet<Conversation[]>('/conversations');
}

/**
 * Creates a conversation owned by the signed-in athlete. The backend
 * normalises the title (word-boundary truncation to 60 chars), so callers
 * pass the raw first user message.
 */
export function createConversation(title?: string | null): Promise<Conversation> {
  return serverPost<Conversation>('/conversations', { title: title ?? null });
}

/**
 * Returns the signed-in athlete's conversation, or null when the backend
 * answers 404. Missing and foreign ids are deliberately indistinguishable at
 * the backend (one generic 404) and stay indistinguishable here — callers
 * render a "not found" state and never learn which case happened. A 422
 * (malformed id in the URL) maps to null too, so a typo'd link renders the
 * same "not found" state instead of a 500. All other errors (401, 5xx,
 * network) propagate.
 */
export async function getConversation(
  conversationId: string,
): Promise<Conversation | null> {
  try {
    return await serverGet<Conversation>(`/conversations/${conversationId}`);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
      return null;
    }
    throw err;
  }
}
