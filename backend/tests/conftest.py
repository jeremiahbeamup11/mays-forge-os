"""Shared pytest fixtures and configuration for the Mays Forge OS backend.

Fixtures defined here are automatically available in every test file in
the tests/ directory, no imports needed. This keeps tests DRY.
"""

import time
from collections.abc import AsyncIterator, Callable

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app

# Type alias for the token factory fixture — improves readability in tests.
TokenFactory = Callable[..., str]


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client that talks directly to the FastAPI app.

    This uses httpx's ASGITransport, which routes requests through the app's
    ASGI interface in-process — no actual network, no live server needed.
    Result: tests are fast, isolated, and deterministic.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def make_token() -> TokenFactory:
    """Factory fixture that builds signed JWTs for tests.

    Produces tokens signed with the same secret and algorithm the app uses
    to verify them. This means tests exercise the real verification path
    without needing to hit Supabase.

    Usage:
        def test_something(make_token):
            token = make_token(sub="user-123", email="a@b.com")
            response = await client.get(
                "/api/v1/me",
                headers={"Authorization": f"Bearer {token}"},
            )

    Supports overrides for every field so tests can construct expired,
    wrong-audience, malformed, or otherwise-broken tokens.
    """

    def _build(
        *,
        sub: str = "11111111-1111-1111-1111-111111111111",
        email: str | None = "test@example.com",
        role: str = "authenticated",
        audience: str | None = None,
        expires_in: int = 3600,
        secret: str | None = None,
        algorithm: str | None = None,
        extra_claims: dict[str, object] | None = None,
    ) -> str:
        now = int(time.time())
        payload: dict[str, object] = {
            "sub": sub,
            "aud": audience if audience is not None else settings.JWT_AUDIENCE,
            "iat": now,
            "exp": now + expires_in,
            "role": role,
        }
        if email is not None:
            payload["email"] = email
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(
            payload,
            secret if secret is not None else settings.JWT_SECRET,
            algorithm=algorithm if algorithm is not None else settings.JWT_ALGORITHM,
        )

    return _build
