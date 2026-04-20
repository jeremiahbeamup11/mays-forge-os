"""Tests for the health check and root endpoints.

These tests establish the pattern every future endpoint test will follow:
1. Make a request via the async client.
2. Assert the status code.
3. Assert key fields of the response body.

We don't assert every field exhaustively — we assert the ones that matter
for the endpoint's contract. Over-asserting makes tests brittle (they break
on harmless changes); under-asserting lets real bugs slip through. Aim for
"the contract is honored" not "the response is byte-identical."
"""

from httpx import AsyncClient


class TestRootEndpoint:
    """Tests for the root `/` endpoint."""

    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/")
        assert response.status_code == 200

    async def test_returns_expected_keys(self, client: AsyncClient) -> None:
        response = await client.get("/")
        data = response.json()
        assert "message" in data
        assert "docs" in data
        assert "health" in data

    async def test_health_link_matches_actual_endpoint(self, client: AsyncClient) -> None:
        """The root endpoint should point to a working health endpoint."""
        root_response = await client.get("/")
        health_path = root_response.json()["health"]

        health_response = await client.get(health_path)
        assert health_response.status_code == 200


class TestHealthEndpoint:
    """Tests for the `/api/v1/health` endpoint."""

    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_status_is_ok(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.json()["status"] == "ok"

    async def test_response_includes_required_fields(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        data = response.json()
        for field in ("status", "app_name", "version", "environment", "timestamp"):
            assert field in data, f"Missing required field: {field}"

    async def test_environment_is_valid(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        env = response.json()["environment"]
        assert env in {"development", "staging", "production"}

    async def test_no_sensitive_data_leaks(self, client: AsyncClient) -> None:
        """Health endpoint must never leak secrets or internal config.

        This is a regression test against accidentally adding debug info.
        """
        response = await client.get("/api/v1/health")
        body = response.text.lower()
        forbidden_substrings = (
            "api_key",
            "secret",
            "password",
            "jwt",
            "supabase_url",
            "anthropic",
            "gemini",
        )
        for forbidden in forbidden_substrings:
            assert forbidden not in body, f"Health response leaks: {forbidden}"


class TestErrorResponses:
    """Tests for the global error handlers — ensures consistent error shape."""

    async def test_404_returns_structured_error(self, client: AsyncClient) -> None:
        """Unknown paths must return our ErrorResponse shape, not raw {detail:...}."""
        response = await client.get("/api/v1/this-does-not-exist")
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
        assert "message" in data
        assert "request_id" in data

    async def test_all_errors_include_request_id(self, client: AsyncClient) -> None:
        """Every error response must include the request_id for debuggability."""
        response = await client.get("/api/v1/this-does-not-exist")
        data = response.json()
        assert data["request_id"] is not None

    async def test_request_id_header_present_on_success(self, client: AsyncClient) -> None:
        """Successful responses must expose the X-Request-ID header."""
        response = await client.get("/api/v1/health")
        assert "x-request-id" in {k.lower() for k in response.headers.keys()}

    async def test_request_id_header_present_on_error(self, client: AsyncClient) -> None:
        """Error responses must also expose the X-Request-ID header."""
        response = await client.get("/api/v1/this-does-not-exist")
        assert "x-request-id" in {k.lower() for k in response.headers.keys()}
