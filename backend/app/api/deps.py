"""Shared FastAPI dependencies.

Dependencies declared here are injected into route handlers via FastAPI's
`Depends()` mechanism. Placing them in a single file keeps the API layer
consistent — every route that needs authentication uses the same dependency.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import AuthenticatedUser, AuthError, verify_access_token

# HTTPBearer parses `Authorization: Bearer <token>` headers for us.
# auto_error=False means we handle the "no header" case ourselves, giving
# us consistent 401 responses instead of FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser:
    """Dependency that returns the authenticated user or raises 401.

    Usage in a route:

        @router.get("/me")
        async def read_me(user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
            return {"id": user.id, "email": user.email}
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verify_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc.reason}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# A convenient type alias so route signatures read naturally:
#     async def endpoint(user: CurrentUser) -> ...
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
