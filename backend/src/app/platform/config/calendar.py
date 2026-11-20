from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Labels, Scope, Tunable


class CalendarSettings(MenageristBaseSettings, group="calendar"):
    """How calendars lay out weeks. People choose; the deployment sets defaults."""

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
def get_calendar_settings() -> CalendarSettings:
    """Return the cached calendar settings."""
    return CalendarSettings()
