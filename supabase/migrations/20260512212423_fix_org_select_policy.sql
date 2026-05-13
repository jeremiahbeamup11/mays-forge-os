-- ============================================================================
-- Migration: fix_org_select_policy
-- ============================================================================
-- Fixes a chicken-and-egg timing issue with INSERT ... RETURNING.
--
-- Problem: When inserting a new organization, PostgreSQL evaluates the
-- SELECT RLS policy on the RETURNING clause. The AFTER INSERT trigger
-- that creates the creator's membership hasn't fired yet at that point,
-- so is_org_member(id) returns false and RETURNING is blocked — causing
-- the entire insert to fail with an RLS violation.
--
-- Fix: Allow SELECT on orgs where the caller is either a member OR the
-- creator. The created_by column is set during the same INSERT, so it's
-- available when RETURNING evaluates.
-- ============================================================================

-- Drop the old policy
drop policy if exists "organizations_select_if_member" on public.organizations;

-- Create the fixed policy: member OR creator can see the org
create policy "organizations_select_if_member_or_creator"
  on public.organizations
  for select
  to authenticated
  using (
    public.is_org_member(id)
    or created_by = auth.uid()
  );
