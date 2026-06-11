/**
 * Verified AI SDK v6 contracts (ai@6.0.201, @ai-sdk/google@3.0.80, @ai-sdk/react@3.0.203)
 *
 * CONTRACT VERIFICATION RESULTS:
 * - streamText option name: `maxOutputTokens` (NOT maxTokens — v4/v5 name)
 * - onAbort: EXISTS in streamText (type StreamTextOnAbortCallback)
 * - onFinish payload: OnFinishEvent extends StepResult → has { text: string, finishReason, steps, ... }
 * - toUIMessageStreamResponse: EXISTS, accepts ResponseInit (which includes headers?: HeadersInit)
 * - DefaultChatTransport: in 'ai', options { api, body: Resolvable<object>, fetch, headers, credentials }
 * - useChat: NOT in 'ai' — must import from '@ai-sdk/react'
 * - useChat helpers: { messages, sendMessage, status, stop, regenerate, setMessages, error, clearError }
 * - status values: 'submitted' | 'streaming' | 'ready' | 'error'
 * - UIMessage: { id, role, parts: UIMessagePart[], metadata? }
 * - UIMessagePart text: { type: 'text', text: string, state?: 'streaming'|'done' }
 * - Model id: 'gemini-3.5-flash' — confirmed in GoogleGenerativeAIModelId union
 * - convertToModelMessages: EXISTS in 'ai'
 * - X-Conversation-Id header: read client-side via custom fetch wrapper on DefaultChatTransport
 * - body as function: Resolvable<object> supports () => object (function form)
 *
 * DEVIATIONS FROM DESIGN:
 * - Design used sendMessage({ text }); v6 useChat.sendMessage() matches — no deviation
 * - Design mentioned onAbort({ steps }); actual type: { steps: StepResult[] } — matches
 * - @ai-sdk/react was not in original dep list but IS required for useChat (added as explicit dep)
 */

/** Subset of the profiles table row used by the chat system prompt builder. */
export interface ChatProfile {
  id: string;
  display_name: string | null;
  objective: string | null;
  weekly_hours: number | null;
  gym_days_per_week: number | null;
  injuries: string | null;
  has_power_meter: boolean | null;
  target_event: string | null;
  target_event_date: string | null;
  ftp_estimated: number | null;
  strava_connected: boolean | null;
  ctl: number | null;
  atl: number | null;
  tsb: number | null;
  weekly_volume_km: number | null;
  weekly_volume_hours: number | null;
  avg_days_per_week: number | null;
  last_sync_at: string | null;
}

/** Matches the conversations table row exactly. */
export interface ConversationRow {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  title: string | null;
  summary: string | null;
}

/** Matches the messages table row exactly. */
export interface MessageRow {
  id: string;
  conversation_id: string;
  user_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  metadata: Record<string, unknown> | null;
}
