"""File upload endpoints.

Tenant-scoped: all file operations happen within an organization context.
The org_id is in the URL path, and RLS enforces that the caller is a
member of that org — both at the storage layer and the database layer.
"""

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.db.files import create_file_record, get_file_by_id, get_files_by_org
from app.models.file import FileRecord, FileUploadResponse
from app.services.ai_analyzer import (
    AnalysisError,
    AnalysisResult,
    analyze_csv,
    analyze_image,
    analyze_pdf,
    generate_blueprint,
)
from app.services.csv_parser import CsvParseError, parse_csv
from app.services.file_validation import FileValidationError, validate_upload
from app.services.pdf_parser import PdfParseError, parse_pdf
from app.services.report_generator import generate_csv_report, generate_image_report
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


def _get_service_client() -> Any:
    """Build a Supabase client with the service-role key (bypasses RLS)."""
    from supabase import create_client

    from app.config import settings

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def _update_file_status(
    file_id: str,
    *,
    processing_status: str,
    processing_error: str | None = None,
    analysis: dict[str, Any] | None = None,
) -> None:
    """Update a file's processing status and optionally attach analysis.

    Uses the service-role client so this works in background tasks
    where the original user token may have expired.
    """
    client = _get_service_client()
    update: dict[str, Any] = {"processing_status": processing_status}
    if processing_error is not None:
        update["processing_error"] = processing_error
    if analysis is not None:
        update["analysis"] = analysis
    client.table("files").update(update).eq("id", file_id).execute()


async def _analyze_csv_file(
    *,
    file_bytes: bytes,
    filename: str,
    file_id: str,
) -> AnalysisResult | None:
    """Parse and analyze a CSV file. Updates the file record with results.

    Returns the AnalysisResult on success, None on failure.
    Failures are logged and stored in the file record but do NOT cause
    the upload endpoint to fail — the file is already stored successfully,
    and analysis can be retried later.
    """
    # Phase 1: Parse
    try:
        await _update_file_status(file_id, processing_status="parsing")
        summary = parse_csv(file_bytes, filename)
    except CsvParseError as exc:
        _log.warning("csv_parse_failed", file_id=file_id, error=str(exc))
        await _update_file_status(
            file_id,
            processing_status="failed",
            processing_error=f"CSV parsing failed: {exc}",
        )
        return None

    # Phase 2: Analyze with Claude
    try:
        await _update_file_status(file_id, processing_status="analyzing")
        csv_context = summary.to_prompt_context()
        result = await analyze_csv(csv_context, filename)
    except AnalysisError as exc:
        _log.warning("ai_analysis_failed", file_id=file_id, error=str(exc))
        await _update_file_status(
            file_id,
            processing_status="failed",
            processing_error=f"AI analysis failed: {exc}",
        )
        return None

    # Phase 3: Store the result
    analysis_payload: dict[str, Any] = {
        "result": result.analysis,
        "metadata": {
            "prompt_version": result.prompt_version,
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "duration_seconds": result.duration_seconds,
            "estimated_cost_usd": result.estimated_cost_usd,
        },
        "csv_summary": summary.to_dict(),
    }

    await _update_file_status(
        file_id,
        processing_status="complete",
        analysis=analysis_payload,
    )

    _log.info(
        "file_analysis_stored",
        file_id=file_id,
        findings_count=len(result.analysis.get("findings", [])),
        recommendations_count=len(result.analysis.get("recommendations", [])),
    )
    return result


async def _analyze_pdf_file(
    *,
    file_bytes: bytes,
    filename: str,
    file_id: str,
) -> AnalysisResult | None:
    """Extract and analyze a PDF document. Updates the file record with results.

    Three-phase pipeline mirroring the CSV path:
    1. Deterministic extraction (tables + sections with page references)
    2. Claude analysis on the structured extraction
    3. Store results
    """
    # Phase 1: Extract (then release the raw PDF bytes)
    try:
        await _update_file_status(file_id, processing_status="parsing")
        extraction = parse_pdf(file_bytes, filename)
        del file_bytes  # Free ~2-5MB before the Claude API call
    except PdfParseError as exc:
        _log.warning("pdf_parse_failed", file_id=file_id, error=str(exc))
        await _update_file_status(
            file_id,
            processing_status="failed",
            processing_error=f"PDF extraction failed: {exc}",
        )
        return None

    # Phase 2: Analyze with Claude
    # Build the prompt context string, then let the extraction's heavy
    # table/section lists be GC'd while the API call is in flight.
    try:
        await _update_file_status(file_id, processing_status="analyzing")
        pdf_context = extraction.to_prompt_context()
        result = await analyze_pdf(pdf_context, filename)
    except AnalysisError as exc:
        _log.warning("pdf_analysis_failed", file_id=file_id, error=str(exc))
        await _update_file_status(
            file_id,
            processing_status="failed",
            processing_error=f"AI analysis failed: {exc}",
        )
        return None

    # Phase 3: Store the result
    # Note: We store extraction stats (not the full extraction) to keep the
    # JSONB payload reasonable. The full extraction can be re-derived from
    # the stored PDF if needed.
    analysis_payload: dict[str, Any] = {
        "result": result.analysis,
        "metadata": {
            "prompt_version": result.prompt_version,
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "duration_seconds": result.duration_seconds,
            "estimated_cost_usd": result.estimated_cost_usd,
        },
        "extraction_stats": {
            "page_count": extraction.page_count,
            "tables_extracted": len(extraction.tables),
            "sections_extracted": len(extraction.sections),
            "vision_pages": extraction.vision_pages,
            "parse_warnings": extraction.parse_warnings,
        },
    }

    await _update_file_status(
        file_id,
        processing_status="complete",
        analysis=analysis_payload,
    )

    _log.info(
        "pdf_analysis_stored",
        file_id=file_id,
        tables_extracted=len(extraction.tables),
        sections_extracted=len(extraction.sections),
        vision_pages=len(extraction.vision_pages),
        financial_findings=len(result.analysis.get("financial_findings", [])),
    )
    return result


async def _run_analysis_safe(
    *,
    kind: str,
    file_bytes: bytes,
    content_type: str,
    filename: str,
    file_id: str,
) -> None:
    """Crash-safe wrapper: guarantees the file reaches a terminal status.

    Any exception — known or unknown — results in status="failed" with the
    error message stored on the record. The file is never left stuck in
    "pending" or "analyzing".
    """
    try:
        if kind == "csv":
            await _analyze_csv_file(
                file_bytes=file_bytes,
                filename=filename,
                file_id=file_id,
            )
        elif kind == "image":
            await _analyze_image_file(
                file_bytes=file_bytes,
                content_type=content_type,
                filename=filename,
                file_id=file_id,
            )
        elif kind == "pdf":
            await _analyze_pdf_file(
                file_bytes=file_bytes,
                filename=filename,
                file_id=file_id,
            )
    except Exception as exc:
        _log.error(
            "analysis_unexpected_failure",
            file_id=file_id,
            kind=kind,
            error=str(exc),
            exc_info=True,
        )
        try:
            await _update_file_status(
                file_id,
                processing_status="failed",
                processing_error=f"Unexpected error during analysis: {exc}",
            )
        except Exception as status_exc:
            _log.error(
                "failed_to_set_failure_status",
                file_id=file_id,
                error=str(status_exc),
            )


@router.get(
    "",
    response_model=list[FileRecord],
    summary="List all files for an organization",
)
async def list_org_files(
    org_id: str,
    _user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> list[FileRecord]:
    """List all files for an organization, newest first."""
    token = _require_token(credentials)
    rows = await get_files_by_org(access_token=token, organization_id=org_id)
    return [FileRecord(**row) for row in rows]


@router.post(
    "",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file to an organization",
    description=(
        "Accepts a multipart file upload, validates it against size and "
        "type policies, stores the bytes in Supabase Storage, and creates "
        "a metadata record in the files table. For CSV files, automatically "
        "triggers AI analysis."
    ),
)
async def upload_org_file(
    org_id: str,
    file: UploadFile,
    user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    background_tasks: BackgroundTasks,
) -> FileUploadResponse:
    """Upload a file to an organization."""
    token = _require_token(credentials)

    # --- Read file bytes ---
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

    # --- Create database record ---
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record file metadata.",
        ) from exc

    record = FileRecord(**row)

    # --- Schedule analysis as a background task ---
    if validated.kind in ("csv", "image", "pdf"):
        background_tasks.add_task(
            _run_analysis_safe,
            kind=validated.kind,
            file_bytes=file_bytes,
            content_type=validated.content_type,
            filename=file.filename or validated.safe_filename,
            file_id=record.id,
        )

    return FileUploadResponse.from_record(record)


async def _analyze_image_file(
    *,
    file_bytes: bytes,
    content_type: str,
    filename: str,
    file_id: str,
) -> AnalysisResult | None:
    """Analyze an uploaded image with Claude Vision, then generate a blueprint.

    Two-stage pipeline:
    1. Image analysis — what does the site look like?
    2. Blueprint generation — what should we build here?
    """
    # Stage 1: Image analysis
    try:
        await _update_file_status(file_id, processing_status="analyzing")
        image_result = await analyze_image(file_bytes, content_type, filename)
    except AnalysisError as exc:
        _log.warning("image_analysis_failed", file_id=file_id, error=str(exc))
        await _update_file_status(
            file_id,
            processing_status="failed",
            processing_error=f"Image analysis failed: {exc}",
        )
        return None

    # Stage 2: Blueprint generation
    blueprint_result = None
    try:
        blueprint_result = await generate_blueprint(
            image_analysis=image_result.analysis,
            filename=filename,
        )
    except AnalysisError as exc:
        _log.warning("blueprint_generation_failed", file_id=file_id, error=str(exc))

    analysis_payload: dict[str, Any] = {
        "result": image_result.analysis,
        "metadata": {
            "prompt_version": image_result.prompt_version,
            "model": image_result.model,
            "input_tokens": image_result.input_tokens,
            "output_tokens": image_result.output_tokens,
            "duration_seconds": image_result.duration_seconds,
            "estimated_cost_usd": image_result.estimated_cost_usd,
        },
    }

    if blueprint_result:
        analysis_payload["blueprint"] = blueprint_result.analysis
        analysis_payload["blueprint_metadata"] = {
            "prompt_version": blueprint_result.prompt_version,
            "model": blueprint_result.model,
            "input_tokens": blueprint_result.input_tokens,
            "output_tokens": blueprint_result.output_tokens,
            "duration_seconds": blueprint_result.duration_seconds,
            "estimated_cost_usd": blueprint_result.estimated_cost_usd,
        }

    await _update_file_status(
        file_id,
        processing_status="complete",
        analysis=analysis_payload,
    )

    _log.info(
        "image_analysis_stored",
        file_id=file_id,
        observations_count=len(image_result.analysis.get("observations", [])),
        has_blueprint=blueprint_result is not None,
    )
    return image_result


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

    if record.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_id}' not found.",
        )

    return record


@router.get(
    "/{file_id}/report",
    summary="Download analysis report as PDF",
    description="Generates and returns a professional PDF report of the AI analysis.",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF report"},
        404: {"description": "File not found or analysis not complete"},
    },
)
async def download_report(
    org_id: str,
    file_id: str,
    _user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Response:
    """Generate and download a PDF report for a completed analysis."""
    token = _require_token(credentials)

    row = await get_file_by_id(access_token=token, file_id=file_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_id}' not found.",
        )

    record = FileRecord(**row)

    if record.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_id}' not found.",
        )

    if record.processing_status != "complete" or record.analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis is not yet complete for this file.",
        )

    # TODO: fetch org name from database. For now, use org_id.
    org_name = "Village of Peotone"

    raw_result = record.analysis.get("result") if isinstance(record.analysis, dict) else None
    raw_meta = record.analysis.get("metadata") if isinstance(record.analysis, dict) else None
    result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}

    if record.kind == "csv":
        pdf_bytes = generate_csv_report(
            org_name=org_name,
            filename=record.original_filename,
            analysis=result,
            metadata=meta,
        )
    elif record.kind == "image":
        raw_blueprint = (
            record.analysis.get("blueprint") if isinstance(record.analysis, dict) else None
        )
        blueprint_data: dict[str, Any] | None = (
            raw_blueprint if isinstance(raw_blueprint, dict) else None
        )
        pdf_bytes = generate_image_report(
            org_name=org_name,
            filename=record.original_filename,
            analysis=result,
            metadata=meta,
            blueprint=blueprint_data,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"PDF reports are not yet supported for '{record.kind}' files.",
        )

    safe_name = record.original_filename.rsplit(".", 1)[0]
    pdf_filename = f"{safe_name}_analysis_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'},
    )
