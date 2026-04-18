"""FastAPI application entry point.

Responsibilities of this file:
- Create the FastAPI app instance
- Configure logging
- Register middleware (CORS, future: rate limiting, request ID injection)
- Include API routers
- Define application lifecycle hooks (startup/shutdown)

Keep this file small. If it grows beyond ~100 lines, we've put logic here
that belongs elsewhere.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager.

    Code before `yield` runs at startup.
    Code after `yield` runs at shutdown.

    This is the modern FastAPI pattern (replaces deprecated @app.on_event).
    """
    configure_logging()
    log = get_logger(__name__)
    log.info(
        "application_starting",
        app_name=settings.APP_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )

    yield  # --- application is running ---

    log.info("application_shutting_down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "Mays Forge OS — urban sustainability and infrastructure "
        "intelligence backend API."
    ),
    lifespan=lifespan,
    # Docs are useful in dev; disable or protect in production.
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# --- Middleware ---
# CORS lets your Next.js frontend (on a different origin) call this API.
# Without this, browsers will block requests with a CORS error.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

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