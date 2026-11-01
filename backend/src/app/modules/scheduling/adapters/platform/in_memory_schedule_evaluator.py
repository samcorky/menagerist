"""Precomputed UTC calendar occurrences for application tests."""

from typing import TYPE_CHECKING

from app.modules.scheduling.domain.job_run import utc_instant

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime


class InMemoryScheduleEvaluator:
    """Look up fixed UTC fixtures; timezone behaviour belongs to the cron adapter."""

    def __init__(self, fires: Mapping[str, Sequence[datetime]]) -> None:
        self._fires = {
            expression: tuple(utc_instant(moment) for moment in moments)
            for expression, moments in fires.items()
        }

    async def latest_fire(
        self, expression: str, timezone: str, *, after: datetime, until: datetime
    ) -> datetime | None:
        """Return the latest fixture inside the requested absolute interval."""
        after, until = utc_instant(after), utc_instant(until)
        return max(
            (fire for fire in self._fires[expression] if after < fire <= until),
            default=None,
        )

    async def next_fire(
        self, expression: str, timezone: str, *, after: datetime
    ) -> datetime | None:
        """Return the first future fixture, or None if none remains."""
        after = utc_instant(after)
        return min(
            (fire for fire in self._fires[expression] if fire > after), default=None
        )
