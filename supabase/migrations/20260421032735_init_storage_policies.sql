-- ============================================================================
-- Migration: init_storage_policies
-- ============================================================================
-- RLS policies for the 'uploads' Supabase Storage bucket.
--
-- Path convention: every object is stored at {organization_id}/{rest-of-path}
-- where organization_id is the UUID of the owning org. The first segment of
-- the object's name is the org's UUID — we extract it and check membership.
--
-- Four policies (SELECT/INSERT/UPDATE/DELETE), same shape as the files table.
-- Without these, bucket access defaults to denied for authenticated users,
-- which is why this migration must ship before any upload code runs.
-- ============================================================================


-- Read: org members can read any object under their org's path prefix.
-- storage.foldername(name) returns the array of path segments; [1] is the
-- first segment. Cast to uuid so it can be compared to organization_id.
create policy "uploads_read_if_member"
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'uploads'
    and public.is_org_member(
      (storage.foldername(name))[1]::uuid
    )
  );

-- Write: org members can upload new objects into their org's path prefix.
-- The 'with check' clause runs on the NEW row being inserted.
create policy "uploads_write_if_member"
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'uploads'
    and public.is_org_member(
      (storage.foldername(name))[1]::uuid
    )
  );

-- Update: org members can update metadata on objects in their org.
-- (Rarely used directly, but covers overwrite-upload operations.)
create policy "uploads_update_if_member"
  on storage.objects
  for update
  to authenticated
  using (
    bucket_id = 'uploads'
    and public.is_org_member(
      (storage.foldername(name))[1]::uuid
    )
  )
  with check (
    bucket_id = 'uploads'
    and public.is_org_member(
      (storage.foldername(name))[1]::uuid
    )
  );

-- Delete: admins and owners only. Same stricter pattern as the files table.
create policy "uploads_delete_if_admin_or_owner"
  on storage.objects
  for delete
  to authenticated
  using (
    bucket_id = 'uploads'
    and exists (
      select 1
      from public.memberships m
      where m.user_id = auth.uid()
        and m.organization_id = (storage.foldername(name))[1]::uuid
        and m.role in ('admin', 'owner')
    )
  );
