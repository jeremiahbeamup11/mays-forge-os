"""Authenticated user endpoints.

The /me endpoint is the canonical way for a frontend to ask "who am I,
based on the token I just sent?" It's the simplest proof that auth works
end-to-end.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser

router = APIRouter(tags=["me"])


class MeResponse(BaseModel):
    """Response model for the /me endpoint."""

    id: str = Field(description="User's unique identifier (Supabase auth UID).")
    email: str | None = Field(description="User's email, if available on the token.")
    role: str = Field(description="User's role claim from the JWT.")


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current authenticated user",
    description="Returns the identity of the user making the request. Requires a valid Supabase JWT.",
)
async def read_me(user: CurrentUser) -> MeResponse:
    """Return basic info about the authenticated caller."""
    return MeResponse(id=user.id, email=user.email, role=user.role)
