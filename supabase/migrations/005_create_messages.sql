-- Migration 005: messages table
-- Append-only log of all chat messages (user + assistant turns).

create table messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz default now(),
  metadata jsonb
);

create index messages_conversation on messages(conversation_id, created_at);

alter table messages enable row level security;

create policy "messages_select_own" on messages
  for select using (auth.uid() = user_id);

create policy "messages_insert_own" on messages
  for insert with check (auth.uid() = user_id);
