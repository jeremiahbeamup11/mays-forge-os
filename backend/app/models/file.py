"""Pydantic models for the file upload domain.

Mirrors the columns in public.files (see 20260421031630_init_files.sql).
Two separate model surfaces:

- Internal models (FileRecord) reflect exactly what's in the database.
- API response models (FileResponse) may hide or reshape fields for the
  external contract.

Right now they're mostly identical, but keeping them separate lets us
evolve one without breaking the other.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirrors public.file_kind enum.
FileKind = Literal["csv", "pdf", "image", "geojson", "other"]

# Mirrors public.file_processing_status enum.
FileProcessingStatus = Literal["pending", "parsing", "analyzing", "complete", "failed"]


class FileRecord(BaseModel):
    """Full representation of a file row from the database."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="File UUID.")
    organization_id: str = Field(description="Owning organization UUID.")
    uploaded_by: str | None = Field(
        default=None,
        description="User UUID who uploaded. May be null if user was removed.",
    )

    original_filename: str = Field(description="Filename as provided by the client.")
    content_type: str = Field(description="MIME type of the upload.")
    size_bytes: int = Field(ge=0, description="Size in bytes.")
    kind: FileKind = Field(description="High-level file category.")

    storage_bucket: str = Field(description="Supabase Storage bucket name.")
    storage_path: str = Field(description="Object path inside the bucket.")

    processing_status: FileProcessingStatus = Field(
        description="Where the file is in the ingest/analyze lifecycle."
    )
    processing_error: str | None = Field(
        default=None, description="Error message if processing_status is 'failed'."
    )

    analysis: dict[str, object] | None = Field(
        default=None,
        description="Structured AI analysis. Shape depends on kind. Null until complete.",
    )

    created_at: datetime
    updated_at: datetime


class FileUploadResponse(BaseModel):
    """Response shape for POST /api/v1/organizations/{org_id}/files.

    Mirrors FileRecord but scoped to fields worth returning right after
    upload. We intentionally omit storage_bucket and storage_path — those
    are internal pointers, not part of the public API contract. Clients
    get signed download URLs via a separate endpoint.
    """

    id: str
    organization_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    kind: FileKind
    processing_status: FileProcessingStatus
    created_at: datetime

    @classmethod
    def from_record(cls, record: FileRecord) -> "FileUploadResponse":
        return cls(
            id=record.id,
            organization_id=record.organization_id,
            original_filename=record.original_filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            kind=record.kind,
            processing_status=record.processing_status,
            created_at=record.created_at,
        )
