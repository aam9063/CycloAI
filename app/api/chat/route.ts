import 'server-only';

import { google } from '@ai-sdk/google';
import { streamText, convertToModelMessages, type UIMessage } from 'ai';
import { createClient } from '@/lib/supabase/server';
import { appendUserMessage, appendAssistantMessage } from '@/lib/db/messages';
import { ApiError, serverPost } from '@/lib/api/server';
import type { ChatContextResponse } from '@/lib/api/types';
import { getClientIp, checkRateLimit } from '@/lib/utils/ratelimit';
import { uiMessageText } from '@/lib/chat/text';

export const runtime = 'nodejs'; // Supabase SSR cookie client requires Node runtime
export const maxDuration = 60;  // Vercel Hobby hard cap (60 s); guards long Gemini streams

export async function POST(req: Request) {
  // 1. Auth — verify Supabase session cookie
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return new Response('No autorizado', { status: 401 });
  }

  // 2. Per-user chat rate limit — checked before any expensive work.
  // Uses user.id (authenticated) so each account has its own budget regardless of IP.
  const ip = await getClientIp();
  const chatRl = await checkRateLimit({ key: `chat:${user.id}:${ip}`, limit: 15, windowSeconds: 60 });
  if (!chatRl.success) {
    return new Response('429: Demasiados mensajes. Espera un momento.', { status: 429 });
  }

  // 3. Parse request body
  const { messages, conversationId } = (await req.json()) as {
    messages: UIMessage[];
    conversationId?: string | null;
  };

  if (!messages || messages.length === 0) {
    return new Response('Solicitud inválida', { status: 400 });
  }

  // Server-side payload size guards — prevent oversized requests from reaching RAG/stream.
  // Total payload: ~100 KB cap (cheap serialisation check).
  if (JSON.stringify(messages).length > 100_000) {
    return new Response('Solicitud demasiado grande.', { status: 400 });
  }

  // 4. Assemble the turn's context via the backend (POST /chat/context).
  // The backend builds the system prompt from the athlete's REAL profile plus
  // knowledge-base retrieval, and resolves or creates the conversation (owner-
  // checked; a missing id and a foreign id are the same generic 404). The
  // response shape is `ChatContextResponse` (lib/api/types.ts), mirroring
  // backend ChatContextOut (routes_chat.py).

  const lastUserMessage = messages[messages.length - 1];
  const lastText = uiMessageText(lastUserMessage);

  // Per-message length cap: 8 000 chars is well above any reasonable user input.
  if (lastText.length > 8_000) {
    return new Response('Mensaje demasiado largo.', { status: 400 });
  }

  let convId: string;
  let systemPrompt: string;
  try {
    const context = await serverPost<ChatContextResponse>('/chat/context', {
      message: lastText,
      conversation_id: conversationId ?? null,
    });
    convId = context.conversation_id;
    systemPrompt = context.system_prompt;
  } catch (err) {
    if (err instanceof ApiError) {
      // 401: unauthenticated backend session — same response as the route's
      // other auth failures. 404: missing or foreign conversation, the same
      // generic 404 the route already produced for a missing conversation.
      if (err.status === 401) {
        return new Response('No autorizado', { status: 401 });
      }
      if (err.status === 404) {
        return new Response('Conversación no encontrada', { status: 404 });
      }
    }
    throw err;
  }

  // 6. Persist user message BEFORE streaming (durability if stream fails).
  // Unlike the old Supabase insert (errors swallowed), a failed save now fails
  // the request loudly — the client sees an error instead of silently losing
  // the turn from history.
  try {
    await appendUserMessage(convId, lastText);
  } catch (err) {
    console.error('[chat] failed to persist user message:', err);
    return new Response('Error interno', { status: 500 });
  }

  // 7. The system prompt came from the backend context call above (step 4):
  // built from the athlete's real profile plus knowledge retrieval, with
  // `knowledge_used` reporting whether retrieval contributed anything.

  // 8. Stream via Gemini 3.5 Flash
  const modelMessages = await convertToModelMessages(messages);

  // W-1 fix: guard against double-insert when both onAbort and onFinish fire on user stop.
  // onAbort fires first (partial text); we set this flag so onFinish skips its insert.
  let persistedByAbort = false;

  // W-2 fix: track whether a mid-stream error is a rate-limit so the stream error
  // chunk carries the right copy to the client. streamText's onError fires for errors
  // that surface inside the stream (e.g. mid-stream Gemini 429s — HTTP 200 body errors).
  // We set a flag here; toUIMessageStreamResponse's onError reads it to return the
  // appropriate string, which becomes error.message in useChat on the client.
  let midStreamIs429 = false;

  // Model is env-overridable: when gemini-3.5-flash hits capacity throttling
  // ("high demand" errors on the free tier), set GEMINI_CHAT_MODEL=gemini-3.1-flash
  // in .env to switch to the stable workhorse without a code change.
  const chatModel = process.env.GEMINI_CHAT_MODEL ?? 'gemini-3.5-flash';

  let result;
  try {
    result = streamText({
      model: google(chatModel),
      system: systemPrompt,
      messages: modelMessages,
      // Gemini 3.5 Flash is a reasoning model: its internal thinking tokens consume
      // the same output budget. 2048 left only a few hundred tokens of visible text
      // (responses cut mid-sentence with finishReason 'length'). 8192 fits full
      // weekly plans; thinkingLevel 'low' keeps latency and token burn down.
      maxOutputTokens: 8192,
      // Free tier: the SDK's default 3 internal retries burn quota against
      // rate-limit walls within seconds (windows reset per minute). One retry max.
      maxRetries: 1,
      providerOptions: {
        google: {
          // thinkingLevel is a Gemini 3.x-only option; 2.5 models use the numeric
          // thinkingBudget (0 = thinking disabled — full output budget goes to text).
          thinkingConfig: chatModel.startsWith('gemini-3')
            ? { thinkingLevel: 'low' }
            : { thinkingBudget: 0 },
        },
      },
      abortSignal: req.signal,  // propagates client stop() / disconnects
      onError: ({ error }) => {
        // Fires for errors that surface inside the stream (mid-stream provider errors).
        // Mark 429s so toUIMessageStreamResponse can embed the right error copy.
        const msg = error instanceof Error ? error.message : String(error);
        // BUG-1a: log provider errors so dev/server logs show failures (no secrets — only message text)
        console.error('[chat] mid-stream provider error:', msg);
        const lower = msg.toLowerCase();
        // Saturation family: hard 429s, quota, AND Google's capacity throttling
        // ("high demand" / overloaded / unavailable) — all map to the retryable copy.
        if (
          lower.includes('429') ||
          lower.includes('rate limit') ||
          lower.includes('quota') ||
          lower.includes('high demand') ||
          lower.includes('overloaded') ||
          lower.includes('resource_exhausted') ||
          lower.includes('unavailable')
        ) {
          midStreamIs429 = true;
        }
      },
      onFinish: async ({ text, finishReason }) => {
        // W-1 fix: if onAbort already persisted a row, skip this insert.
        if (persistedByAbort) return;
        const isAborted = finishReason !== 'stop' && finishReason !== 'length';
        // Append bumps updated_at server-side, so the old touchConversation call
        // is gone. A failed save is logged, not swallowed silently, and cannot
        // crash the stream response this late.
        try {
          await appendAssistantMessage(convId, text, isAborted
            ? { aborted: true, finishReason }
            : { finishReason });
        } catch (err) {
          console.error('[chat] failed to persist assistant message:', err);
        }
      },
      onAbort: async ({ steps }) => {
        // Fires when abortSignal fires (user stop / client disconnect) mid-stream.
        // Accumulate partial text from all steps so far.
        const partial = steps
          .map((s) => s.text ?? '')
          .join('');
        persistedByAbort = true; // W-1: signal onFinish to skip its insert
        // Append bumps updated_at server-side, so the old touchConversation call
        // is gone. A failed save is logged, not swallowed silently.
        try {
          await appendAssistantMessage(convId, partial, { aborted: true }); // SG-1: spec says { aborted: true }
        } catch (err) {
          console.error('[chat] failed to persist aborted assistant message:', err);
        }
      },
    });
  } catch (err) {
    // Catch 429 rate-limit from Gemini before streaming starts (synchronous/config errors)
    const errorMessage = err instanceof Error ? err.message : String(err);
    // BUG-1a: log pre-stream errors so server logs show provider failures (no secrets)
    console.error('[chat] pre-stream error:', errorMessage);
    if (errorMessage.includes('429') || errorMessage.toLowerCase().includes('rate')) {
      // BUG-1b: body text includes '429' so the client-side '429:' prefix check matches
      return new Response('429: Rate limit', { status: 429 });
    }
    return new Response('Error del asistente', { status: 500 });
  }

  // 9. Return streaming response with the conversation id in a response header.
  // W-2 fix: toUIMessageStreamResponse's onError embeds the error message into the
  // UI message stream protocol. The client's useChat surfaces it as error.message,
  // which ChatInterface.tsx already inspects for '429' to pick the right Spanish copy.
  // Mechanism: streamText.onError sets midStreamIs429 → toUIMessageStreamResponse.onError
  // returns a string containing '429' → useChat.error.message contains '429' → client
  // shows "El asistente está saturado. Inténtalo de nuevo en un momento."
  //
  // Continue-on-cut: attach finishReason to the UI message metadata so the client
  // can show a "Continuar" affordance when the stream ends abnormally.
  // The messageMetadata callback fires on 'start' and 'finish' parts; we only act
  // on 'finish' where part.finishReason is defined.
  return result.toUIMessageStreamResponse({
    headers: {
      'X-Conversation-Id': convId,
    },
    messageMetadata: ({ part }) => {
      if (part.type === 'finish' && part.finishReason) {
        return { finishReason: part.finishReason } as Record<string, unknown>;
      }
      return undefined;
    },
    onError: (error) => {
      const msg = error instanceof Error ? error.message : String(error);
      if (midStreamIs429 || msg.includes('429') || msg.toLowerCase().includes('rate limit') || msg.toLowerCase().includes('quota')) {
        return '429: El asistente está saturado.';
      }
      return 'Error del asistente';
    },
  });
}
