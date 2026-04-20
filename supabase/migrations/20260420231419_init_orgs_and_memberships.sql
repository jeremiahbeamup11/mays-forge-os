-- ============================================================================
-- Migration: init_orgs_and_memberships
-- ============================================================================
-- Creates the core multi-tenant schema for Mays Forge OS:
--
--   * public.organizations  - one row per tenant (city).
--   * public.memberships    - links users to organizations with a role.
--
-- Enforces tenant isolation via Row-Level Security. Even a buggy API query
-- that forgets to filter by org will return nothing to unauthorized callers,
-- because Postgres itself refuses to surface the rows.
--
-- Helper function public.is_org_member(uuid) is SECURITY DEFINER so RLS
-- policies can reference it without triggering recursion on the memberships
-- table.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Extensions
-- ----------------------------------------------------------------------------
-- pgcrypto gives us gen_random_uuid() for default primary keys. Supabase
-- usually has it on, but we enable defensively in case this migration is
-- ever replayed on a fresh project.
create extension if not exists pgcrypto;


-- ----------------------------------------------------------------------------
-- Enums
-- ----------------------------------------------------------------------------
-- Membership role is a fixed enum rather than free text. Constrains data at
-- the DB layer and documents the valid set in one place.
do $$
begin
  if not exists (select 1 from pg_type where typname = 'membership_role') then
    create type public.membership_role as enum ('owner', 'admin', 'member');
  end if;
end
$$;


-- ----------------------------------------------------------------------------
-- Table: organizations
-- ----------------------------------------------------------------------------
create table if not exists public.organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  slug        text not null unique,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  created_by  uuid references auth.users(id) on delete set null
);

comment on table public.organizations is
  'Tenants in Mays Forge OS. Each city/customer gets one row here.';
comment on column public.organizations.slug is
  'URL-safe identifier, e.g. "peotone-il". Lowercased, hyphenated, unique.';
comment on column public.organizations.created_by is
  'User who created the org. Set to null (not deleted) if the user is removed.';

-- Validate slugs at the database layer. No uppercase, no spaces, no symbols.
alter table public.organizations
  add constraint organizations_slug_format
  check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$');


-- ----------------------------------------------------------------------------
-- Table: memberships
-- ----------------------------------------------------------------------------
create table if not exists public.memberships (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id         uuid not null references auth.users(id) on delete cascade,
  role            public.membership_role not null default 'member',
  created_at      timestamptz not null default now(),
  unique (organization_id, user_id)
);

comment on table public.memberships is
  'Which users belong to which organizations, and in what role.';
comment on column public.memberships.organization_id is
  'Cascading delete: removing an org removes its memberships.';
comment on column public.memberships.user_id is
  'Cascading delete: removing a user removes their memberships.';

-- Index to speed up "which orgs does this user belong to?" queries,
-- which is the hottest path in RLS policies.
create index if not exists memberships_user_id_idx on public.memberships (user_id);


-- ----------------------------------------------------------------------------
-- Helper: is_org_member(org_id)
-- ----------------------------------------------------------------------------
-- Returns true iff the current authenticated user has a membership in the
-- given organization. Used by RLS policies on every tenant-scoped table.
--
-- SECURITY DEFINER means the function runs with the privileges of its owner
-- (postgres), not the caller. That lets it read public.memberships even when
-- the caller itself doesn't have direct select privileges on that table —
-- and it prevents the recursive policy trap where "to read memberships you
-- must check memberships."
--
-- We set search_path explicitly to prevent schema-hijack attacks where a
-- malicious user creates a shadow function in their own schema.
create or replace function public.is_org_member(org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.memberships
    where organization_id = org_id
      and user_id = auth.uid()
  );
$$;

comment on function public.is_org_member(uuid) is
  'Returns true if the current authenticated user is a member of the given organization. SECURITY DEFINER to avoid RLS recursion.';

-- Lock down who can execute the helper. Only authenticated roles should be
-- able to call it; anon users never need to.
revoke all on function public.is_org_member(uuid) from public;
grant execute on function public.is_org_member(uuid) to authenticated;


-- ----------------------------------------------------------------------------
-- Row-Level Security: organizations
-- ----------------------------------------------------------------------------
alter table public.organizations enable row level security;

-- Read: a user sees an org only if they're a member of it.
create policy "organizations_select_if_member"
  on public.organizations
  for select
  to authenticated
  using (public.is_org_member(id));

-- Insert: any authenticated user may create a new org. The accompanying
-- membership row is created by a trigger below, so the creator is
-- guaranteed to be a member of the org they just made.
create policy "organizations_insert_any_authenticated"
  on public.organizations
  for insert
  to authenticated
  with check (auth.uid() is not null);

-- Update: only admins/owners of the org can modify it.
create policy "organizations_update_if_admin_or_owner"
  on public.organizations
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.memberships m
      where m.organization_id = organizations.id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner')
    )
  )
  with check (
    exists (
      select 1
      from public.memberships m
      where m.organization_id = organizations.id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner')
    )
  );

-- Delete: only owners can delete. Deliberately stricter than update.
create policy "organizations_delete_if_owner"
  on public.organizations
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.memberships m
      where m.organization_id = organizations.id
        and m.user_id = auth.uid()
        and m.role = 'owner'
    )
  );


-- ----------------------------------------------------------------------------
-- Row-Level Security: memberships
-- ----------------------------------------------------------------------------
alter table public.memberships enable row level security;

-- Read: users see their own memberships and the memberships of orgs they
-- belong to (so they can see their teammates).
create policy "memberships_select_self_or_same_org"
  on public.memberships
  for select
  to authenticated
  using (
    user_id = auth.uid()
    or public.is_org_member(organization_id)
  );

-- Insert: only admins/owners of the target org can add new members.
-- We intentionally DON'T allow arbitrary self-insertion — joining an org
-- must go through an invite flow (to be added later).
create policy "memberships_insert_if_admin_or_owner"
  on public.memberships
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.memberships m
      where m.organization_id = memberships.organization_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner')
    )
  );

-- Update: admins/owners can change roles of other members. A user cannot
-- edit their own role (prevents privilege escalation by self-update).
create policy "memberships_update_if_admin_or_owner"
  on public.memberships
  for update
  to authenticated
  using (
    user_id <> auth.uid()
    and exists (
      select 1
      from public.memberships m
      where m.organization_id = memberships.organization_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner')
    )
  )
  with check (
    user_id <> auth.uid()
    and exists (
      select 1
      from public.memberships m
      where m.organization_id = memberships.organization_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner')
    )
  );

-- Delete: a user can remove themselves, or an admin/owner can remove anyone.
create policy "memberships_delete_self_or_admin"
  on public.memberships
  for delete
  to authenticated
  using (
    user_id = auth.uid()
    or exists (
      select 1
      from public.memberships m
      where m.organization_id = memberships.organization_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner')
    )
  );


-- ----------------------------------------------------------------------------
-- Trigger: auto-create membership when a user creates an organization
-- ----------------------------------------------------------------------------
-- Without this, a freshly created org would have zero memberships and the
-- creator couldn't even see the row they just made (RLS would hide it).
-- The trigger gives the creator an 'owner' membership atomically.
create or replace function public.handle_new_organization()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.memberships (organization_id, user_id, role)
  values (new.id, auth.uid(), 'owner');
  return new;
end;
$$;

drop trigger if exists on_organization_created on public.organizations;
create trigger on_organization_created
  after insert on public.organizations
  for each row
  execute function public.handle_new_organization();


-- ----------------------------------------------------------------------------
-- Trigger: keep updated_at fresh on organizations
-- ----------------------------------------------------------------------------
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists touch_organizations_updated_at on public.organizations;
create trigger touch_organizations_updated_at
  before update on public.organizations
  for each row
  execute function public.touch_updated_at();
