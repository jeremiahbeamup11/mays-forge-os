"""Tests for the organizations API layer.

Scope of this file:
- Verify the /api/v1/organizations/mine endpoint correctly shapes responses.
- Verify auth is enforced.
- Verify edge cases (empty lists, malformed rows) are handled gracefully.

Out of scope:
- Whether RLS policies actually enforce tenant isolation. That's the
  database's job and was verified manually against live Supabase via the
  SQL verification script (see docs/RLS_VERIFICATION.md — to be added).
  When we have a dedicated CI Supabase project in Phase 7, we'll add
  integration tests that exercise RLS end-to-end.

We use pytest's monkeypatch to replace the Supabase query function with a
test double. This gives us full control over what the "database" returns,
letting us test every code path without a real network call.
"""

from collections.abc import Callable
from typing import Any

import pytest
from httpx import AsyncClient

MINE_URL = "/api/v1/organizations/mine"
TokenFactory = Callable[..., str]


def _fake_row(
    org_id: str = "11111111-1111-1111-1111-111111111111",
    name: str = "Peotone",
    slug: str = "peotone-il",
    role: str = "owner",
) -> dict[str, Any]:
    """Build a fake Supabase response row in the shape our query returns."""
    return {
        "role": role,
        "organization": {
            "id": org_id,
            "name": name,
            "slug": slug,
            "created_at": "2026-04-20T00:00:00+00:00",
            "updated_at": "2026-04-20T00:00:00+00:00",
        },
    }


class TestMineEndpointUnauthenticated:
    """Auth must be enforced before we even look at the data layer."""

    async def test_no_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(MINE_URL)
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"

    async def test_bad_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(MINE_URL, headers={"Authorization": "Bearer garbage"})
        assert response.status_code == 401


class TestMineEndpointResponseShape:
    """Verify authenticated responses have the expected shape."""

    async def test_empty_list_when_user_has_no_orgs(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A user with no memberships gets an empty list, not an error."""

        async def fake_list(_: str) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr("app.api.v1.organizations.list_memberships_for_user", fake_list)

        token = make_token()
        response = await client.get(MINE_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == {"organizations": []}

    async def test_single_org_is_shaped_correctly(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_list(_: str) -> list[dict[str, Any]]:
            return [_fake_row(name="Peotone", slug="peotone-il", role="owner")]

        monkeypatch.setattr("app.api.v1.organizations.list_memberships_for_user", fake_list)

        token = make_token()
        response = await client.get(MINE_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["organizations"]) == 1

        entry = data["organizations"][0]
        assert entry["role"] == "owner"
        assert entry["organization"]["name"] == "Peotone"
        assert entry["organization"]["slug"] == "peotone-il"
        assert "id" in entry["organization"]
        assert "created_at" in entry["organization"]
        assert "updated_at" in entry["organization"]

    async def test_multiple_orgs_are_all_returned(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_list(_: str) -> list[dict[str, Any]]:
            return [
                _fake_row(
                    org_id="11111111-1111-1111-1111-111111111111",
                    name="Peotone",
                    slug="peotone-il",
                    role="owner",
                ),
                _fake_row(
                    org_id="22222222-2222-2222-2222-222222222222",
                    name="Monee",
                    slug="monee-il",
                    role="member",
                ),
            ]

        monkeypatch.setattr("app.api.v1.organizations.list_memberships_for_user", fake_list)

        token = make_token()
        response = await client.get(MINE_URL, headers={"Authorization": f"Bearer {token}"})
        data = response.json()
        assert len(data["organizations"]) == 2

        slugs = {entry["organization"]["slug"] for entry in data["organizations"]}
        assert slugs == {"peotone-il", "monee-il"}

    async def test_role_is_preserved_per_org(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each org's role must be attached to that specific org, not mixed up."""

        async def fake_list(_: str) -> list[dict[str, Any]]:
            return [
                _fake_row(
                    org_id="11111111-1111-1111-1111-111111111111",
                    name="Peotone",
                    slug="peotone-il",
                    role="owner",
                ),
                _fake_row(
                    org_id="22222222-2222-2222-2222-222222222222",
                    name="Monee",
                    slug="monee-il",
                    role="member",
                ),
            ]

        monkeypatch.setattr("app.api.v1.organizations.list_memberships_for_user", fake_list)

        token = make_token()
        response = await client.get(MINE_URL, headers={"Authorization": f"Bearer {token}"})
        by_slug = {
            entry["organization"]["slug"]: entry["role"]
            for entry in response.json()["organizations"]
        }
        assert by_slug["peotone-il"] == "owner"
        assert by_slug["monee-il"] == "member"


class TestMineEndpointRobustness:
    """Defensive tests: malformed data from the DB shouldn't 500 the endpoint."""

    async def test_row_missing_organization_is_skipped(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A row with a null organization object should be silently dropped."""

        async def fake_list(_: str) -> list[dict[str, Any]]:
            return [
                {"role": "owner", "organization": None},  # malformed
                _fake_row(name="Peotone", slug="peotone-il"),
            ]

        monkeypatch.setattr("app.api.v1.organizations.list_memberships_for_user", fake_list)

        token = make_token()
        response = await client.get(MINE_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert len(response.json()["organizations"]) == 1

    async def test_row_with_missing_role_is_skipped(
        self,
        client: AsyncClient,
        make_token: TokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A row with a null role should be silently dropped."""

        async def fake_list(_: str) -> list[dict[str, Any]]:
            return [
                {"role": None, "organization": _fake_row()["organization"]},
                _fake_row(name="Peotone", slug="peotone-il"),
            ]

        monkeypatch.setattr("app.api.v1.organizations.list_memberships_for_user", fake_list)

        token = make_token()
        response = await client.get(MINE_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert len(response.json()["organizations"]) == 1
