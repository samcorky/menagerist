"""Deployment settings for recurring background jobs."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict

from app.platform.config._base import MenageristBaseSettings


class SchedulerSettings(MenageristBaseSettings):
    """Instance timezone and the amount of job history to retain."""

    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True)

    timezone: ZoneInfo = Field(
        default_factory=lambda: ZoneInfo("UTC"),
        validation_alias=AliasChoices("MENAGERIST_TIMEZONE", "TZ"),
        description="Timezone used to interpret recurring job schedules.",
    )
    run_history_per_job: int = Field(
        default=100,
        ge=1,
        description="Number of completed runs to retain for each job.",
    )


@lru_cache(maxsize=1)
def get_scheduler_settings() -> SchedulerSettings:
    """Return the cached scheduler settings."""
    return SchedulerSettings()
