-- Migration 006: knowledge_embeddings (RAG corpus + hybrid search)
-- Adds vector extension, knowledge_embeddings table with HNSW + FTS + RLS,
-- and the search_knowledge RPC using Reciprocal Rank Fusion (RRF k=60).

create extension if not exists vector;

create table knowledge_embeddings (
  id          uuid primary key default gen_random_uuid(),
  content     text not null,
  -- LOCK-IN: dimension 768 = Google gemini-embedding-001 with outputDimensionality 768.
  -- Must match index script (RETRIEVAL_DOCUMENT) and query module (RETRIEVAL_QUERY).
  embedding   vector(768) not null,
  -- { category, source_file, title, chunk_index, total_chunks, keywords[] }
  metadata    jsonb not null default '{}',
  -- Generated STORED column: tsvector computed once per insert/update, Spanish config.
  -- Avoids repeating to_tsvector() in every FTS query; planner reuses for @@ and ts_rank_cd.
  fts         tsvector generated always as (to_tsvector('spanish', content)) stored,
  created_at  timestamptz default now()
);

-- HNSW (not ivfflat): no training threshold at ~200-400 chunks, better recall at this corpus size.
create index knowledge_embeddings_hnsw
  on knowledge_embeddings
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- GIN on generated fts column: used by the FTS leg of search_knowledge.
create index knowledge_embeddings_fts
  on knowledge_embeddings using gin (fts);

-- GIN on metadata: supports future category filtering (deferred feature).
create index knowledge_embeddings_metadata
  on knowledge_embeddings using gin (metadata);

-- RLS: shared non-sensitive content. Any authenticated user may SELECT.
-- The indexing script uses the service role which bypasses RLS for writes.
-- No INSERT / UPDATE / DELETE policy: app is read-only.
alter table knowledge_embeddings enable row level security;

create policy "knowledge_select_authenticated"
  on knowledge_embeddings
  for select
  using (auth.uid() is not null);

-- ---------------------------------------------------------------------------
-- search_knowledge: hybrid RRF retrieval (vector cosine + FTS).
-- RRF k=60 (Cormack et al.) fuses ranks from two independent legs:
--   vector_hits  — cosine similarity > 0.65 (threshold applied ONLY on vector leg)
--   fts_hits     — websearch_to_tsquery 'spanish' (injection-safe; never raises on punctuation)
-- Full outer join ensures acronym/exact-term queries (FTP, TSS, CTL, ATL, TSB, VO2max)
-- surface via FTS even when vector similarity is below the threshold.
-- Returns up to match_count rows ordered by descending fused RRF score.
-- STABLE + SECURITY INVOKER: RLS select-authenticated policy applies to the caller's session.
-- ---------------------------------------------------------------------------
create or replace function search_knowledge(
  query_embedding vector(768),
  query_text      text,
  match_count     int default 4
)
returns table (
  id       uuid,
  content  text,
  metadata jsonb,
  score    double precision
)
language sql
stable
security invoker
as $$
  with vector_hits as (
    select
      ke.id,
      row_number() over (order by ke.embedding <=> query_embedding) as rank
    from knowledge_embeddings ke
    -- Vector threshold applied only on this leg. FTS leg is unfiltered so acronym
    -- queries that score below 0.65 in cosine space still surface via FTS.
    where (1 - (ke.embedding <=> query_embedding)) > 0.65
    order by ke.embedding <=> query_embedding
    limit 10
  ),
  fts_hits as (
    select
      ke.id,
      row_number() over (
        order by ts_rank_cd(ke.fts, websearch_to_tsquery('spanish', query_text)) desc
      ) as rank
    from knowledge_embeddings ke
    where ke.fts @@ websearch_to_tsquery('spanish', query_text)
    limit 10
  ),
  fused as (
    select
      coalesce(v.id, f.id) as id,
      coalesce(1.0 / (60 + v.rank), 0.0)
        + coalesce(1.0 / (60 + f.rank), 0.0) as score
    from vector_hits v
    full outer join fts_hits f on v.id = f.id
  )
  select
    ke.id,
    ke.content,
    ke.metadata,
    fused.score
  from fused
  join knowledge_embeddings ke on ke.id = fused.id
  order by fused.score desc
  limit match_count;
$$;
