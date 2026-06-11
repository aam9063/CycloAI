-- Migration 004: conversations table
-- Stores chat conversation threads, one per user per topic.

create table conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  title text,
  summary text
);

create index conversations_user_updated on conversations(user_id, updated_at desc);

alter table conversations enable row level security;

create policy "conversations_select_own" on conversations
  for select using (auth.uid() = user_id);

create policy "conversations_insert_own" on conversations
  for insert with check (auth.uid() = user_id);

create policy "conversations_update_own" on conversations
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
