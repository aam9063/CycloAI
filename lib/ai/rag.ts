import 'server-only';

import { google } from '@ai-sdk/google';
import { embed } from 'ai';
import { createClient } from '@/lib/supabase/server';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// LOCK-IN: must match vector(768) in migration 006 and outputDimensionality in
// the indexing script. Any mismatch causes a Postgres type error at runtime.
const EMBED_DIMENSIONS = 768;

// Approximate token cap for RAG context injected into the system prompt.
// 6000 chars ≈ 1500 tokens at 4 chars/token. Whole-chunk truncation only — never
// mid-chunk. The '## BASE DE CONOCIMIENTO RELEVANTE' header is owned by
// system-prompt.ts; this module returns chunk bodies only (no duplication).
const MAX_RAG_CHARS = 6000;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface KnowledgeRow {
  id: string;
  content: string;
  metadata: { title?: string; source_file?: string } & Record<string, unknown>;
  score: number;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Retrieves relevant knowledge chunks for a given query text.
 *
 * Embeds the query using gemini-embedding-001 (768 dims, RETRIEVAL_QUERY taskType),
 * then calls the search_knowledge RPC (hybrid RRF: vector cosine + FTS).
 *
 * Failure semantics: ANY failure (embed error, RPC error, empty result) returns ''.
 * The function NEVER throws. The chat route continues normally when '' is returned —
 * system-prompt.ts omits the knowledge section and the model answers unassisted.
 *
 * @param queryText - The user's latest message text.
 * @returns Formatted knowledge chunks string, or '' on any error / no results.
 */
export async function searchKnowledgeBase(queryText: string): Promise<string> {
  const text = queryText?.trim();
  if (!text) return '';

  try {
    // Embed the query. taskType RETRIEVAL_QUERY optimises the embedding for
    // asymmetric retrieval (query vs. document). Must match dimension 768.
    const { embedding } = await embed({
      model: google.textEmbedding('gemini-embedding-001'),
      value: text,
      providerOptions: {
        google: {
          outputDimensionality: EMBED_DIMENSIONS,
          taskType: 'RETRIEVAL_QUERY',
        },
      },
    });

    // SESSION (anon/RLS) client — RLS select-authenticated policy applies.
    // Never use service-role in app code (secrets boundary enforced by design).
    const supabase = await createClient();
    const { data, error } = await supabase.rpc('search_knowledge', {
      query_embedding: embedding,
      query_text: text,
      match_count: 4,
    });

    if (error || !data) {
      console.error('[rag] rpc error:', error?.message ?? 'no data returned');
      return '';
    }

    return formatChunks(data as KnowledgeRow[]);
  } catch (err) {
    // Covers embed network failures, quota errors, and any unexpected throws.
    console.error('[rag] embed error:', err instanceof Error ? err.message : String(err));
    return '';
  }
}

// ---------------------------------------------------------------------------
// Formatting (exported for unit tests)
// ---------------------------------------------------------------------------

/**
 * Formats an array of knowledge rows into a plain-text block suitable for
 * injection into the system prompt.
 *
 * Format per chunk:
 *   [Conocimiento N — {title}]
 *   {content}
 *
 * Chunks are joined with \n\n---\n\n. Truncation is whole-chunk only: once
 * adding the next block would exceed MAX_RAG_CHARS the loop stops (no mid-chunk
 * splits). Returns '' when rows is empty.
 */
export function formatChunks(rows: KnowledgeRow[]): string {
  if (!rows.length) return '';

  const blocks: string[] = [];
  let used = 0;

  for (let i = 0; i < rows.length; i++) {
    const title =
      rows[i].metadata?.title ??
      rows[i].metadata?.source_file ??
      `Fragmento ${i + 1}`;
    const block = `[Conocimiento ${blocks.length + 1} — ${title}]\n${rows[i].content}`;

    // Whole-chunk cap: never split mid-chunk. Allow the FIRST chunk through even
    // if it alone exceeds the cap (avoids returning empty on an oversized single result).
    if (blocks.length > 0 && used + block.length > MAX_RAG_CHARS) break;

    blocks.push(block);
    used += block.length;
  }

  return blocks.join('\n\n---\n\n');
}
