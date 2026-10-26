"""The effective schedule for a registered job."""

from typing import Protocol


class ScheduleSource(Protocol):
    """Read deployment schedules now and layered settings later."""

    async def schedule_for(self, schedule_key: str) -> str | None:
        """Return a cron expression, or None when scheduling is disabled."""
        ...
