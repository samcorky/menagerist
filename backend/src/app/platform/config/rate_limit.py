from functools import lru_cache

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings


class RateLimitSettings(MenageristBaseSettings, group="rate_limit"):
    """Request limits on the endpoints that are expensive to serve.

    Each limit is per signed-in user per minute and counted in each server
    process separately, so the effective limit is the setting times the number
    of workers. `0` turns a limit off.
    """

    uploads_per_minute: int = Field(
        default=30,
        ge=0,
        description="Media and backup uploads allowed per user each minute.",
    )
    thumbnails_per_minute: int = Field(
        default=600,
        ge=0,
        description="Thumbnail requests allowed per user each minute.",
    )
    search_per_minute: int = Field(
        default=120,
        ge=0,
        description="Item searches allowed per user each minute.",
    )
    imports_per_minute: int = Field(
        default=10,
        ge=0,
        description="Preset and user-data imports allowed per user each minute.",
    )


@lru_cache(maxsize=1)
def get_rate_limit_settings() -> RateLimitSettings:
    """Return the cached rate limit settings."""
    return RateLimitSettings()
