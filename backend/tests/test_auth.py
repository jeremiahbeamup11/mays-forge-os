"""Tests for the authentication layer.

These tests cover the /api/v1/me endpoint because it's the simplest
protected endpoint. The same verification code guards every other
protected endpoint, so testing it thoroughly here means we don't have to
re-test auth on every future endpoint — we just test the endpoint's
specific business logic.
"""

from collections.abc import Callable

from httpx import AsyncClient

ME_URL = "/api/v1/me"
TokenFactory = Callable[..., str]


class TestMeEndpointUnauthenticated:
    """Verify the protected endpoint rejects everything that isn't a valid token."""

    async def test_no_authorization_header_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL)
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"

    async def test_empty_bearer_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL, headers={"Authorization": "Bearer "})
        assert response.status_code == 401

    async def test_malformed_authorization_header_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL, headers={"Authorization": "NotBearer abc"})
        assert response.status_code == 401

    async def test_garbage_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL, headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401


class TestMeEndpointInvalidTokens:
    """Verify tokens that are structurally valid JWTs but shouldn't be accepted."""

    async def test_wrong_secret_returns_401(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        token = make_token(secret="an-attacker-controlled-secret")  # noqa: S106
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_wrong_audience_returns_401(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        token = make_token(audience="some-other-service")
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_expired_token_returns_401(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        token = make_token(expires_in=-60)
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


class TestMeEndpointAuthenticated:
    """Verify the happy path: a valid token returns the caller's identity."""

    async def test_valid_token_returns_200(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        token = make_token()
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    async def test_response_contains_user_identity(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        token = make_token(sub="abc123", email="bob@peotone.gov")
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        data = response.json()
        assert data["id"] == "abc123"
        assert data["email"] == "bob@peotone.gov"
        assert data["role"] == "authenticated"

    async def test_missing_email_is_handled(
        self, client: AsyncClient, make_token: TokenFactory
    ) -> None:
        """Not every Supabase token will have an email (e.g., anonymous users)."""
        token = make_token(email=None)
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["email"] is None


class TestNoAuthLeakage:
    """Defense-in-depth: verify auth errors don't leak sensitive info."""

    async def test_401_response_does_not_leak_secrets(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL, headers={"Authorization": "Bearer invalid-token-here"})
        body = response.text.lower()
        forbidden = ("jwt_secret", "supabase_url", "supabase_service_role")
        for term in forbidden:
            assert term not in body
