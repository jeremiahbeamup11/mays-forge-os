"""Recovery service for files stuck in non-terminal processing states.

When the web server process restarts (e.g. Render spin-down/up), any
in-flight background analysis tasks are killed. Those files are left
in "pending", "parsing", or "analyzing" forever. This module finds
them and marks them as "failed" so the frontend shows an actionable
error instead of spinning indefinitely.

Used by:
- The startup lifespan hook (automatic on every boot)
- POST /admin/retry-stuck-files (manual trigger)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import create_client

from app.config import settings
from app.core.logging import get_logger

_log = get_logger(__name__)

STUCK_THRESHOLD_MINUTES = 5

NON_TERMINAL_STATUSES = ("pending", "parsing", "analyzing")


def _get_service_client() -> Any:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def recover_stuck_files() -> dict[str, Any]:
    """Find and mark stuck files as failed.

    A file is "stuck" if its processing_status is non-terminal and its
    updated_at is older than STUCK_THRESHOLD_MINUTES ago.

    Returns a summary dict with counts and file IDs.
    """
    client = _get_service_client()
    cutoff = (datetime.now(UTC) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)).isoformat()

    stuck_response = (
        client.table("files")
        .select("id, processing_status, original_filename, updated_at")
        .in_("processing_status", list(NON_TERMINAL_STATUSES))
        .lt("updated_at", cutoff)
        .execute()
    )

    stuck_files = stuck_response.data if isinstance(stuck_response.data, list) else []

    if not stuck_files:
        return {"found": 0, "recovered": 0, "file_ids": []}

    recovered_ids = []
    for file_row in stuck_files:
        file_id = file_row["id"]
        old_status = file_row.get("processing_status", "unknown")
        try:
            client.table("files").update(
                {
                    "processing_status": "failed",
                    "processing_error": (
                        f"Analysis was interrupted (server restart). "
                        f"Previous status: {old_status}. "
                        f"Use the retry button or re-upload to try again."
                    ),
                }
            ).eq("id", file_id).execute()
            recovered_ids.append(file_id)
            _log.info(
                "stuck_file_recovered",
                file_id=file_id,
                old_status=old_status,
                filename=file_row.get("original_filename"),
            )
        except Exception as exc:
            _log.error(
                "stuck_file_recovery_failed",
                file_id=file_id,
                error=str(exc),
            )

    return {
        "found": len(stuck_files),
        "recovered": len(recovered_ids),
        "file_ids": recovered_ids,
    }
