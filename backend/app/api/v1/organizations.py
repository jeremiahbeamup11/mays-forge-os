"""Organization endpoints.

These endpoints are always tenant-scoped. They never return data belonging
to orgs the caller isn't a member of — a guarantee enforced by Row-Level
Security at the database layer, not just by our query code.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import CurrentUser
from app.db.organizations import list_memberships_for_user
from app.models.organization import (
    Organization,
    OrganizationMembership,
    OrganizationsListResponse,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])

# We need the raw JWT here — not just the AuthenticatedUser — to pass to the
# user-scoped Supabase client. Reuse the same bearer parser the deps module uses.
_bearer = HTTPBearer(auto_error=False)


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
    """Return the caller's organizations.

    The `_user` dependency ensures the request is authenticated; its
    underscore prefix signals we don't use its value directly — we just need
    the side effect of it raising 401 on bad auth. The raw bearer token
    is what we actually pass down to the database layer.
    """
    if credentials is None or not credentials.credentials:
        # Shouldn't be reachable because CurrentUser already validated, but
        # we belt-and-suspender here to satisfy the type checker.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials.",
        )

    rows = await list_memberships_for_user(credentials.credentials)

    memberships: list[OrganizationMembership] = []
    for row in rows:
        org_data = row.get("organization")
        role = row.get("role")
        if not isinstance(org_data, dict) or not isinstance(role, str):
            # Skip malformed rows rather than 500ing the whole request.
            continue
        memberships.append(
            OrganizationMembership(
                organization=Organization(**org_data),
                role=role,  # type: ignore[arg-type]
            )
        )

    return OrganizationsListResponse(organizations=memberships)
