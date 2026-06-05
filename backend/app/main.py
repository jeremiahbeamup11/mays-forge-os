"""FastAPI application entry point.

Responsibilities of this file:
- Create the FastAPI app instance
- Configure logging
- Register middleware (CORS, request ID, access log)
- Register exception handlers
- Include API routers
- Define application lifecycle hooks (startup/shutdown)

Keep this file small. If it grows beyond ~150 lines, we've put logic here
that belongs elsewhere.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.middleware import AccessLogMiddleware, RequestIdMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager.

    Code before `yield` runs at startup.
    Code after `yield` runs at shutdown.
    """
    configure_logging()
    log = get_logger(__name__)
    log.info(
        "application_starting",
        app_name=settings.APP_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )

    # Recover files orphaned by a previous process crash/restart.
    try:
        from app.services.stuck_files import recover_stuck_files

        result = await recover_stuck_files()
        if result["found"] > 0:
            log.warning(
                "startup_recovered_stuck_files",
                found=result["found"],
                recovered=result["recovered"],
                file_ids=result["file_ids"],
            )
    except Exception as exc:
        log.error("startup_stuck_file_recovery_failed", error=str(exc))

    yield  # --- application is running ---

    log.info("application_shutting_down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "Mays Forge OS — urban sustainability and infrastructure intelligence backend API."
    ),
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# --- Middleware ---
# Middleware order matters. Starlette runs them in REVERSE order of
# registration on the way IN, and forward order on the way OUT.
# We register CORS last so it runs first — it needs to handle preflight
# OPTIONS requests before anything else touches them.
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# --- Exception handlers ---
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)

# --- Routers ---
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Root endpoint — a polite signpost to the API docs."""
    return {
        "message": f"{settings.APP_NAME} API",
        "docs": "/docs" if not settings.is_production else "disabled",
        "health": "/api/v1/health",
    }
