"""Calendar evaluation without exposing a parser to application code."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime


class ScheduleEvaluator(Protocol):
    """Resolve occurrences in the instance zone as UTC instants."""

    async def latest_fire(
        self, expression: str, timezone: str, *, after: datetime, until: datetime
    ) -> datetime | None:
        """Return the latest fire in (after, until], or None."""
        ...

    async def next_fire(
        self, expression: str, timezone: str, *, after: datetime
    ) -> datetime | None:
        """Return the next occurrence strictly after the supplied instant."""
        ...
