"""Supabase Storage integration.

Handles uploading file bytes to the 'uploads' bucket and generating
signed download URLs. All storage operations use the service-role client
because Supabase Storage's auth model differs from PostgREST — the
service-role client gives us reliable, predictable access.

Tenant isolation is enforced by:
1. The upload endpoint checking org membership before calling this module.
2. The storage RLS policies on storage.objects (backup layer).
3. The path convention embedding org_id as the first path segment.

This module does NOT make authorization decisions. It stores and retrieves
bytes at paths it's told to use. Authorization happens upstream.
"""

import uuid

from app.core.logging import get_logger
from app.db.client import get_supabase_admin

_log = get_logger(__name__)

BUCKET_NAME = "uploads"


class StorageUploadError(Exception):
    """Raised when a file upload to Supabase Storage fails."""


def build_storage_path(organization_id: str, safe_filename: str) -> str:
    """Build a unique storage path for a file.

    Convention: {org_id}/{unique_prefix}_{safe_filename}
    The unique prefix prevents collisions when the same filename is
    uploaded twice. The org_id prefix enables storage-layer RLS.
    """
    unique_prefix = uuid.uuid4().hex[:12]
    return f"{organization_id}/{unique_prefix}_{safe_filename}"


async def upload_file(
    *,
    storage_path: str,
    file_bytes: bytes,
    content_type: str,
) -> None:
    """Upload file bytes to Supabase Storage.

    Raises StorageUploadError if the upload fails for any reason.
    """
    client = get_supabase_admin()

    try:
        client.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
    except Exception as exc:
        message = str(exc).lower()
        _log.error(
            "storage_upload_failed",
            storage_path=storage_path,
            error=str(exc),
        )
        # Supabase returns a specific error for duplicate paths.
        if "duplicate" in message or "already exists" in message:
            raise StorageUploadError(f"A file already exists at path '{storage_path}'.") from exc
        raise StorageUploadError("Failed to upload file to storage.") from exc

    _log.info(
        "storage_upload_success",
        storage_path=storage_path,
        size_bytes=len(file_bytes),
    )
