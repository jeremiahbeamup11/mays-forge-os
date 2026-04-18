"""Health check endpoints.

Health checks are not glamorous, but they are the first thing a deployment
platform (Render, Kubernetes, load balancers) hits to decide whether your
service is alive. A well-designed health endpoint distinguishes between:

- Liveness: "the process is running" — very cheap, no downstream calls
- Readiness: "the process is ready to serve requests" — may check DB, etc.

For now we only need liveness. Readiness will matter once Supabase is wired in.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response model for the health check endpoint.

    Using a Pydantic model (rather than returning a raw dict) gives us:
    - Automatic OpenAPI schema documentation
    - Guaranteed response shape — no typos in field names
    - A single source of truth that both the backend and frontend can reference
    """

    status: str = Field(description="Overall service status.", examples=["ok"])
    app_name: str = Field(description="Name of the application.")
    version: str = Field(description="Application version.")
    environment: str = Field(description="Deployment environment.")
    timestamp: datetime = Field(description="Current server time in UTC.")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Returns basic service status. Used by deployment platforms to verify the service is alive.",
)
async def health() -> HealthResponse:
    """Return a liveness check response.

    This endpoint must remain dependency-free (no database calls, no external
    APIs) so it stays fast and reliable even when downstream systems are down.
    """
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
    )