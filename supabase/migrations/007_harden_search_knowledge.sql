-- Migration 007: harden search_knowledge + relocate vector extension
-- Fixes two Supabase security advisors:
--   1. "Extension in Public"          — vector moves to the extensions schema.
--   2. "Function Search Path Mutable" — search_knowledge gets a pinned search_path.
--
-- Order matters: the extension moves FIRST; the function is then recreated with
-- an explicit extensions-qualified signature and a pinned search_path so the
-- vector operators (<=>) keep resolving at execution time.

-- Supabase projects ship with an `extensions` schema (usage granted to all roles);
-- create defensively for portability.
create schema if not exists extensions;

alter extension vector set schema extensions;

-- Recreate with pinned search_path. Signature type is schema-qualified because
-- the migration session's default search_path no longer sees `vector` unqualified.
create or replace function public.search_knowledge(
  query_embedding extensions.vector(768),
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
set search_path = public, extensions
as $$
  with vector_hits as (
    select
      ke.id,
      row_number() over (order by ke.embedding <=> query_embedding) as rank
    from knowledge_embeddings ke
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
