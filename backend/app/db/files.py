"""Database access for the files domain.

Mirrors the pattern in db/organizations.py:
- User-scoped client for queries that should respect RLS.
- Typed exceptions for known failure modes.
- Returns raw dicts that the API layer converts to Pydantic models.
"""

from typing import Any, cast

from app.core.logging import get_logger
from app.db.organizations import get_user_scoped_client

_log = get_logger(__name__)


async def create_file_record(
    *,
    access_token: str,
    organization_id: str,
    uploaded_by: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    kind: str,
    storage_bucket: str,
    storage_path: str,
) -> dict[str, Any]:
    """Insert a new file row. Uses user-scoped client so RLS validates
    that the caller is actually a member of the target organization.

    Returns the inserted row as a dict.
    """
    client = get_user_scoped_client(access_token)

    row: dict[str, Any] = {
        "organization_id": organization_id,
        "uploaded_by": uploaded_by,
        "original_filename": original_filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "kind": kind,
        "storage_bucket": storage_bucket,
        "storage_path": storage_path,
        "processing_status": "pending",
    }

    try:
        response = client.table("files").insert(row).execute()
    except Exception as exc:
        _log.error(
            "file_record_insert_failed",
            organization_id=organization_id,
            filename=original_filename,
            error=str(exc),
        )
        raise

    data = response.data
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError("Unexpected response shape from files insert.")

    _log.info(
        "file_record_created",
        file_id=data[0].get("id"),
        organization_id=organization_id,
        filename=original_filename,
    )
    return cast(dict[str, Any], data[0])


async def get_file_by_id(
    *,
    access_token: str,
    file_id: str,
) -> dict[str, Any] | None:
    """Fetch a single file by ID. RLS ensures the caller can only see
    files belonging to orgs they're a member of.

    Returns the row dict, or None if not found (or not visible due to RLS).
    """
    client = get_user_scoped_client(access_token)

    response = client.table("files").select("*").eq("id", file_id).execute()

    data = response.data
    if not isinstance(data, list) or not data:
        return None
    row = data[0]
    if not isinstance(row, dict):
        return None
    return cast(dict[str, Any], row)
