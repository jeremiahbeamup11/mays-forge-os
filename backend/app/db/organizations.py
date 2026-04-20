"""Database access for the organizations domain.

This module centralizes all Supabase queries related to organizations and
memberships. Keeping DB access in one place means:

- Route handlers stay thin — they only orchestrate, not query.
- If we ever swap Supabase for something else, only this file changes.
- Security-sensitive patterns (which client to use, how to scope queries)
  live in one auditable spot.

Client choice:
- Queries that must respect the caller's tenant scoping use a per-request
  client that carries the caller's JWT, so RLS policies filter correctly.
- The global `get_supabase_anon()` client is only safe for operations that
  don't depend on user identity (there aren't many).
"""

from supabase import Client, create_client

from app.config import settings


def get_user_scoped_client(access_token: str) -> Client:
    """Return a Supabase client that runs queries AS the authenticated user.

    RLS policies use `auth.uid()` to decide what rows to return. For that to
    work, the client has to carry the user's JWT in its Authorization header.
    Supabase's Postgres role is set to `authenticated` rather than `anon`,
    and auth.uid() returns the sub claim from the JWT.

    Building a fresh client per request is cheap (supabase-py is a thin
    wrapper around httpx). We intentionally DO NOT cache these by token —
    that would be a session-fixation risk.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client


async def list_memberships_for_user(access_token: str) -> list[dict[str, object]]:
    """Return all (membership, organization) pairs for the current user.

    The Supabase client enforces our RLS policies, so this query only ever
    returns rows belonging to the authenticated caller — even if a bug
    caused us to omit a WHERE clause, the database itself would filter.

    Response shape per row:
        {
            "role": "owner" | "admin" | "member",
            "organization": { id, name, slug, created_at, updated_at }
        }
    """
    client = get_user_scoped_client(access_token)

    response = (
        client.table("memberships")
        .select("role, organization:organizations(id, name, slug, created_at, updated_at)")
        .execute()
    )

    # supabase-py returns a typed response object with .data holding the rows.
    # We narrow it to a list of dicts for the caller.
    data = response.data
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]
