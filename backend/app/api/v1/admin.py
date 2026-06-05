"""Admin endpoints for operational recovery.

These endpoints are not user-facing. They exist so operators can
recover from infrastructure failures (e.g. process restarts that
orphan in-progress analysis jobs) without a redeploy.
"""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, status

from app.core.logging import get_logger
from app.services.stuck_files import recover_stuck_files

router = APIRouter(prefix="/admin", tags=["admin"])

_log = get_logger(__name__)


@router.post(
    "/retry-stuck-files",
    status_code=status.HTTP_200_OK,
    summary="Re-queue files stuck in non-terminal status",
    description=(
        "Finds files stuck in 'pending', 'parsing', or 'analyzing' for more "
        "than 5 minutes and marks them as 'failed' with an error message. "
        "For files that still have their bytes in storage, a future version "
        "can re-trigger analysis; for now this unblocks the UI."
    ),
)
async def retry_stuck_files(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Mark stuck files as failed so the frontend stops spinning."""
    result = await recover_stuck_files()

    _log.info(
        "admin_retry_stuck_files",
        found=result["found"],
        recovered=result["recovered"],
    )

    return result
