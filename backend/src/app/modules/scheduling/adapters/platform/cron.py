"""Timezone-aware cron evaluation; the parser stays outside the domain."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from cronsim import CronSim, CronSimError

from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class CronSchedule:
    """A five-field cron expression evaluated in the instance timezone."""

    expression: str
    zone: ZoneInfo

    def __post_init__(self) -> None:
        """Validate expressions before they reach the worker loop."""
        if len(self.expression.split()) != 5:
            raise ValidationError("A schedule must have five cron fields")
        try:
            CronSim(self.expression, datetime(2000, 1, 1, tzinfo=self.zone))
        except CronSimError as exc:
            raise ValidationError(f"Invalid cron schedule: {self.expression}") from exc

    def fires_between(self, after: datetime, until: datetime) -> Iterator[datetime]:
        """Yield UTC fire times in (after, until], including DST adjustments."""
        if after.utcoffset() is None or until.utcoffset() is None:
            raise ValidationError("Timezone-aware datetimes are required")
        start = after.astimezone(UTC)
        end = until.astimezone(UTC)
        for local in CronSim(self.expression, after.astimezone(self.zone)):
            moment = local.astimezone(UTC)
            if moment > end:
                break
            if moment > start:
                yield moment
