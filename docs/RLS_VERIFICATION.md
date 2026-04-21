# RLS Verification

Manual procedure to verify Row-Level Security is correctly enforcing tenant isolation on the `organizations` and `memberships` tables.

Run this any time you change an RLS policy, add a new tenant-scoped table, or want to sanity-check before a demo.

## When to run

- After changing any RLS policy
- After changing the `is_org_member` helper function
- After modifying the `handle_new_organization` trigger
- Before any deployment to a new environment
- Before showing the app to an external user (e.g., Bob)

## Procedure

Open Supabase SQL Editor and run each block below **separately**, noting the row count for each test.

### Setup

```sql
insert into auth.users (id, email, instance_id, aud, role)
values
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'alice@rls.test',
   '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'bob@rls.test',
   '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated');

set local role authenticated;
set local request.jwt.claims = '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated"}';
insert into public.organizations (id, name, slug, created_by)
values ('11111111-1111-1111-1111-111111111111', 'Peotone RLS Test', 'peotone-rls-test',
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');

reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated"}';
insert into public.organizations (id, name, slug, created_by)
values ('22222222-2222-2222-2222-222222222222', 'Naperville RLS Test', 'naperville-rls-test',
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');

reset role;
select 'Setup complete' as status;
```

### Test 1 — Alice sees her own org (expect 1)

```sql
set local role authenticated;
set local request.jwt.claims = '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated"}';
select count(*) as alice_org_count from public.organizations;
```

### Test 2 — Alice cannot read Naperville by ID (expect 0)

```sql
set local role authenticated;
set local request.jwt.claims = '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated"}';
select count(*) as alice_sees_naperville
from public.organizations
where id = '22222222-2222-2222-2222-222222222222';
```

### Test 3 — Alice sees only her own memberships (expect 1)

```sql
set local role authenticated;
set local request.jwt.claims = '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated"}';
select count(*) as alice_membership_count from public.memberships;
```

### Test 4 — Alice cannot update Naperville (expect 0)

```sql
set local role authenticated;
set local request.jwt.claims = '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated"}';
with attempt as (
  update public.organizations
  set name = 'Hacked by Alice'
  where id = '22222222-2222-2222-2222-222222222222'
  returning id
)
select count(*) as rows_alice_could_update from attempt;
```

### Test 5 — Bob has symmetric access to his own org (expect 1)

```sql
set local role authenticated;
set local request.jwt.claims = '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated"}';
select count(*) as bob_org_count from public.organizations;
```

### Test 6 — Anonymous users see no orgs (expect 0)

```sql
set local role anon;
select count(*) as anon_org_count from public.organizations;
```

### Cleanup — ALWAYS run after testing

```sql
reset role;
delete from public.organizations
where id in ('11111111-1111-1111-1111-111111111111',
             '22222222-2222-2222-2222-222222222222');
delete from auth.users
where id in ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
             'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
select 'Cleanup complete' as status;
```

## Expected Results

Passing run: `1, 0, 1, 0, 1, 0`

If any number is wrong, the RLS policy for that operation is broken. **Do not deploy** until the discrepancy is understood and fixed.

## History

| Date | Result | Notes |
|------|--------|-------|
| 2026-04-20 | 1, 0, 1, 0, 1, 0 ✓ | Initial verification after Phase 2 Part B. All six tests passed. |

Append a row each time you re-run.
