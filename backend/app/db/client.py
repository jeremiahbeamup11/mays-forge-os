"""Supabase client factory.

Two clients are exposed:

- `get_supabase_anon()` — uses the anon/public key. Respects Row-Level
  Security. Used for the vast majority of operations where RLS policies
  should filter data to the calling user.

- `get_supabase_admin()` — uses the service_role key. BYPASSES RLS.
  Used only for trusted admin operations (e.g., provisioning a new org,
  background jobs, migrations). Never pass user-controlled data into
  queries made through this client without re-applying authorization
  manually.

Both are cached (instantiated once per process) via lru_cache.
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache
def get_supabase_anon() -> Client:
    """Supabase client using the anon key. Respects Row-Level Security."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


@lru_cache
def get_supabase_admin() -> Client:
    """Supabase client using the service_role key. Bypasses RLS.

    Only use this for trusted server-side operations. Never construct
    queries from user-provided data without authorization checks.
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
