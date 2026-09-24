"""P2: initial CycloAI schema adapted from the deleted Supabase project.

Revision ID: 1a2b3c4d5e6f
Revises:
Create Date: 2025-01-01 00:00:00

Provenance: the Supabase database was DELETED, so there is no data to migrate —
only the schema. Every original Supabase migration under
``supabase/migrations/`` was ported by hand into this single revision:

- ``001_create_profiles.sql``
    The ``profiles`` table. Adapted: the FK now targets our own ``users`` table
    (created here) instead of ``auth.users``, with ``on delete cascade``
    absorbed directly (see ``003``). All defaults made explicit
    (``not null default``) as specified for the standalone schema.

- ``002_harden_handle_new_user.sql``
    Nothing to port: it only ran ``revoke ... from anon, authenticated, public``
    on ``handle_new_user``, and those Supabase roles do not exist here. The
    hardening that survives is in the function itself: ``security definer``
    with a pinned empty ``search_path``.

- ``003_profiles_cascade.sql``
    Absorbed into the ``profiles.id`` FK (``on delete cascade``) in this
    revision instead of being a separate constraint swap.

- ``004_create_conversations.sql``
    The ``conversations`` table and the ``conversations_user_updated`` index.
    Adapted: ``user_id`` references ``users(id)`` (the original referenced
    ``profiles(id)``).

- ``005_create_messages.sql``
    The ``messages`` table and the ``messages_conversation`` index.

- ``006_knowledge_embeddings.sql``
    The ``vector`` extension, the ``knowledge_embeddings`` table (768-dim
    embeddings for gemini-embedding-001, generated Spanish ``tsvector``
    column), its HNSW / GIN-fts / GIN-metadata indexes, and the hybrid RRF
    ``search_knowledge`` function (k=60, 0.65 cosine threshold on the vector
    leg only, Spanish ``websearch_to_tsquery``).

- ``007_harden_search_knowledge.sql``
    KEPT in full: the ``vector`` extension relocated into the ``extensions``
    schema and ``search_knowledge`` recreated with the schema-qualified
    ``extensions.vector(768)`` signature, a pinned
    ``set search_path = public, extensions``, ``stable`` and
    ``security invoker``. Keeping ``public`` clean and pinning the search path
    is good practice outside Supabase too.

- ``008_waitlist.sql``
    The ``waitlist`` table and the case-insensitive
    ``waitlist_email_unique`` index on ``lower(email)``.

- ``009_waitlist_constrained_insert.sql``
    The original migration expressed the row-shape rules as a Row Level
    Security ``WITH CHECK``. Since RLS is gone, those rules are translated
    into the ``waitlist_email_shape`` CHECK constraint. This preserves the
    original intent — validation at the database layer as defense in depth
    against writes that bypass the application.

Dropped deliberately, and why:

- Row Level Security and every ``auth.uid()`` policy, plus the ``anon`` /
  ``authenticated`` / ``service_role`` roles: none of those exist outside
  Supabase. CONSEQUENCE: authorization moves entirely into the application
  layer. Every query must filter by owner, and the repository layer must be
  tested for cross-user isolation — the database no longer enforces it.
- ``auth.users`` and the FK onto it: replaced by our own ``users`` table
  (owned by the upcoming auth work), which carries ``password_hash`` and a
  case-insensitively unique ``email``.
- The ``handle_new_user`` trigger moves from ``auth.users`` onto our own
  ``users`` table, preserving the invariant that every user gets a ``profiles``
  row. The display name / avatar now come straight from the ``users`` row
  instead of ``raw_user_meta_data``.

The trigger is created last so all referenced objects exist first; the
downgrade reverses that order exactly.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- pgvector, relocated to its own schema (from 006 + 007) -------------
    op.execute("create extension if not exists vector")
    op.execute("create schema if not exists extensions")
    op.execute("alter extension vector set schema extensions")

    # --- users (replaces auth.users) ----------------------------------------
    op.execute(
        """
        create table users (
          id            uuid primary key default gen_random_uuid(),
          email         text not null,
          password_hash text not null,
          display_name  text,
          avatar_url    text,
          created_at    timestamptz not null default now()
        )
        """
    )
    op.execute("create unique index users_email_unique on users (lower(email))")

    # --- profiles (from 001, cascade absorbed from 003) ---------------------
    op.execute(
        """
        create table profiles (
          id                    uuid primary key references users(id) on delete cascade,
          created_at            timestamptz not null default now(),
          updated_at            timestamptz not null default now(),
          display_name          text,
          avatar_url            text,
          strava_id             bigint unique,
          strava_connected      boolean not null default false,
          strava_connected_at   timestamptz,
          objective             text,
          weekly_hours          numeric(4,1),
          gym_days_per_week     integer,
          injuries              text,
          has_power_meter       boolean not null default false,
          target_event          text,
          target_event_date     date,
          onboarding_completed  boolean not null default false,
          training_system       text not null default 'heart_rate'
                                check (training_system in ('power', 'heart_rate')),
          lthr_bpm              integer,
          ftp_estimated         integer,
          ctl                   numeric(6,2),
          atl                   numeric(6,2),
          tsb                   numeric(6,2),
          weekly_volume_km      numeric(8,2),
          weekly_volume_hours   numeric(6,2),
          avg_days_per_week     numeric(4,2),
          last_sync_at          timestamptz
        )
        """
    )

    # --- conversations (from 004) -------------------------------------------
    op.execute(
        """
        create table conversations (
          id         uuid primary key default gen_random_uuid(),
          user_id    uuid not null references users(id) on delete cascade,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          title      text,
          summary    text
        )
        """
    )
    op.execute(
        "create index conversations_user_updated on conversations (user_id, updated_at desc)"
    )

    # --- messages (from 005) --------------------------------------------------
    op.execute(
        """
        create table messages (
          id              uuid primary key default gen_random_uuid(),
          conversation_id uuid not null references conversations(id) on delete cascade,
          user_id         uuid not null references users(id) on delete cascade,
          role            text not null check (role in ('user', 'assistant')),
          content         text not null,
          created_at      timestamptz not null default now(),
          metadata        jsonb
        )
        """
    )
    op.execute("create index messages_conversation on messages (conversation_id, created_at)")

    # --- knowledge_embeddings (from 006, extension relocated per 007) --------
    op.execute(
        """
        create table knowledge_embeddings (
          id         uuid primary key default gen_random_uuid(),
          content    text not null,
          embedding  extensions.vector(768) not null,
          metadata   jsonb not null default '{}',
          fts        tsvector generated always as (to_tsvector('spanish', content)) stored,
          created_at timestamptz default now()
        )
        """
    )
    op.execute(
        """
        create index knowledge_embeddings_hnsw on knowledge_embeddings
          using hnsw (embedding extensions.vector_cosine_ops) with (m = 16, ef_construction = 64)
        """
    )
    op.execute("create index knowledge_embeddings_fts on knowledge_embeddings using gin (fts)")
    op.execute(
        "create index knowledge_embeddings_metadata on knowledge_embeddings using gin (metadata)"
    )

    # --- search_knowledge (from 006, hardened per 007) -----------------------
    op.execute(
        """
        create or replace function search_knowledge(
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
        $$
        """
    )

    # --- handle_new_user trigger, now on public.users (from 001) -------------
    op.execute(
        """
        create or replace function public.handle_new_user()
        returns trigger
        language plpgsql
        security definer
        set search_path = ''
        as $$
        begin
          insert into public.profiles (id, display_name, avatar_url, onboarding_completed)
          values (new.id, new.display_name, new.avatar_url, false);
          return new;
        end;
        $$
        """
    )
    op.execute(
        """
        create trigger on_user_created
          after insert on public.users
          for each row execute function public.handle_new_user()
        """
    )

    # --- waitlist (from 008; RLS WITH CHECK from 009 became a CHECK) ---------
    op.execute(
        """
        create table waitlist (
          id         uuid primary key default gen_random_uuid(),
          email      text not null,
          source     text,
          created_at timestamptz default now(),
          constraint waitlist_email_shape check (
            char_length(email) between 3 and 320
            and position('@' in email) > 1
            and position('.' in split_part(email, '@', 2)) > 0
            and (source is null or char_length(source) <= 50)
          )
        )
        """
    )
    op.execute("create unique index waitlist_email_unique on waitlist (lower(email))")


def downgrade() -> None:
    op.execute("drop table if exists waitlist")
    op.execute("drop table if exists knowledge_embeddings")
    op.execute("drop table if exists messages")
    op.execute("drop table if exists conversations")
    op.execute("drop table if exists profiles")
    op.execute("drop table if exists users")
    op.execute("drop function if exists public.handle_new_user()")
    op.execute(
        "drop function if exists public.search_knowledge(extensions.vector, text, integer)"
    )
    op.execute("drop extension if exists vector")
    op.execute("drop schema if exists extensions")
