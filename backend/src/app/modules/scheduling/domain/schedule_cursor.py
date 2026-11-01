"""Observation cursors are independent of retained or manually requested runs."""

from dataclasses import dataclass, replace
from datetime import datetime

from app.modules.scheduling.domain.job_run import utc_instant


@dataclass(frozen=True, kw_only=True, eq=False)
class ScheduleCursor:
    """The deployment schedule and last interval observed for one job."""

    job_key: str
    expression: str | None
    timezone: str
    checked_until: datetime
    # Set by `observe` when it replaced a different schedule; never stored.
    changed_from: ScheduleCursor | None = None

    def __post_init__(self) -> None:
        """Store the observation boundary as an absolute UTC instant."""
        object.__setattr__(self, "checked_until", utc_instant(self.checked_until))

    def observe(
        self, expression: str | None, timezone: str, now: datetime
    ) -> ScheduleCursor:
        """Start a new interval when deployment configuration changes."""
        now = utc_instant(now)
        if self.expression != expression or self.timezone != timezone:
            return replace(
                self,
                expression=expression,
                timezone=timezone,
                checked_until=max(self.checked_until, now),
                changed_from=self,
            )
        return self if self.changed_from is None else replace(self, changed_from=None)

    def advance(self, now: datetime) -> ScheduleCursor:
        """Advance monotonically even if the worker clock moves backwards."""
        return replace(self, checked_until=max(self.checked_until, utc_instant(now)))
