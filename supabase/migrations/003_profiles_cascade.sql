-- Migration: 003_profiles_cascade
-- Adds ON DELETE CASCADE to the profiles → auth.users FK so that calling
-- admin.deleteUser(id) via the delete-account edge function automatically
-- removes the matching profiles row.
--
-- Constraint name: Postgres default for `id uuid references auth.users(id)`
-- is `profiles_id_fkey`. Verify before applying:
--   SELECT constraint_name FROM information_schema.table_constraints
--   WHERE table_name = 'profiles' AND constraint_type = 'FOREIGN KEY';
-- Adjust the constraint name below if it differs.
--
-- Idempotent: DROP CONSTRAINT IF EXISTS means re-running is safe.

alter table public.profiles
  drop constraint if exists profiles_id_fkey;

alter table public.profiles
  add constraint profiles_id_fkey
  foreign key (id)
  references auth.users(id)
  on delete cascade;
