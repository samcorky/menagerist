from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Labels, Scope, Tunable
from app.platform.config._types import TimeZoneChoice  # noqa: TC001 - pydantic resolves this at runtime


class DateTimeSettings(
    MenageristBaseSettings, group="datetime", label="Dates and times"
):
    """How dates, times and weeks read. People choose; the deployment sets defaults."""

    time_zone: Annotated[
        TimeZoneChoice,
        Field(
            title="Time zone",
            description=(
                "The zone times are shown in, and that decides when a day starts for "
                + "dates like 'the last 30 days'. Match my browser follows the device."
            ),
        ),
        # Each person's device is the right default; the server's zone is a separate
        # setting (MENAGERIST_TIME_ZONE), so this one has no variable of its own.
        Tunable(scope=Scope.USER, env_default=False),
    ] = "browser"
    date_order: Annotated[
        Literal["automatic", "dmy", "mdy", "ymd"],
        Labels(
            {
                "automatic": "Automatic (from your language)",
                "dmy": "Day first (31/12/2026, 31 Dec 2026)",
                "mdy": "Month first (12/31/2026, Dec 31, 2026)",
                "ymd": "Year first (2026-12-31)",
            }
        ),
        Field(
            title="Date format",
            description=(
                "The order dates are written in. Automatic uses your browser's "
                + "language."
            ),
        ),
        Tunable(scope=Scope.USER),
    ] = "automatic"
    clock: Annotated[
        Literal["automatic", "12h", "24h"],
        Labels(
            {
                "automatic": "Automatic (from your language)",
                "12h": "12-hour (2:30 pm)",
                "24h": "24-hour (14:30)",
            }
        ),
        Field(
            title="Clock",
            description=(
                "How times of day are written. Automatic uses your browser's language."
            ),
        ),
        Tunable(scope=Scope.USER),
    ] = "automatic"

    first_day: Annotated[
        Literal["automatic", "monday", "sunday", "saturday"],
        Labels(
            {
                "automatic": "Automatic (from your region)",
                "monday": "Monday",
                "sunday": "Sunday",
                "saturday": "Saturday",
            }
        ),
        Field(
            title="First day of the week",
            description=(
                "The day calendars start each week on. Automatic uses your "
                + "region's usual start."
            ),
        ),
        Tunable(scope=Scope.USER),
    ] = "automatic"


@lru_cache(maxsize=1)
def get_date_time_settings() -> DateTimeSettings:
    """Return the cached date and time settings."""
    return DateTimeSettings()
