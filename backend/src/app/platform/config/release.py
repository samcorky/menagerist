from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Labels, Tunable
from app.platform.config._types import Cron  # noqa: TC001 - pydantic resolves this at runtime


class ReleaseSettings(MenageristBaseSettings, group="release", label="Updates"):
    """Which releases the instance looks for and how often."""

    check_enabled: Annotated[
        bool,
        Field(
            title="Update checks",
            description=(
                "Whether this instance ever contacts github.com and ghcr.io to look "
                + "for newer builds. Off turns off both the scheduled check and the "
                + "Status page's Check now, and is set by the deployment, so an "
                + "administrator cannot turn it back on from the interface."
            ),
        ),
    ] = True
    channel: Annotated[
        Literal["stable", "preview"],
        Labels({"stable": "Stable", "preview": "Preview"}),
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
    check_on_startup: Annotated[
        bool,
        Field(
            title="Check for updates on startup",
            description=(
                "Whether the app also looks for a newer release each time it starts, "
                + "so the Status page is current after a deploy rather than waiting "
                + "for the next scheduled check. Has no effect while update checks "
                + "are off."
            ),
        ),
    ] = True


@lru_cache(maxsize=1)
def get_release_settings() -> ReleaseSettings:
    """Return the cached release settings."""
    return ReleaseSettings()
