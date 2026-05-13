"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from .env and environment variables.

    Pydantic Settings validates every field at startup. If a required field
    is missing or malformed, the app will refuse to start — which is exactly
    what we want. Failing fast in config is always better than failing
    mysteriously three layers deep in a request handler.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Application metadata ---
    APP_NAME: str = "Mays Forge OS"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # --- AI Provider Keys (optional; validated at use-site) ---
    ANTHROPIC_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # --- Supabase (required) ---
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_ANON_KEY: str = Field(..., description="Supabase anon/public key")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ..., description="Supabase service role key (server-side only)"
    )

    # --- Security ---
    JWT_SECRET: str = Field(
        ..., description="JWT secret from Supabase; used to verify access tokens"
    )
    JWT_ALGORITHM: str = "ES256"
    JWT_AUDIENCE: str = "authenticated"

    # --- CORS ---
    CORS_ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed frontend origins.",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins string into a list."""
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Using lru_cache ensures Settings() is instantiated exactly once per process.
    In tests, you can override this with `get_settings.cache_clear()` and
    reconfigure environment variables.

    Note: mypy can't see that Pydantic Settings loads required fields from
    the environment at runtime, so we suppress the spurious call-arg error.
    """
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
