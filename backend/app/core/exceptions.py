"""Global exception handlers.

Purpose:
- Convert unhandled exceptions into a single consistent JSON shape.
- Log the full exception with request context for debugging.
- Never leak stack traces or internal paths to clients (security).

FastAPI and Starlette raise different exception types in different
situations. We handle all three:

- StarletteHTTPException: 404s from the router, HTTP errors from middleware.
- FastAPI HTTPException: errors raised deliberately from route handlers.
- RequestValidationError: Pydantic validation failures on request input.
- Exception: everything else — the catch-all for bugs.
"""

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

_log = get_logger("exceptions")


class ErrorResponse(BaseModel):
    """Standard error response shape returned to clients.

    Every error — validation, auth, server — uses this shape. Consistent
    error structure makes frontend error handling dramatically simpler.
    """

    error: str
    message: str
    request_id: str | None = None


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle known HTTP exceptions (including 404s from the router).

    Covers both FastAPI's HTTPException and Starlette's underlying
    HTTPException — the latter is what gets raised for 404s on unregistered
    routes. Registering once against StarletteHTTPException catches both
    since FastAPI's version is a subclass.
    """
    request_id = getattr(request.state, "request_id", None)
    _log.info(
        "http_exception",
        status=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=_status_to_slug(exc.status_code),
            message=str(exc.detail),
            request_id=request_id,
        ).model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors on request input.

    Raised automatically by FastAPI when request body, query params, or
    path params fail Pydantic validation. We return a consistent 422 with
    the field-level errors exposed — safe to expose since the client
    already sent the invalid data.

    Pydantic's error details can contain non-JSON-serializable objects in
    the `ctx` field (e.g., ValueError instances from custom validators).
    We use jsonable_encoder to coerce everything into JSON-safe forms
    before serialization.
    """
    request_id = getattr(request.state, "request_id", None)
    errors = exc.errors()
    _log.info(
        "validation_error",
        path=request.url.path,
        errors=errors,
    )
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {
                "error": "unprocessable_entity",
                "message": "Request validation failed.",
                "request_id": request_id,
                "details": errors,
            }
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for exceptions the app didn't anticipate.

    Security note: we log the full exception (with traceback) but the
    client response contains only a generic message. Exposing internal
    errors to clients leaks library versions, file paths, SQL structure,
    etc., all of which help attackers map the system.
    """
    request_id = getattr(request.state, "request_id", None)
    _log.exception(
        "unhandled_exception",
        path=request.url.path,
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_server_error",
            message="An unexpected error occurred. Please try again later.",
            request_id=request_id,
        ).model_dump(),
    )


def _status_to_slug(status_code: int) -> str:
    """Map HTTP status codes to machine-readable slugs."""
    mapping = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "unprocessable_entity",
        429: "too_many_requests",
        500: "internal_server_error",
        502: "bad_gateway",
        503: "service_unavailable",
    }
    return mapping.get(status_code, "error")


# Keep HTTPException import for backwards-compat with existing imports.
__all__ = [
    "ErrorResponse",
    "HTTPException",
    "http_exception_handler",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
