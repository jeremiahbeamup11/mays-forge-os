"""Authentication and security utilities.

Verifies Supabase-issued JWT access tokens. Supabase signs tokens with
ES256 (ECDSA with P-256 curve) using asymmetric keys. The public keys
are published at the project's JWKS endpoint.

We fetch and cache the public keys, then verify each token's signature
locally — no network call per request after the initial key fetch.

Design decisions:
- We verify signature, expiration, and audience claim.
- We require `sub` (subject — the user's UUID).
- We expose a minimal `AuthenticatedUser` type rather than leaking the
  raw JWT payload into route handlers.
"""

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidTokenError,
    PyJWTError,
)

from app.config import settings
from app.core.logging import get_logger

_log = get_logger(__name__)


class AuthError(Exception):
    """Base class for authentication failures."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents the authenticated user derived from a verified JWT."""

    id: str
    email: str | None
    role: str


# JWKS endpoint for the Supabase project. Public keys rotate occasionally;
# PyJWKClient caches them and refreshes when it encounters an unknown kid.
_JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Lazy-initialize the JWKS client (cached after first call)."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_JWKS_URL, cache_keys=True)
    return _jwks_client


def verify_access_token(token: str) -> AuthenticatedUser:
    """Verify a Supabase JWT and return the authenticated user.

    Raises AuthError if the token is invalid for any reason.
    """
    if not token:
        raise AuthError("missing_token")

    try:
        # Fetch the signing key that matches this token's `kid` header.
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience=settings.JWT_AUDIENCE,
            options={
                "require": ["exp", "sub", "aud"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
            },
        )
    except ExpiredSignatureError as exc:
        raise AuthError("token_expired") from exc
    except InvalidAudienceError as exc:
        raise AuthError("invalid_audience") from exc
    except InvalidTokenError as exc:
        raise AuthError("invalid_token") from exc
    except PyJWTError as exc:
        raise AuthError("token_verification_failed") from exc
    except Exception as exc:
        # Catch JWKS fetch failures (network errors, malformed response).
        _log.error("jwks_fetch_failed", error=str(exc))
        raise AuthError("token_verification_failed") from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise AuthError("invalid_subject")

    email_raw = payload.get("email")
    email = email_raw if isinstance(email_raw, str) else None

    role_raw = payload.get("role")
    role = role_raw if isinstance(role_raw, str) else "authenticated"

    return AuthenticatedUser(id=user_id, email=email, role=role)
