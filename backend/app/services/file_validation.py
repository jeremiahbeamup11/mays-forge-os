"""File upload validation.

Central policy module: decides which uploads the system accepts. Imported
by the upload endpoint — the endpoint never makes its own security
decisions, it delegates here.

Reasoning for each rejected category is documented in the README. Summary:
- Executables and scripts: malware distribution, social engineering.
- Archives: zip bombs, path traversal, smuggling blocked types.
- Anything not on the allowlist: principle of deny-by-default.

Full magic-byte content sniffing is deferred to a later iteration
(see docs/SECURITY.md once we write it). Current validation checks
declared content-type, file extension consistency, and size only.
"""

from dataclasses import dataclass

from app.models.file import FileKind

# Maximum accepted size for any single upload, in bytes.
# Keep conservative for v1; raise deliberately, not by accident.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB


# Allowlist: MIME type -> (FileKind, accepted extensions).
# Both MIME and extension are checked to catch the common "wrong extension
# for declared type" cases. Not a full defense (both are client-supplied
# and can be lied about), but a cheap first layer.
_ALLOWED_TYPES: dict[str, tuple[FileKind, tuple[str, ...]]] = {
    # Structured data
    "text/csv": ("csv", (".csv",)),
    "application/csv": ("csv", (".csv",)),
    "text/plain": ("other", (".txt", ".csv")),  # fallback for CSVs served as text/plain
    # Documents
    "application/pdf": ("pdf", (".pdf",)),
    # Images
    "image/jpeg": ("image", (".jpg", ".jpeg")),
    "image/png": ("image", (".png",)),
    "image/webp": ("image", (".webp",)),
    # GIS
    "application/geo+json": ("geojson", (".geojson", ".json")),
    "application/json": ("geojson", (".geojson", ".json")),
}


class FileValidationError(Exception):
    """Raised when an upload fails a validation check.

    The `reason` field is a short stable code suitable for API clients
    to handle programmatically; the exception message is human-readable.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ValidatedUpload:
    """The validated, kind-classified description of an incoming file."""

    kind: FileKind
    content_type: str
    size_bytes: int
    safe_filename: str


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    size_bytes: int,
) -> ValidatedUpload:
    """Validate an incoming upload against size, type, and filename rules.

    Raises FileValidationError on any failure. On success, returns a
    ValidatedUpload describing the file in normalized form.
    """
    if not filename:
        raise FileValidationError("missing_filename", "Filename is required.")

    if not content_type:
        raise FileValidationError("missing_content_type", "Content-Type is required on the upload.")

    if size_bytes <= 0:
        raise FileValidationError("empty_file", "Uploaded file is empty.")

    if size_bytes > MAX_UPLOAD_BYTES:
        raise FileValidationError(
            "file_too_large",
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit.",
        )

    normalized_type = content_type.lower().split(";")[0].strip()
    allowed = _ALLOWED_TYPES.get(normalized_type)
    if allowed is None:
        raise FileValidationError(
            "disallowed_content_type",
            f"Content type '{content_type}' is not allowed.",
        )

    kind, allowed_extensions = allowed
    safe_name = _sanitize_filename(filename)
    if not _has_allowed_extension(safe_name, allowed_extensions):
        raise FileValidationError(
            "extension_mismatch",
            (
                f"File extension does not match declared content-type "
                f"'{content_type}'. Expected one of: {', '.join(allowed_extensions)}."
            ),
        )

    return ValidatedUpload(
        kind=kind,
        content_type=normalized_type,
        size_bytes=size_bytes,
        safe_filename=safe_name,
    )


def _sanitize_filename(filename: str) -> str:
    """Return a filename safe for storage paths.

    Strips directory components (defeats simple path-traversal attempts),
    collapses whitespace, and drops characters that aren't safe in URLs
    or file paths. Preserves the extension.
    """
    # Drop any directory component. basename handles both / and \ on macOS/Linux;
    # we also strip backslashes explicitly for defense in depth.
    stem = filename.replace("\\", "/").rsplit("/", 1)[-1]
    stem = stem.strip()
    if not stem:
        return "upload"

    # Keep only alphanumerics, dot, hyphen, underscore. Everything else becomes _.
    safe_chars = []
    for ch in stem:
        if ch.isalnum() or ch in "._-":
            safe_chars.append(ch)
        else:
            safe_chars.append("_")
    cleaned = "".join(safe_chars).strip("._")

    # Hard cap to prevent absurdly long names breaking storage paths.
    if len(cleaned) > 200:
        # Preserve extension when truncating.
        if "." in cleaned:
            name, ext = cleaned.rsplit(".", 1)
            cleaned = name[: 200 - len(ext) - 1] + "." + ext
        else:
            cleaned = cleaned[:200]

    return cleaned or "upload"


def _has_allowed_extension(filename: str, allowed: tuple[str, ...]) -> bool:
    lowered = filename.lower()
    return any(lowered.endswith(ext) for ext in allowed)
