from functools import lru_cache

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings


class RetentionSettings(MenageristBaseSettings, group="retention"):
    """How long deleted content stays recoverable before it is purged."""

    deleted_days: int = Field(
        default=30,
        ge=1,
        description="Days deleted content stays recoverable before it is purged.",
    )


@lru_cache(maxsize=1)
def get_retention_settings() -> RetentionSettings:
    """Return the cached retention settings."""
    return RetentionSettings()
