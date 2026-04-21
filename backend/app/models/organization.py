"""Pydantic models for the organization domain.

These models describe the shape of organization data as it flows through
the API layer. They are distinct from the database schema:

- Database column names and types live in SQL migrations.
- API shapes live here.

Keeping them separate means we can evolve the API without every database
change breaking clients, and vice versa.
"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Valid roles mirror the Postgres enum in the init_orgs_and_memberships migration.
# If you add a new role in SQL, add it here too.
MembershipRole = Literal["owner", "admin", "member"]


# Slug format enforced at both API (here) and DB (CHECK constraint) layers.
# Defense in depth: API rejects malformed slugs with a clear 422, DB refuses
# them as a last resort.
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


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


class CreateOrganizationRequest(BaseModel):
    """Request body for POST /api/v1/organizations.

    Slug is optional; if omitted, we derive one from the name. Callers who
    want deterministic slugs (e.g. scripting) can provide one explicitly.
    """

    name: str = Field(
        min_length=2,
        max_length=100,
        description="Display name of the organization.",
    )
    slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=60,
        description="URL-safe identifier. Auto-generated from name if omitted.",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name cannot be blank.")
        return stripped

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not _SLUG_PATTERN.match(value):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens between words "
                "(e.g. 'peotone-il')."
            )
        return value


class CreateOrganizationResponse(BaseModel):
    """Response shape for POST /api/v1/organizations.

    Includes the caller's role in the newly created org — always 'owner'
    because the handle_new_organization trigger grants creator-owner.
    """

    organization: Organization
    role: MembershipRole = Field(description="Caller's role in the new org.")


def slugify(name: str) -> str:
    """Derive a URL-safe slug from an organization name.

    Rules:
    - Lowercase
    - Spaces and underscores become hyphens
    - Non-alphanumeric characters dropped
    - Collapse consecutive hyphens
    - Strip leading/trailing hyphens
    - Truncate to 60 characters

    Not guaranteed unique — the DB's unique constraint on slug is the
    final arbiter. If a user's name yields a colliding slug, the API
    surfaces the conflict and asks them to provide an explicit slug.
    """
    lowered = name.strip().lower()
    # Replace any run of non-alphanumeric characters with a single hyphen.
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = slug.strip("-")
    if len(slug) > 60:
        slug = slug[:60].rstrip("-")
    return slug
