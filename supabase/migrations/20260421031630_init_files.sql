-- ============================================================================
-- Migration: init_files
-- ============================================================================
-- Creates the files table that tracks all uploads across the system.
--
-- Each row represents ONE file uploaded to ONE organization. The binary
-- itself lives in Supabase Storage; this table holds the metadata and
-- any AI-generated analysis of the file's contents.
--
-- Processing lifecycle:
--   pending     -> file row exists, upload in progress or just completed
--   parsing     -> we're parsing the file (CSV decode, PDF text extract, etc)
--   analyzing   -> Claude (or other AI) is analyzing the parsed content
--   complete    -> analysis attached, ready for retrieval
--   failed      -> something went wrong; see processing_error for details
--
-- RLS: tenant-isolated. A file can be seen/modified only by members of
-- the org it belongs to.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Enums
-- ----------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'file_processing_status') then
    create type public.file_processing_status as enum (
      'pending', 'parsing', 'analyzing', 'complete', 'failed'
    );
  end if;
end
$$;

do $$
begin
  if not exists (select 1 from pg_type where typname = 'file_kind') then
    create type public.file_kind as enum (
      'csv', 'pdf', 'image', 'geojson', 'other'
    );
  end if;
end
$$;


-- ----------------------------------------------------------------------------
-- Table: files
-- ----------------------------------------------------------------------------
create table if not exists public.files (
  id                  uuid primary key default gen_random_uuid(),
  organization_id     uuid not null references public.organizations(id) on delete cascade,
  uploaded_by         uuid references auth.users(id) on delete set null,

  -- Original file metadata
  original_filename   text not null,
  content_type        text not null,         -- MIME type as declared by client
  size_bytes          bigint not null check (size_bytes >= 0),
  kind                public.file_kind not null default 'other',

  -- Storage pointer (bucket + path inside the bucket)
  storage_bucket      text not null,
  storage_path        text not null,

  -- Processing state machine
  processing_status   public.file_processing_status not null default 'pending',
  processing_error    text,

  -- AI-generated analysis (shape varies by kind)
  analysis            jsonb,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),

  -- Storage path must be unique within a bucket.
  unique (storage_bucket, storage_path)
);

comment on table public.files is
  'All files uploaded to Mays Forge OS, one row per upload. Binary data lives in Supabase Storage.';
comment on column public.files.organization_id is
  'Owning tenant. Cascading delete: removing an org removes all its files.';
comment on column public.files.uploaded_by is
  'User who uploaded. Set to null if user is later removed, so files survive.';
comment on column public.files.kind is
  'High-level type for routing to the right parser/analyzer.';
comment on column public.files.analysis is
  'Structured AI analysis result. Shape depends on kind. Queryable via JSONB operators.';


-- Index for the hottest query: "show me this org's files, newest first."
create index if not exists files_org_created_idx
  on public.files (organization_id, created_at desc);

-- Index for the background worker query: "give me files that need processing."
create index if not exists files_status_idx
  on public.files (processing_status)
  where processing_status in ('pending', 'parsing', 'analyzing');


-- ----------------------------------------------------------------------------
-- Row-Level Security
-- ----------------------------------------------------------------------------
alter table public.files enable row level security;

-- Read: any org member can see their org's files.
create policy "files_select_if_member"
  on public.files
  for select
  to authenticated
  using (public.is_org_member(organization_id));

-- Insert: any org member can upload to their org. The row must claim
-- the org the caller is actually a member of — prevents cross-tenant
-- uploads via forged organization_id.
create policy "files_insert_if_member"
  on public.files
  for insert
  to authenticated
  with check (
    public.is_org_member(organization_id)
    and uploaded_by = auth.uid()
  );

-- Update: any member can update processing state / analysis of files in
-- their org. (The backend service role does most of this work, but we
-- want authenticated users to be able to, e.g., re-trigger processing
-- via API endpoints that run user-scoped queries.)
create policy "files_update_if_member"
  on public.files
  for update
  to authenticated
  using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

-- Delete: only admins and owners can delete files. Regular members
-- can upload and analyze but not remove. Destructive ops stay gated.
create policy "files_delete_if_admin_or_owner"
  on public.files
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.memberships m
      where m.organization_id = files.organization_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner')
    )
  );


-- ----------------------------------------------------------------------------
-- Trigger: keep updated_at fresh (reuse function from earlier migration)
-- ----------------------------------------------------------------------------
drop trigger if exists touch_files_updated_at on public.files;
create trigger touch_files_updated_at
  before update on public.files
  for each row
  execute function public.touch_updated_at();
