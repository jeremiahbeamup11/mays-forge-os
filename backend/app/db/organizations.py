"""Database access for the organizations domain.

This module centralizes all Supabase queries related to organizations and
memberships. Keeping DB access in one place means:

- Route handlers stay thin — they only orchestrate, not query.
- If we ever swap Supabase for something else, only this file changes.
- Security-sensitive patterns (which client to use, how to scope queries)
  live in one auditable spot.
"""

from typing import Any

from supabase import Client, create_client

from app.config import settings


def get_user_scoped_client(access_token: str) -> Client:
    """Return a Supabase client that runs queries AS the authenticated user.

    RLS policies use `auth.uid()` to decide what rows to return. For that to
    work, the client has to carry the user's JWT in its Authorization header.

    Building a fresh client per request is cheap (supabase-py is a thin
    wrapper around httpx). We intentionally DO NOT cache these by token —
    that would be a session-fixation risk.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client


async def list_memberships_for_user(access_token: str) -> list[dict[str, Any]]:
    """Return all (membership, organization) pairs for the current user.

    The Supabase client enforces our RLS policies, so this query only ever
    returns rows belonging to the authenticated caller — even if a bug
    caused us to omit a WHERE clause, the database itself would filter.
    """
    client = get_user_scoped_client(access_token)

    response = (
        client.table("memberships")
        .select("role, organization:organizations(id, name, slug, created_at, updated_at)")
        .execute()
    )

    data = response.data
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


class OrganizationSlugConflictError(Exception):
    """Raised when the requested slug is already taken.

    Surfaced to the API layer as HTTP 409 Conflict with a helpful message.
    """


async def create_organization(
    *,
    access_token: str,
    name: str,
    slug: str,
) -> dict[str, Any]:
    """Create a new organization and return it.

    The `handle_new_organization` trigger automatically creates a
    membership row making the caller an 'owner'. We don't need to do that
    explicitly here — the database handles it atomically.

    Raises OrganizationSlugConflict if the slug is already taken.
    """
    client = get_user_scoped_client(access_token)

    try:
        response = client.table("organizations").insert({"name": name, "slug": slug}).execute()
    except Exception as exc:
        # Supabase surfaces unique-constraint violations as exceptions with
        # 'duplicate' or '23505' in the message. Rather than parsing error
        # codes out of strings, we check for the specific failure modes
        # we know about and re-raise as typed exceptions.
        message = str(exc).lower()
        if "duplicate" in message or "23505" in message or "unique" in message:
            raise OrganizationSlugConflictError(
                f"An organization with slug '{slug}' already exists."
            ) from exc
        raise

    data = response.data
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError("Unexpected response shape from organizations insert.")
    return data[0]
