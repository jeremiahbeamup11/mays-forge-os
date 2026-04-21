"""Organization endpoints.

These endpoints are always tenant-scoped. They never return data belonging
to orgs the caller isn't a member of — a guarantee enforced by Row-Level
Security at the database layer, not just by our query code.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import CurrentUser
from app.db.organizations import (
    OrganizationSlugConflictError,
    create_organization,
    list_memberships_for_user,
)
from app.models.organization import (
    CreateOrganizationRequest,
    CreateOrganizationResponse,
    Organization,
    OrganizationMembership,
    OrganizationsListResponse,
    slugify,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])

# We need the raw JWT here — not just the AuthenticatedUser — to pass to the
# user-scoped Supabase client. Reuse the same bearer parser the deps module uses.
_bearer = HTTPBearer(auto_error=False)


def _require_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    """Extract the raw bearer token or raise 401.

    The CurrentUser dependency already validates the token is present and
    well-formed, but FastAPI type checkers don't know that — so we re-check
    at the point we need to use the raw string.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials.",
        )
    return credentials.credentials


@router.get(
    "/mine",
    response_model=OrganizationsListResponse,
    summary="List organizations the caller belongs to",
    description=(
        "Returns every organization the authenticated user is a member of, "
        "along with the user's role in each."
    ),
)
async def list_my_organizations(
    _user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> OrganizationsListResponse:
    """Return the caller's organizations."""
    token = _require_token(credentials)
    rows = await list_memberships_for_user(token)

    memberships: list[OrganizationMembership] = []
    for row in rows:
        org_data = row.get("organization")
        role = row.get("role")
        if not isinstance(org_data, dict) or not isinstance(role, str):
            continue
        memberships.append(
            OrganizationMembership(
                organization=Organization(**org_data),
                role=role,  # type: ignore[arg-type]
            )
        )

    return OrganizationsListResponse(organizations=memberships)


@router.post(
    "",
    response_model=CreateOrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization",
    description=(
        "Creates a new organization and makes the caller its owner. "
        "If slug is omitted, it is derived from the name."
    ),
)
async def create_my_organization(
    body: CreateOrganizationRequest,
    _user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CreateOrganizationResponse:
    """Create an org. The DB trigger auto-creates the caller's owner membership."""
    token = _require_token(credentials)
    slug = body.slug or slugify(body.name)

    if len(slug) < 3:
        # Can happen if slugify drops everything (e.g. non-Latin name).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Could not derive a valid slug from the organization name. "
                "Please provide a slug explicitly."
            ),
        )

    try:
        row = await create_organization(access_token=token, name=body.name, slug=slug)
    except OrganizationSlugConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return CreateOrganizationResponse(
        organization=Organization(**row),
        role="owner",
    )
