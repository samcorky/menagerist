from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable
from app.platform.config._types import Cron  # noqa: TC001 - pydantic resolves this at runtime


class ReleaseSettings(MenageristBaseSettings, group="release"):
    """Which releases the instance looks for and how often."""

    channel: Annotated[
        Literal["stable", "preview"],
        Field(
            title="Release channel",
            description=(
                "Releases to report: stable only, or preview, which also includes "
                + "release candidates and other prereleases."
            ),
        ),
        Tunable(),
    ] = "stable"
    check_schedule: Annotated[
        Cron,
        Field(
            title="Update check schedule",
            description=(
                "Cron expression for looking for a newer release in the instance "
                + "timezone. Empty turns the scheduled check off; an administrator "
                + "can still check from the Status page."
            ),
        ),
        Tunable(),
    ] = "20 5 * * *"


@lru_cache(maxsize=1)
def get_release_settings() -> ReleaseSettings:
    """Return the cached release settings."""
    return ReleaseSettings()
