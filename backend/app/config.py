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

    # --- Supabase (required once we wire up the database) ---
    # Marked optional for now so the app can boot without them during setup.
    # We'll tighten these to required once auth is integrated.
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # --- Security ---
    JWT_SECRET: str | None = None

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
    """
    return Settings()


settings = get_settings()