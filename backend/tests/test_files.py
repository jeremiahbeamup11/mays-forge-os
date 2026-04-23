"""Tests for the file upload and retrieval endpoints.

Scope:
- Validation logic (size, type, extension)
- Upload endpoint auth enforcement
- Upload endpoint happy path (mocked storage + db)
- Retrieval endpoint happy path + 404
- Edge cases (empty files, wrong extensions, oversized)

Out of scope:
- Actual Supabase Storage uploads (tested via manual verification)
- RLS enforcement (verified manually via SQL Editor)
"""

from collections.abc import Callable
from io import BytesIO
from typing import Any

import pytest
from httpx import AsyncClient

TokenFactory = Callable[..., str]

ORG_ID = "11111111-1111-1111-1111-111111111111"
UPLOAD_URL = f"/api/v1/organizations/{ORG_ID}/files"


def _make_upload_file(
    content: bytes = b"col1,col2\nval1,val2\n",
    filename: str = "test_data.csv",
    content_type: str = "text/csv",
) -> dict[str, Any]:
    """Build the 'files' dict that httpx uses for multipart uploads."""
    return {"file": (filename, BytesIO(content), content_type)}


# ============================================================================
# Validation tests (no mocking needed — these fail before hitting storage/db)
# ============================================================================


class TestUploadValidation:
    """Validation rejects bad uploads before they touch storage or DB."""

    async def test_no_auth_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(UPLOAD_URL, files=_make_upload_file())
        assert response.status_code == 401

    async def test_empty_file_returns_422(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        token = make_token()
        response = await client.post(
            UPLOAD_URL,
            files=_make_upload_file(content=b""),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert "empty" in response.json()["message"].lower()

    async def test_disallowed_content_type_returns_422(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        token = make_token()
        response = await client.post(
            UPLOAD_URL,
            files=_make_upload_file(
                content=b"MZ\x90\x00",  # PE header bytes
                filename="malware.exe",
                content_type="application/x-msdownload",
            ),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert "not allowed" in response.json()["message"].lower()

    async def test_extension_mismatch_returns_422(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        """A file claiming to be CSV but with a .pdf extension is rejected."""
        token = make_token()
        response = await client.post(
            UPLOAD_URL,
            files=_make_upload_file(
                content=b"col1,col2\nval1,val2\n",
                filename="data.pdf",
                content_type="text/csv",
            ),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert "extension" in response.json()["message"].lower()


# ============================================================================
# Upload happy path (storage + db mocked)
# ============================================================================


class TestUploadHappyPath:
    """Successful uploads with mocked storage and database."""

    async def test_csv_upload_returns_201(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_upload(*, storage_path: str, file_bytes: bytes, content_type: str) -> None:
            pass  # Pretend storage succeeded.

        async def fake_create_record(**kwargs: Any) -> dict[str, Any]:
            return {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "organization_id": kwargs["organization_id"],
                "uploaded_by": kwargs["uploaded_by"],
                "original_filename": kwargs["original_filename"],
                "content_type": kwargs["content_type"],
                "size_bytes": kwargs["size_bytes"],
                "kind": kwargs["kind"],
                "storage_bucket": kwargs["storage_bucket"],
                "storage_path": kwargs["storage_path"],
                "processing_status": "pending",
                "processing_error": None,
                "analysis": None,
                "created_at": "2026-04-21T00:00:00+00:00",
                "updated_at": "2026-04-21T00:00:00+00:00",
            }

        monkeypatch.setattr("app.api.v1.files.upload_file", fake_upload)
        monkeypatch.setattr("app.api.v1.files.create_file_record", fake_create_record)

        token = make_token()
        response = await client.post(
            UPLOAD_URL,
            files=_make_upload_file(),
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["kind"] == "csv"
        assert data["processing_status"] == "pending"
        assert data["organization_id"] == ORG_ID
        assert data["original_filename"] == "test_data.csv"
        assert data["size_bytes"] > 0

    async def test_image_upload_returns_201(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_upload(*, storage_path: str, file_bytes: bytes, content_type: str) -> None:
            pass

        async def fake_create_record(**kwargs: Any) -> dict[str, Any]:
            return {
                "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "organization_id": kwargs["organization_id"],
                "uploaded_by": kwargs["uploaded_by"],
                "original_filename": kwargs["original_filename"],
                "content_type": kwargs["content_type"],
                "size_bytes": kwargs["size_bytes"],
                "kind": kwargs["kind"],
                "storage_bucket": kwargs["storage_bucket"],
                "storage_path": kwargs["storage_path"],
                "processing_status": "pending",
                "processing_error": None,
                "analysis": None,
                "created_at": "2026-04-21T00:00:00+00:00",
                "updated_at": "2026-04-21T00:00:00+00:00",
            }

        monkeypatch.setattr("app.api.v1.files.upload_file", fake_upload)
        monkeypatch.setattr("app.api.v1.files.create_file_record", fake_create_record)

        token = make_token()
        # Minimal valid JPEG header
        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        response = await client.post(
            UPLOAD_URL,
            files=_make_upload_file(
                content=jpeg_bytes,
                filename="vacant_lot.jpg",
                content_type="image/jpeg",
            ),
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        assert response.json()["kind"] == "image"

    async def test_upload_response_excludes_storage_path(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Storage internals must not leak to clients."""

        async def fake_upload(**kwargs: Any) -> None:
            pass

        async def fake_create_record(**kwargs: Any) -> dict[str, Any]:
            return {
                "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "organization_id": kwargs["organization_id"],
                "uploaded_by": kwargs["uploaded_by"],
                "original_filename": kwargs["original_filename"],
                "content_type": kwargs["content_type"],
                "size_bytes": kwargs["size_bytes"],
                "kind": kwargs["kind"],
                "storage_bucket": "uploads",
                "storage_path": f"{ORG_ID}/abc_test.csv",
                "processing_status": "pending",
                "processing_error": None,
                "analysis": None,
                "created_at": "2026-04-21T00:00:00+00:00",
                "updated_at": "2026-04-21T00:00:00+00:00",
            }

        monkeypatch.setattr("app.api.v1.files.upload_file", fake_upload)
        monkeypatch.setattr("app.api.v1.files.create_file_record", fake_create_record)

        token = make_token()
        response = await client.post(
            UPLOAD_URL,
            files=_make_upload_file(),
            headers={"Authorization": f"Bearer {token}"},
        )
        body = response.json()
        assert "storage_path" not in body
        assert "storage_bucket" not in body


# ============================================================================
# Retrieval tests
# ============================================================================


class TestGetFile:
    """Tests for GET /api/v1/organizations/{org_id}/files/{file_id}."""

    async def test_no_auth_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(f"{UPLOAD_URL}/some-file-id")
        assert response.status_code == 401

    async def test_file_not_found_returns_404(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_get(*, access_token: str, file_id: str) -> None:
            return None

        monkeypatch.setattr("app.api.v1.files.get_file_by_id", fake_get)

        token = make_token()
        response = await client.get(
            f"{UPLOAD_URL}/nonexistent-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    async def test_file_from_wrong_org_returns_404(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Belt-and-suspenders: even if RLS leaks, the endpoint catches org mismatch."""

        async def fake_get(*, access_token: str, file_id: str) -> dict[str, Any]:
            return {
                "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "organization_id": "99999999-9999-9999-9999-999999999999",
                "uploaded_by": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "original_filename": "leaked.csv",
                "content_type": "text/csv",
                "size_bytes": 100,
                "kind": "csv",
                "storage_bucket": "uploads",
                "storage_path": "99999999/leaked.csv",
                "processing_status": "pending",
                "processing_error": None,
                "analysis": None,
                "created_at": "2026-04-21T00:00:00+00:00",
                "updated_at": "2026-04-21T00:00:00+00:00",
            }

        monkeypatch.setattr("app.api.v1.files.get_file_by_id", fake_get)

        token = make_token()
        response = await client.get(
            f"{UPLOAD_URL}/dddddddd-dddd-dddd-dddd-dddddddddddd",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Must be 404, not 200 — the file belongs to a different org.
        assert response.status_code == 404


# ============================================================================
# Validation unit tests (direct function, no HTTP)
# ============================================================================


class TestValidationFunction:
    """Direct tests of the validate_upload function."""

    def test_valid_csv(self) -> None:
        from app.services.file_validation import validate_upload

        result = validate_upload(filename="data.csv", content_type="text/csv", size_bytes=100)
        assert result.kind == "csv"
        assert result.safe_filename == "data.csv"

    def test_valid_pdf(self) -> None:
        from app.services.file_validation import validate_upload

        result = validate_upload(
            filename="report.pdf",
            content_type="application/pdf",
            size_bytes=5000,
        )
        assert result.kind == "pdf"

    def test_valid_jpeg(self) -> None:
        from app.services.file_validation import validate_upload

        result = validate_upload(
            filename="photo.jpg",
            content_type="image/jpeg",
            size_bytes=2048,
        )
        assert result.kind == "image"

    def test_path_traversal_stripped(self) -> None:
        from app.services.file_validation import validate_upload

        result = validate_upload(
            filename="../../../data.csv",
            content_type="text/csv",
            size_bytes=50,
        )
        assert "/" not in result.safe_filename
        assert ".." not in result.safe_filename
        assert result.safe_filename.endswith(".csv")

    def test_oversized_rejected(self) -> None:
        from app.services.file_validation import FileValidationError, validate_upload

        with pytest.raises(FileValidationError, match="limit"):
            validate_upload(
                filename="huge.csv",
                content_type="text/csv",
                size_bytes=30 * 1024 * 1024,
            )

    def test_exe_rejected(self) -> None:
        from app.services.file_validation import FileValidationError, validate_upload

        with pytest.raises(FileValidationError, match="not allowed"):
            validate_upload(
                filename="malware.exe",
                content_type="application/x-msdownload",
                size_bytes=1024,
            )

    def test_zip_rejected(self) -> None:
        from app.services.file_validation import FileValidationError, validate_upload

        with pytest.raises(FileValidationError, match="not allowed"):
            validate_upload(
                filename="archive.zip",
                content_type="application/zip",
                size_bytes=1024,
            )
