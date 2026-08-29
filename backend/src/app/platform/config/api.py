from functools import lru_cache

from pydantic import Field

from app.platform.config._base import CSV, MenageristBaseSettings


class ApiSettings(MenageristBaseSettings):
    """API entrypoint settings."""

    cors_origins: CSV[str] = Field(default=["*"])


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Return the cached API settings."""
    return ApiSettings()
