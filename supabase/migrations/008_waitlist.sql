-- Migration 008: waitlist
-- Pre-launch waiting list. Public (anon) INSERT-only: visitors sign up from the
-- landing without an account. No read/update/delete from the API — the list is
-- consumed from the Supabase dashboard / service contexts only.

create table waitlist (
  id          uuid primary key default gen_random_uuid(),
  email       text not null,
  source      text,                      -- e.g. 'landing-hero', 'landing-cta'
  created_at  timestamptz default now()
);

-- Case-insensitive uniqueness: one row per email regardless of casing.
create unique index waitlist_email_unique on waitlist (lower(email));

alter table waitlist enable row level security;

-- Anyone (anon or authenticated) may join; nobody may read the list via the API.
create policy "waitlist_insert_public"
  on waitlist
  for insert
  to anon, authenticated
  with check (true);
