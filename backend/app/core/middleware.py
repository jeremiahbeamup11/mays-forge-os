"""HTTP middleware for request correlation and access logging.

Request correlation is the practice of assigning each incoming request a
unique ID that's propagated through all logs generated while handling it.
It's the single most important piece of observability infrastructure for
a backend service. Without it, debugging production incidents is like
trying to reconstruct a conversation from overlapping recordings.

This module provides:
- RequestIdMiddleware: assigns/propagates a unique ID per request.
- AccessLogMiddleware: logs one structured line per request with timing.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger

# Header name for request correlation. `X-Request-ID` is the de-facto
# standard across most HTTP infrastructure (proxies, load balancers, APMs).
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique ID to every request.

    If the incoming request already carries an X-Request-ID header (e.g.,
    set by an upstream proxy, load balancer, or another service), we respect
    it — this allows distributed tracing across service boundaries. Otherwise
    we generate a fresh UUID4.

    The ID is:
    - Stored in `request.state.request_id` for access in route handlers.
    - Bound to structlog's context vars so every log line emitted while
      handling this request automatically includes it.
    - Echoed back in the response's X-Request-ID header so clients can
      reference it when reporting issues.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        request_id: str
        if incoming_id is not None and _is_valid_request_id(incoming_id):
            request_id = incoming_id
        else:
            request_id = _generate_id()

        request.state.request_id = request_id

        # Bind to structlog's contextvars so all logs during this request
        # automatically include the ID without needing to pass it around.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
        finally:
            # Always clear context on the way out, even if the handler raised.
            # Prevents IDs from leaking across requests in async workers.
            structlog.contextvars.clear_contextvars()

        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per request with method, path, status, duration."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._log = get_logger("access")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        status_code = 500  # default if handler raises before setting one

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=status_code,
                duration_ms=duration_ms,
                client_ip=_client_ip(request),
            )


def _generate_id() -> str:
    """Generate a fresh request ID.

    UUID4 gives us 122 bits of randomness — more than enough to be
    globally unique in any realistic scenario.
    """
    return str(uuid.uuid4())


def _is_valid_request_id(value: str | None) -> bool:
    """Reject suspicious or malformed incoming request IDs.

    We accept IDs from clients, but only if they look reasonable. An
    attacker could otherwise inject control characters or absurdly long
    strings into log lines. Conservative bounds: 8-128 chars, printable ASCII.
    """
    if not value:
        return False
    if not (8 <= len(value) <= 128):
        return False
    return all(32 <= ord(c) < 127 for c in value)


def _client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For if behind a proxy.

    WARNING: X-Forwarded-For is client-supplied and can be spoofed unless
    you trust the proxy terminating it. In production on Render, Render
    sets it correctly. For now we read it but don't trust it for auth.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain (the original client).
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
