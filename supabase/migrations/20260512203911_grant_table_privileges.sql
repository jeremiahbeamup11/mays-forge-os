-- ============================================================================
-- Migration: grant_table_privileges
-- ============================================================================
-- Grants the necessary privileges to the `authenticated` and `anon` roles
-- on all public tables and the helper functions.
--
-- Why this is needed:
-- Tables created via Supabase CLI migrations run as the `postgres` user.
-- Unlike tables created through the Supabase dashboard (which auto-grant),
-- CLI-created tables only have privileges for `postgres`. The
-- `authenticated` role needs explicit grants to INSERT/SELECT/UPDATE/DELETE
-- through the PostgREST API, even with RLS policies in place.
--
-- RLS policies control WHICH rows are accessible.
-- Grants control WHETHER the role can access the table at all.
-- Both are required.
-- ============================================================================

-- Organizations: authenticated users can read, create, update, delete
-- (RLS policies further restrict which rows)
grant select, insert, update, delete on public.organizations to authenticated;

-- Memberships: authenticated users can read, create, update, delete
grant select, insert, update, delete on public.memberships to authenticated;

-- Files: authenticated users can read, create, update, delete
grant select, insert, update, delete on public.files to authenticated;

-- Anon gets nothing on any table (our RLS policies already exclude anon,
-- but belt-and-suspenders: don't even grant table access)
-- (No grants for anon — intentionally omitted)

-- Grant usage on custom types so authenticated role can use the enums
grant usage on schema public to authenticated;
grant usage on schema public to anon;
