"""Shared pytest fixtures and configuration for the Mays Forge OS backend."""

import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

import app.api.deps as _deps_module
import app.core.security as _security_module
from app.config import settings
from app.core.security import AuthenticatedUser, AuthError
from app.main import app

TokenFactory = Callable[..., str]


def _test_verify_access_token(token: str) -> AuthenticatedUser:
    """Test-only token verifier that accepts HS256 tokens."""
    if not token:
        raise AuthError("missing_token")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            audience=settings.JWT_AUDIENCE,
            options={
                "require": ["exp", "sub", "aud"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
            },
        )
    except jwt.PyJWTError as exc:
        raise AuthError("invalid_token") from exc

    user_id = payload.get("sub", "")
    email_raw = payload.get("email")
    email = email_raw if isinstance(email_raw, str) else None
    role_raw = payload.get("role")
    role = role_raw if isinstance(role_raw, str) else "authenticated"
    return AuthenticatedUser(id=user_id, email=email, role=role)


# Patch both the source module and the importing module so the test
# verifier is used everywhere, regardless of import order.
_security_module.verify_access_token = _test_verify_access_token  # type: ignore[assignment]
_deps_module.verify_access_token = _test_verify_access_token  # type: ignore[assignment]


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client that talks directly to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def make_token() -> TokenFactory:
    """Factory fixture that builds signed JWTs for tests."""

    def _build(
        *,
        sub: str = "11111111-1111-1111-1111-111111111111",
        email: str | None = "test@example.com",
        role: str = "authenticated",
        audience: str | None = None,
        expires_in: int = 3600,
        secret: str | None = None,
        algorithm: str | None = None,
        extra_claims: dict[str, Any] | None = None,
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
            algorithm=algorithm if algorithm is not None else "HS256",
        )

    return _build
