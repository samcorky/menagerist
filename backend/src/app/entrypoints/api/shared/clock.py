"""The request's own "today": the date in the time zone the client names."""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, tzinfo
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Header

from app.platform.config import get_server_settings

type Today = Callable[[], date]

# IANA names are letters, digits and `_+-/`; anything else is never looked up.
_ZONE_NAME = re.compile(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+){0,2}")


def zone_named(name: str | None, fallback: tzinfo = UTC) -> tzinfo:
    """The zone `name` names, or `fallback` if it is missing or not an IANA zone."""
    if not name or len(name) > 64 or not _ZONE_NAME.fullmatch(name):
        return fallback
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        return fallback


def today_in(zone: tzinfo) -> Today:
    """A clock that reads today's date in `zone` each time it is asked."""
    return lambda: datetime.now(zone).date()


def get_today(
    time_zone: Annotated[
        str | None,
        Header(
            alias="Time-Zone",
            description=(
                "An IANA time zone, such as `Europe/London`, for relative dates like "
                + "'the last 30 days'. Missing or unknown means the server's zone "
                + "(`MENAGERIST_TIME_ZONE`)."
            ),
        ),
    ] = None,
) -> Today:
    """Today in the zone the request names, or the server's, for relative dates."""
    return today_in(zone_named(time_zone, get_server_settings().time_zone))
