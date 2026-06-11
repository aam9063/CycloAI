/**
 * RAG indexing script — offline, developer-run tooling.
 *
 * Reads every *.md file under knowledge-base/, chunks by ## headings (max 400 words,
 * 50-word overlap for oversized sections), embeds with gemini-embedding-001 (768 dims,
 * RETRIEVAL_DOCUMENT taskType), then upserts into knowledge_embeddings via the
 * service-role Supabase client (bypasses RLS).
 *
 * Run: pnpm rag:index
 *
 * Required env vars (set in shell before running — NEVER persist to .env files):
 *   SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL
 *   SUPABASE_SERVICE_ROLE_KEY
 *   GOOGLE_GENERATIVE_AI_API_KEY
 *
 * The SUPABASE_SERVICE_ROLE_KEY is read only here (scripts/rag-index.ts).
 * It MUST NOT appear in app/, lib/, components/, or any committed .env file.
 */

import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import { loadEnvConfig } from '@next/env';
import { createClient } from '@supabase/supabase-js';
import { google } from '@ai-sdk/google';
import { embedMany } from 'ai';

// ---------------------------------------------------------------------------
// 1. Environment validation
// ---------------------------------------------------------------------------

// Load .env / .env.local exactly like Next.js does, so the PUBLIC vars and the
// Gemini key (already in the developer's .env) are picked up automatically.
// SUPABASE_SERVICE_ROLE_KEY is intentionally NOT in any .env file — it must be
// exported ad-hoc in the shell for each run.
loadEnvConfig(process.cwd());

const supabaseUrl =
  process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL ?? '';
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY ?? '';
const googleApiKey = process.env.GOOGLE_GENERATIVE_AI_API_KEY ?? '';

const missingVars: string[] = [];
if (!supabaseUrl) missingVars.push('SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL)');
if (!serviceRoleKey) missingVars.push('SUPABASE_SERVICE_ROLE_KEY');
if (!googleApiKey) missingVars.push('GOOGLE_GENERATIVE_AI_API_KEY');

if (missingVars.length > 0) {
  console.error(
    'Error: las siguientes variables de entorno son requeridas y no están configuradas:\n' +
      missingVars.map((v) => `  - ${v}`).join('\n') +
      '\nExporte las variables en su terminal antes de ejecutar pnpm rag:index.'
  );
  process.exit(1);
}

// ---------------------------------------------------------------------------
// 2. Clients
// ---------------------------------------------------------------------------

// Plain Node client with service-role key — bypasses RLS for writes.
// This client is LOCAL to this script; never exported or used by app code.
const supabase = createClient(supabaseUrl, serviceRoleKey);

// ---------------------------------------------------------------------------
// 2b. Rate-limit helpers (Gemini free tier: ~100 embed requests/min,
//     each VALUE in an embedMany batch counts as one request)
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Extracts Google's suggested retry delay ("Please retry in 31.66s") if present. */
function parseRetryDelayMs(message: string): number {
  const match = message.match(/retry in ([\d.]+)\s*s/i);
  if (match) return Math.ceil(parseFloat(match[1]) * 1000) + 1000; // +1s safety
  return 45_000; // sensible default for a per-minute quota window
}

function isQuotaError(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes('quota') ||
    lower.includes('429') ||
    lower.includes('rate limit') ||
    lower.includes('resource_exhausted')
  );
}

/**
 * embedMany with patient quota backoff: on quota errors, waits the delay Google
 * suggests (or 45s) and retries — up to maxAttempts total tries.
 */
async function embedWithBackoff(
  values: string[],
  maxAttempts = 5
): Promise<number[][]> {
  let lastError = '';
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const result = await embedMany({
        model: google.textEmbedding('gemini-embedding-001'),
        values,
        providerOptions: {
          google: {
            outputDimensionality: 768,
            taskType: 'RETRIEVAL_DOCUMENT',
          },
        },
      });
      return result.embeddings;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
      if (!isQuotaError(lastError) || attempt === maxAttempts) throw err;
      const waitMs = parseRetryDelayMs(lastError);
      console.log(
        `    · cuota alcanzada — esperando ${Math.round(waitMs / 1000)}s antes de reintentar (${attempt}/${maxAttempts - 1})`
      );
      await sleep(waitMs);
    }
  }
  throw new Error(lastError);
}

// ---------------------------------------------------------------------------
// 3. File walker
// ---------------------------------------------------------------------------

/**
 * Recursively collects all *.md file paths under the given directory.
 * Uses Node fs only — no glob dependency.
 */
function walkMarkdownFiles(dir: string): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkMarkdownFiles(full));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      results.push(full);
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// 4. Chunker
// ---------------------------------------------------------------------------

const MAX_CHUNK_WORDS = 400;
const OVERLAP_WORDS = 50;

/**
 * Splits a markdown body into chunks using ## headings as primary boundaries.
 *
 * - Each ## section with ≤ MAX_CHUNK_WORDS words → one chunk.
 * - Each ## section with > MAX_CHUNK_WORDS words → sliding window with OVERLAP_WORDS.
 * - The ## heading is kept inside each chunk so it carries its section title.
 *
 * @param body - Raw markdown body (frontmatter already stripped by gray-matter).
 * @returns Array of chunk strings.
 */
function chunkMarkdown(body: string): string[] {
  // Split on newlines that precede a ## heading (keeps the ## at the start of each section).
  const sections = body.split(/\n(?=## )/);
  const chunks: string[] = [];

  for (const section of sections) {
    const trimmed = section.trim();
    if (!trimmed) continue;

    const words = trimmed.split(/\s+/);

    if (words.length <= MAX_CHUNK_WORDS) {
      chunks.push(trimmed);
    } else {
      // Sliding window: each window is MAX_CHUNK_WORDS words with OVERLAP_WORDS overlap.
      let start = 0;
      while (start < words.length) {
        const end = Math.min(start + MAX_CHUNK_WORDS, words.length);
        const chunk = words.slice(start, end).join(' ');
        chunks.push(chunk);
        if (end === words.length) break;
        start += MAX_CHUNK_WORDS - OVERLAP_WORDS;
      }
    }
  }

  return chunks.filter((c) => c.length > 0);
}

// ---------------------------------------------------------------------------
// 5. Main indexing loop
// ---------------------------------------------------------------------------

interface FileResult {
  file: string;
  chunks: number;
  status: 'ok' | 'failed' | 'skipped';
  error?: string;
}

async function indexFile(
  filePath: string,
  knowledgeBaseDir: string,
  force: boolean
): Promise<FileResult> {
  const relativePath = path
    .relative(knowledgeBaseDir, filePath)
    .replace(/\\/g, '/');

  // Resume mode: skip files that already have chunks in the DB (saves quota on
  // re-runs after partial failures). Use --force to re-embed everything.
  if (!force) {
    const { count } = await supabase
      .from('knowledge_embeddings')
      .select('id', { count: 'exact', head: true })
      .eq('metadata->>source_file', relativePath);
    if ((count ?? 0) > 0) {
      return { file: relativePath, chunks: count ?? 0, status: 'skipped' };
    }
  }

  // Derive category from the first path segment under knowledge-base/.
  const category = relativePath.split('/')[0] ?? 'unknown';

  let parsed: ReturnType<typeof matter>;
  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    parsed = matter(raw);
  } catch (err) {
    return {
      file: relativePath,
      chunks: 0,
      status: 'failed',
      error: `read/parse error: ${err instanceof Error ? err.message : String(err)}`,
    };
  }

  const frontmatter = parsed.data as {
    title?: string;
    keywords?: string[];
    category?: string;
  };
  const title =
    frontmatter.title ?? path.basename(filePath, '.md');
  const keywords = frontmatter.keywords ?? [];
  const sourceFile = relativePath;

  const chunkTexts = chunkMarkdown(parsed.content);
  if (chunkTexts.length === 0) {
    return {
      file: relativePath,
      chunks: 0,
      status: 'failed',
      error: 'no chunks produced (file may be empty)',
    };
  }

  // Embed all chunks for this file in a single batched call, with quota backoff.
  let embeddings: number[][];
  try {
    embeddings = await embedWithBackoff(chunkTexts);
  } catch (err) {
    return {
      file: relativePath,
      chunks: 0,
      status: 'failed',
      error: `embed error: ${err instanceof Error ? err.message : String(err)}`,
    };
  }

  // Idempotent write: delete existing rows for this source_file, then insert fresh.
  // Brief delete+insert window is acceptable for offline dev reindexing.
  const { error: deleteError } = await supabase
    .from('knowledge_embeddings')
    .delete()
    .eq('metadata->>source_file', sourceFile);

  if (deleteError) {
    return {
      file: relativePath,
      chunks: 0,
      status: 'failed',
      error: `delete error: ${deleteError.message}`,
    };
  }

  const rows = chunkTexts.map((content, idx) => ({
    content,
    embedding: embeddings[idx],
    metadata: {
      category,
      source_file: sourceFile,
      title,
      chunk_index: idx,
      total_chunks: chunkTexts.length,
      keywords,
    },
  }));

  const { error: insertError } = await supabase
    .from('knowledge_embeddings')
    .insert(rows);

  if (insertError) {
    return {
      file: relativePath,
      chunks: 0,
      status: 'failed',
      error: `insert error: ${insertError.message}`,
    };
  }

  return { file: relativePath, chunks: chunkTexts.length, status: 'ok' };
}

async function main(): Promise<void> {
  const repoRoot = path.resolve(__dirname, '..');
  const knowledgeBaseDir = path.join(repoRoot, 'knowledge-base');

  if (!fs.existsSync(knowledgeBaseDir)) {
    console.error(
      `Error: el directorio knowledge-base no existe en ${knowledgeBaseDir}\n` +
        'Los archivos de contenido deben ser creados antes de ejecutar este script.'
    );
    process.exit(1);
  }

  const files = walkMarkdownFiles(knowledgeBaseDir);

  if (files.length === 0) {
    console.error(
      'Error: no se encontraron archivos .md en knowledge-base/\n' +
        'Agregue contenido antes de ejecutar el indexador.'
    );
    process.exit(1);
  }

  const force = process.argv.includes('--force');
  console.log(
    `\nIndexando ${files.length} archivo(s) desde ${knowledgeBaseDir}` +
      (force ? ' (--force: re-embebe todo)' : ' (reanudación: salta lo ya indexado)') +
      '\n'
  );

  const results: FileResult[] = [];
  for (const filePath of files) {
    const result = await indexFile(filePath, knowledgeBaseDir, force);
    results.push(result);
    const icon =
      result.status === 'ok' ? '✓' : result.status === 'skipped' ? '→' : '✗';
    const detail =
      result.status === 'ok'
        ? `${result.chunks} chunk(s)`
        : result.status === 'skipped'
          ? `ya indexado (${result.chunks} chunk(s)) — omitido`
          : `FAILED: ${result.error ?? 'unknown error'}`;
    console.log(`  ${icon} ${result.file} — ${detail}`);

    // Pace embedding throughput: free tier counts each chunk as a request
    // against a ~100/min window. ~700ms per embedded chunk keeps us under it.
    if (result.status === 'ok') {
      await sleep(result.chunks * 700);
    }
  }

  // Final summary
  const totalFiles = results.length;
  const embedded = results.filter((r) => r.status === 'ok');
  const totalChunks = embedded.reduce((sum, r) => sum + r.chunks, 0);
  const totalSkipped = results.filter((r) => r.status === 'skipped').length;
  const totalFailed = results.filter((r) => r.status === 'failed').length;

  console.log('\n----------------------------------------');
  console.log(`Archivos procesados : ${totalFiles}`);
  console.log(`Embebidos ahora     : ${embedded.length} (${totalChunks} chunks)`);
  console.log(`Omitidos (ya en DB) : ${totalSkipped}`);
  console.log(`Fallos              : ${totalFailed}`);
  console.log('----------------------------------------\n');

  if (totalFailed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Error fatal:', err instanceof Error ? err.message : String(err));
  process.exit(1);
});
