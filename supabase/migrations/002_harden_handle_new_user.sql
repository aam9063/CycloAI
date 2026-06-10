-- Migration: 002_harden_handle_new_user
-- The trigger function runs via auth.users inserts (supabase_auth_admin);
-- it must not be callable through the PostgREST RPC API.
-- Fixes Supabase security advisor warnings 0028/0029.

revoke execute on function public.handle_new_user() from anon, authenticated, public;
