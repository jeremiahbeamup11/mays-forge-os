"""Pydantic models for the organization domain.

These models describe the shape of organization data as it flows through
the API layer. They are distinct from the database schema:

- Database column names and types live in SQL migrations.
- API shapes live here.

Keeping them separate means we can evolve the API without every database
change breaking clients, and vice versa.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Valid roles mirror the Postgres enum in the init_orgs_and_memberships migration.
# If you add a new role in SQL, add it here too.
MembershipRole = Literal["owner", "admin", "member"]


class Organization(BaseModel):
    """A single organization (tenant) in Mays Forge OS."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Organization UUID.")
    name: str = Field(description="Display name, e.g. 'Village of Peotone'.")
    slug: str = Field(description="URL-safe identifier, e.g. 'peotone-il'.")
    created_at: datetime = Field(description="When the org was created.")
    updated_at: datetime = Field(description="Last time the org was modified.")


class OrganizationMembership(BaseModel):
    """An organization the caller belongs to, with their role in it."""

    model_config = ConfigDict(from_attributes=True)

    organization: Organization
    role: MembershipRole = Field(description="Caller's role in this organization.")


class OrganizationsListResponse(BaseModel):
    """Response shape for GET /api/v1/organizations/mine."""

    organizations: list[OrganizationMembership] = Field(
        description="Organizations the caller is a member of."
    )
