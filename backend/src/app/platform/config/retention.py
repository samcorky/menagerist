from functools import lru_cache
from typing import Annotated

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable
from app.platform.config._types import Cron  # noqa: TC001 - pydantic resolves this at runtime


class RetentionSettings(MenageristBaseSettings, group="retention"):
    """How long deleted content stays recoverable before it is purged."""

    deleted_days: int = Field(
        default=30,
        ge=1,
        description="Days deleted content stays recoverable before it is purged.",
    )
    purge_schedule: Annotated[
        Cron,
        Field(
            title="Deleted items removal schedule",
            description=(
                "Cron expression for permanently removing content older than the "
                + "retention period, in the instance timezone. Empty, the default, "
                + "leaves it to the data purge-deleted command."
            ),
        ),
        Tunable(),
    ] = ""


@lru_cache(maxsize=1)
def get_retention_settings() -> RetentionSettings:
    """Return the cached retention settings."""
    return RetentionSettings()
