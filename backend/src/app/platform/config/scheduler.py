"""Deployment settings for recurring background jobs."""

from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import SettingsConfigDict

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable


class SchedulerSettings(MenageristBaseSettings, group="scheduler"):
    """Instance timezone, worker liveness and job history retention."""

    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True)

    timezone: ZoneInfo = Field(
        default_factory=lambda: ZoneInfo("UTC"),
        validation_alias=AliasChoices("MENAGERIST_TIMEZONE", "TZ"),
        description="Timezone used to interpret recurring job schedules.",
    )
    run_history_per_job: Annotated[
        int,
        Field(
            ge=1,
            title="Runs kept per task",
            description="Number of completed runs to retain for each job.",
        ),
        Tunable(),
    ] = 100
    worker_heartbeat_timeout_seconds: int = Field(
        default=300,
        gt=0,
        description="Seconds without a worker heartbeat before liveness checks warn.",
    )
    worker_heartbeat_interval_seconds: int = Field(
        default=60,
        gt=0,
        description="Seconds between the worker's liveness heartbeats.",
    )

    @model_validator(mode="after")
    def _heartbeat_interval_within_timeout(self) -> SchedulerSettings:
        """Require time for a worker to check in before its heartbeat expires."""
        if (
            self.worker_heartbeat_interval_seconds
            >= self.worker_heartbeat_timeout_seconds
        ):
            msg = "Worker heartbeat interval must be shorter than its timeout"
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_scheduler_settings() -> SchedulerSettings:
    """Return the cached scheduler settings."""
    return SchedulerSettings()
