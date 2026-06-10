-- Migration: 001_create_profiles
-- Creates the profiles table, enables RLS, adds owner-only policies,
-- and wires the handle_new_user trigger for auto-insert on auth.users registration.

create table profiles (
  id uuid references auth.users(id) primary key,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),

  -- Identity
  display_name text,
  avatar_url text,

  -- Strava integration (null until user connects)
  strava_id bigint unique,
  strava_connected boolean default false,
  strava_connected_at timestamptz,

  -- Onboarding fields
  objective text,
  weekly_hours numeric(4,1),
  gym_days_per_week integer,
  injuries text,
  has_power_meter boolean default false,
  target_event text,
  target_event_date date,
  onboarding_completed boolean default false,

  -- Strava metric cache (refreshed on each sync)
  ftp_estimated integer,
  ctl numeric(6,2),
  atl numeric(6,2),
  tsb numeric(6,2),
  weekly_volume_km numeric(8,2),
  weekly_volume_hours numeric(6,2),
  avg_days_per_week numeric(4,2),
  last_sync_at timestamptz
);

-- Enable Row Level Security
alter table profiles enable row level security;

-- Owner-only SELECT: users can only read their own profile
create policy "profiles_select_own"
  on profiles
  for select
  using (auth.uid() = id);

-- Owner-only UPDATE: users can only update their own profile
create policy "profiles_update_own"
  on profiles
  for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- No INSERT policy for regular users — inserts happen only via the
-- security-definer trigger below, which bypasses RLS.

-- Auto-insert a profiles row when a new user signs up (email or OAuth).
-- security definer + set search_path = '' hardens against search_path injection.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, avatar_url, onboarding_completed)
  values (
    new.id,
    coalesce(
      new.raw_user_meta_data ->> 'full_name',
      new.raw_user_meta_data ->> 'name'
    ),
    new.raw_user_meta_data ->> 'avatar_url',
    false
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
