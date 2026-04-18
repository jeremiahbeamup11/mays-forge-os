"""Structured logging configuration.

Uses structlog to produce:
- Pretty, colorized, human-readable logs in development.
- JSON logs in staging/production, suitable for log aggregators like
  Render's log stream, Datadog, or Logtail.

Logs are structured, meaning every log line is a dict of key-value pairs.
This is vastly easier to query than unstructured text logs.
"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any, cast

import structlog
from structlog.types import Processor

from app.config import settings


def configure_logging() -> None:
    """Configure structlog and standard library logging.

    Called once at application startup from main.py.
    """
    # Shared processors run on every log call, regardless of output format.
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Redact any field named like a secret. Defense-in-depth: even if a
        # dev accidentally logs `api_key=...`, it gets scrubbed before output.
        _redact_sensitive_fields,
    ]

    if settings.is_development:
        # Pretty, colored output for humans.
        renderer: Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON for machines. Log aggregators love this.
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure the standard library logger so that uvicorn/fastapi
    # logs flow through our structlog pipeline instead of being printed raw.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


# Keys that should never appear in logs. Add more as you add more secrets.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "jwt",
        "anthropic_api_key",
        "gemini_api_key",
        "supabase_service_role_key",
        "jwt_secret",
    }
)


def _redact_sensitive_fields(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Replace any sensitive field values with `***REDACTED***`.

    Matches keys case-insensitively against a denylist. Belt-and-suspenders
    protection — the real defense is never logging secrets in the first place,
    but if someone slips up, this catches it.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Usage:
        log = get_logger(__name__)
        log.info("user_login", user_id=user.id, ip=request.client.host)
    """
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
