"""Cron-backed schedule evaluation behind the application-facing port."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.modules.scheduling.adapters.platform.cron import CronSchedule


class CronScheduleEvaluator:
    """Keep cron parsing and timezone rules in a driven adapter."""

    async def latest_fire(
        self, expression: str, timezone: str, *, after: datetime, until: datetime
    ) -> datetime | None:
        """Evaluate forward so spring-forward catch-up occurrences are preserved."""
        latest = None
        for fire in CronSchedule(
            expression=expression, zone=ZoneInfo(timezone)
        ).fires_between(after, until):
            latest = fire
        return latest

    async def next_fire(
        self, expression: str, timezone: str, *, after: datetime
    ) -> datetime | None:
        """Use the same interval rules for next-run previews and execution."""
        fires = CronSchedule(
            expression=expression, zone=ZoneInfo(timezone)
        ).fires_between(after, datetime.max.replace(tzinfo=UTC))
        return next(fires, None)
