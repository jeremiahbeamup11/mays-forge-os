"""Authentication and security utilities.

This module verifies Supabase-issued JWT access tokens. Supabase signs
tokens with HS256 using a per-project JWT secret. If we have the secret
(which we do — it's in our .env), we can verify tokens locally on every
request without making a network call to Supabase. That means auth checks
add microseconds, not milliseconds, to every request.

Design decisions:
- We verify signature, expiration, and audience claim.
- We require `sub` (subject — the user's UUID).
- We expose a minimal `AuthenticatedUser` type rather than leaking the
  raw JWT payload into route handlers. Route handlers should never touch
  raw tokens.
"""

from dataclasses import dataclass

import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidTokenError,
    PyJWTError,
)

from app.config import settings


class AuthError(Exception):
    """Base class for authentication failures.

    Caught in the dependency layer and converted to 401 responses. Keeping
    a custom exception type (rather than raising HTTPException directly)
    keeps this module framework-agnostic and easier to test.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents the authenticated user derived from a verified JWT.

    Intentionally minimal. If you need more fields (role, org membership),
    fetch them from the database via a separate query — don't stuff them
    into the token and trust them blindly.
    """

    id: str
    email: str | None
    role: str


def verify_access_token(token: str) -> AuthenticatedUser:
    """Verify a Supabase JWT and return the authenticated user.

    Raises AuthError if the token is invalid for any reason.
    """
    if not token:
        raise AuthError("missing_token")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
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

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise AuthError("invalid_subject")

    email_raw = payload.get("email")
    email = email_raw if isinstance(email_raw, str) else None

    role_raw = payload.get("role")
    role = role_raw if isinstance(role_raw, str) else "authenticated"

    return AuthenticatedUser(id=user_id, email=email, role=role)
