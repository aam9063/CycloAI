import 'server-only';

import type { SupabaseClient } from '@supabase/supabase-js';
import { truncateTitle } from '@/lib/chat/text';
import type { ChatProfile, ConversationRow } from '@/lib/ai/types';

/**
 * Loads the authenticated user's profile row (all fields needed for system prompt).
 * Returns null if no profile row exists yet.
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
 * Returns the conversation id to use for this turn.
 * - If conversationId is provided, verifies ownership → throws Error('forbidden') on mismatch.
 * - If conversationId is absent, creates a new conversation row and returns its id.
 * Title is set to the first user message content truncated to 60 chars.
 */
export async function getOrCreateConversation(
  supabase: SupabaseClient,
  userId: string,
  conversationId: string | undefined | null,
  firstText: string,
): Promise<string> {
  if (conversationId) {
    const { data, error } = await supabase
      .from('conversations')
      .select('id, user_id')
      .eq('id', conversationId)
      .single();

    if (error || !data) throw new Error('not_found');
    if (data.user_id !== userId) throw new Error('forbidden');
    return data.id as string;
  }

  const title = truncateTitle(firstText, 60);
  const { data, error } = await supabase
    .from('conversations')
    .insert({ user_id: userId, title })
    .select('id')
    .single();

  if (error || !data) throw new Error('insert_failed');
  return data.id as string;
}

/**
 * Returns a conversation row if it belongs to the given user, otherwise null.
 * Used by RSC pages to enforce ownership before rendering.
 */
export async function getConversationOwned(
  supabase: SupabaseClient,
  id: string,
  userId: string,
): Promise<ConversationRow | null> {
  const { data, error } = await supabase
    .from('conversations')
    .select('*')
    .eq('id', id)
    .eq('user_id', userId)
    .single();

  if (error || !data) return null;
  return data as ConversationRow;
}

/**
 * Lists all conversations for the user, most-recently updated first.
 */
export async function listConversations(
  supabase: SupabaseClient,
  userId: string,
): Promise<ConversationRow[]> {
  const { data, error } = await supabase
    .from('conversations')
    .select('*')
    .eq('user_id', userId)
    .order('updated_at', { ascending: false });

  if (error || !data) return [];
  return data as ConversationRow[];
}

/**
 * Bumps updated_at on a conversation (called in onFinish / onAbort after assistant turn).
 */
export async function touchConversation(
  supabase: SupabaseClient,
  id: string,
): Promise<void> {
  await supabase
    .from('conversations')
    .update({ updated_at: new Date().toISOString() })
    .eq('id', id);
}
