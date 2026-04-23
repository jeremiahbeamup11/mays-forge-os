"""File upload endpoints.

Tenant-scoped: all file operations happen within an organization context.
The org_id is in the URL path, and RLS enforces that the caller is a
member of that org — both at the storage layer and the database layer.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.db.files import create_file_record, get_file_by_id
from app.models.file import FileRecord, FileUploadResponse
from app.services.file_validation import FileValidationError, validate_upload
from app.services.storage import (
    BUCKET_NAME,
    StorageUploadError,
    build_storage_path,
    upload_file,
)

router = APIRouter(prefix="/organizations/{org_id}/files", tags=["files"])

_bearer = HTTPBearer(auto_error=False)
_log = get_logger(__name__)


def _require_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials.",
        )
    return credentials.credentials


@router.post(
    "",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file to an organization",
    description=(
        "Accepts a multipart file upload, validates it against size and "
        "type policies, stores the bytes in Supabase Storage, and creates "
        "a metadata record in the files table. Returns the file metadata "
        "with processing_status='pending'."
    ),
)
async def upload_org_file(
    org_id: str,
    file: UploadFile,
    user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> FileUploadResponse:
    """Upload a file to an organization."""
    token = _require_token(credentials)

    # --- Read file bytes (enforces size limit implicitly) ---
    file_bytes = await file.read()
    size = len(file_bytes)

    # --- Validate ---
    try:
        validated = validate_upload(
            filename=file.filename,
            content_type=file.content_type,
            size_bytes=size,
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Upload rejected: {exc}",
        ) from exc

    # --- Build storage path and upload bytes ---
    storage_path = build_storage_path(org_id, validated.safe_filename)

    try:
        await upload_file(
            storage_path=storage_path,
            file_bytes=file_bytes,
            content_type=validated.content_type,
        )
    except StorageUploadError as exc:
        _log.error(
            "upload_endpoint_storage_failed",
            org_id=org_id,
            filename=validated.safe_filename,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store file. Please try again.",
        ) from exc

    # --- Create database record (user-scoped: RLS double-checks org membership) ---
    try:
        row = await create_file_record(
            access_token=token,
            organization_id=org_id,
            uploaded_by=user.id,
            original_filename=file.filename or validated.safe_filename,
            content_type=validated.content_type,
            size_bytes=validated.size_bytes,
            kind=validated.kind,
            storage_bucket=BUCKET_NAME,
            storage_path=storage_path,
        )
    except Exception as exc:
        _log.error(
            "upload_endpoint_db_failed",
            org_id=org_id,
            filename=validated.safe_filename,
            error=str(exc),
        )
        # TODO: clean up orphaned storage object. For now, accept the risk
        # of an orphan — it's wasted space but not a security issue.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record file metadata.",
        ) from exc

    record = FileRecord(**row)
    return FileUploadResponse.from_record(record)


@router.get(
    "/{file_id}",
    response_model=FileRecord,
    summary="Get file metadata by ID",
    description="Returns the metadata and analysis (if complete) for a single file.",
)
async def get_org_file(
    org_id: str,
    file_id: str,
    _user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> FileRecord:
    """Retrieve a single file's metadata. RLS scopes to caller's orgs."""
    token = _require_token(credentials)

    row = await get_file_by_id(access_token=token, file_id=file_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_id}' not found.",
        )

    record = FileRecord(**row)

    # Extra safety: even if RLS somehow returned a row from another org
    # (it shouldn't), reject it here. Belt and suspenders.
    if record.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_id}' not found.",
        )

    return record
