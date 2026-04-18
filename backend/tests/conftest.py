"""Shared pytest fixtures and configuration for the Mays Forge OS backend.

Fixtures defined here are automatically available in every test file in
the tests/ directory, no imports needed. This keeps tests DRY.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client that talks directly to the FastAPI app.

    This uses httpx's ASGITransport, which routes requests through the app's
    ASGI interface in-process — no actual network, no live server needed.
    Result: tests are fast, isolated, and deterministic.

    Usage in a test:
        async def test_something(client: AsyncClient) -> None:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
